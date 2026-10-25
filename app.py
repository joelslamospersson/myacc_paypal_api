"""PayPal Orders v2 checkout backend for MyAAC.

The browser never receives a privileged API credential. MyAAC's authenticated PHP
page calls /internal/* over loopback and signs each request with an HMAC. Only
server-created orders belonging to the authenticated account can grant credit.
"""
import hmac
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256

import mysql.connector
import requests
from flask import Flask, abort, jsonify, request
from werkzeug.middleware.proxy_fix import ProxyFix

from config import (
    DB_CONFIG, PAYPAL, PAYPAL_UI, FLASK_PORT, AMOUNT_TO_POINTS,
    COIN_IMAGES, SECRET_KEY, PAYPAL_INTERNAL_SECRET, Currency,
)

log = logging.getLogger(__name__)
app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=16384,
)
# Flask is behind exactly one trusted localhost reverse proxy.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

ORDER_ID_RE = re.compile(r"^[A-Za-z0-9-]{6,64}$")
MAX_SKEW_SECONDS = 120
PAYPAL_TIMEOUT = (5, 20)
PRICE_MAP = {Decimal(str(k)).quantize(Decimal("0.01")): int(v)
             for k, v in AMOUNT_TO_POINTS.items()}


def connect_db():
    return mysql.connector.connect(**DB_CONFIG)


def create_schema():
    """Only creates missing tables; never silently modifies an existing ledger."""
    conn = connect_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS coin_purchase_agreement_log (
              id INT AUTO_INCREMENT PRIMARY KEY,
              user_id INT NOT NULL,
              accepted_at DATETIME NOT NULL,
              ip_address VARCHAR(45) NOT NULL,
              user_agent VARCHAR(255) NOT NULL,
              order_id VARCHAR(255) NULL,
              payer_email VARCHAR(255) NULL,
              INDEX (user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS myaac_paypal (
              id INT AUTO_INCREMENT PRIMARY KEY,
              txn_id VARCHAR(255) NOT NULL,
              email VARCHAR(255) NOT NULL,
              account_id INT NOT NULL,
              price DECIMAL(10,2) NOT NULL,
              currency VARCHAR(10) NOT NULL,
              points INT NOT NULL,
              payer_status VARCHAR(50) DEFAULT 'verified',
              payment_status VARCHAR(50) DEFAULT 'Completed',
              created DATETIME NOT NULL,
              UNIQUE KEY uq_txn_id (txn_id),
              INDEX (account_id), INDEX (created)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS paypal_pending_orders (
              order_id VARCHAR(64) PRIMARY KEY,
              account_id INT NOT NULL,
              agreement_id INT NOT NULL,
              amount DECIMAL(10,2) NOT NULL,
              currency CHAR(3) NOT NULL,
              points INT NOT NULL,
              created DATETIME NOT NULL,
              INDEX (account_id), INDEX (created)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()
    finally:
        conn.close()


def assert_unique_capture_index(cur):
    """An existing table created without uq_txn_id is NOT fixed by CREATE TABLE."""
    cur.execute("""
        SELECT INDEX_NAME
        FROM information_schema.statistics
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME='myaac_paypal'
              AND NON_UNIQUE=0
        GROUP BY INDEX_NAME
        HAVING COUNT(*)=1 AND MAX(COLUMN_NAME)='txn_id'
    """)
    if not cur.fetchone():
        raise RuntimeError(
            "Missing UNIQUE index on myaac_paypal(txn_id). "
            "Review existing duplicates and add the index before enabling checkout."
        )


def verify_internal_request(action):
    """Authenticate calls from the MyAAC PHP server, never the browser."""
    if request.remote_addr not in ("127.0.0.1", "::1"):
        abort(403)
    timestamp = request.headers.get("X-Paypal-Timestamp", "")
    signature = request.headers.get("X-Paypal-Signature", "")
    try:
        when = int(timestamp)
    except (TypeError, ValueError):
        abort(403)
    if abs(int(datetime.now(timezone.utc).timestamp()) - when) > MAX_SKEW_SECONDS:
        abort(403)
    raw = request.get_data(cache=True)
    expected = hmac.new(
        PAYPAL_INTERNAL_SECRET.encode("utf-8"),
        timestamp.encode("ascii") + b"." + action.encode("ascii") + b"." + raw,
        sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        abort(403)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400)
    account_id = data.get("account_id")
    if type(account_id) is not int or account_id <= 0:
        abort(400)
    return data, account_id


def paypal_base():
    return "https://api-m.sandbox.paypal.com" if PAYPAL["sandbox"] else "https://api-m.paypal.com"


def paypal_token():
    resp = requests.post(
        paypal_base() + "/v1/oauth2/token",
        auth=(PAYPAL_UI["client_id"], PAYPAL_UI["secret"]),
        data={"grant_type": "client_credentials"},
        timeout=PAYPAL_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def paypal_request(method, path, token, *, data=None, idempotency=None):
    headers = {"Authorization": "Bearer " + token,
               "Content-Type": "application/json",
               "Accept": "application/json"}
    if idempotency:
        headers["PayPal-Request-Id"] = idempotency
    resp = requests.request(
        method, paypal_base() + path, headers=headers, json=data,
        timeout=PAYPAL_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def response_error(message, status):
    return jsonify({"success": False, "error": message}), status


def verified_payee(purchase_unit, capture):
    """Fail closed if PayPal does not identify our configured merchant."""
    expected_id = PAYPAL.get("merchant_id", "").strip()
    expected_email = PAYPAL.get("receiver_email", "").strip().casefold()
    for obj in (capture, purchase_unit):
        payee = obj.get("payee") or {}
        if expected_id and payee.get("merchant_id") == expected_id:
            return True
        if expected_email and payee.get("email_address", "").casefold() == expected_email:
            return True
    return False


def validate_capture(order, account_id, expected_price, expected_currency):
    if order.get("status") != "COMPLETED":
        raise ValueError("PayPal order is not completed")
    units = order.get("purchase_units") or []
    if len(units) != 1:
        raise ValueError("Unexpected PayPal purchase units")
    unit = units[0]
    if unit.get("custom_id") != str(account_id):
        raise ValueError("PayPal account binding mismatch")
    captures = (unit.get("payments") or {}).get("captures") or []
    if len(captures) != 1 or captures[0].get("status") != "COMPLETED":
        raise ValueError("Capture is not completed")
    capture = captures[0]
    amount = capture.get("amount") or {}
    unit_amount = unit.get("amount") or {}
    try:
        captured = Decimal(str(amount["value"])).quantize(Decimal("0.01"))
        ordered = Decimal(str(unit_amount["value"])).quantize(Decimal("0.01"))
    except (KeyError, InvalidOperation, TypeError):
        raise ValueError("Invalid amount from PayPal")
    if not (
        captured == ordered == expected_price
        and amount.get("currency_code") == expected_currency
        and unit_amount.get("currency_code") == expected_currency
    ):
        raise ValueError("PayPal amount/currency mismatch")
    if not verified_payee(unit, capture):
        raise ValueError("PayPal merchant identity mismatch")
    txn_id = capture.get("id", "")
    if not txn_id or len(txn_id) > 255:
        raise ValueError("Missing PayPal capture transaction ID")
    return txn_id


@app.get("/api/paypal/config")
def public_config():
    return jsonify({
        "client_id": PAYPAL_UI["client_id"],
        "currency": PAYPAL_UI["currency"],
        "sandbox": PAYPAL["sandbox"],
        "images": COIN_IMAGES,
    })


@app.get("/api/paypal/prices")
def public_prices():
    return jsonify({format(k, ".2f"): v for k, v in PRICE_MAP.items()})


@app.post("/internal/agreement")
def agreement():
    data, account_id = verify_internal_request("agreement")
    ip = str(data.get("ip_address") or "unknown")[:45]
    agent = str(data.get("user_agent") or "unknown")[:255]
    conn = connect_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM accounts WHERE id=%s", (account_id,))
        if not cur.fetchone():
            return response_error("Account not found", 404)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        cur.execute("""
            INSERT INTO coin_purchase_agreement_log
            (user_id, accepted_at, ip_address, user_agent) VALUES (%s,%s,%s,%s)
        """, (account_id, now, ip, agent))
        agreement_id = cur.lastrowid
        conn.commit()
        return jsonify({"success": True, "agreement_id": agreement_id,
                        "accepted_at": now.isoformat()})
    except mysql.connector.Error:
        conn.rollback()
        log.exception("Agreement database failure")
        return response_error("Agreement unavailable", 503)
    finally:
        conn.close()


@app.post("/internal/orders/create")
def create_order():
    data, account_id = verify_internal_request("create")
    try:
        price = Decimal(str(data["price"])).quantize(Decimal("0.01"))
        agreement_id = int(data["agreement_id"])
    except (KeyError, InvalidOperation, TypeError, ValueError):
        return response_error("Invalid purchase details", 400)
    if price not in PRICE_MAP or agreement_id <= 0:
        return response_error("Unknown package or agreement", 400)

    conn = connect_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM coin_purchase_agreement_log WHERE id=%s AND user_id=%s",
            (agreement_id, account_id),
        )
        if not cur.fetchone():
            return response_error("Agreement not valid for this account", 403)
        token = paypal_token()
        amount = format(price, ".2f")
        order = paypal_request(
            "POST", "/v2/checkout/orders", token,
            data={
                "intent": "CAPTURE",
                "purchase_units": [{
                    "reference_id": str(account_id),
                    "custom_id": str(account_id),
                    "amount": {"currency_code": PAYPAL_UI["currency"], "value": amount},
                }],
            },
            idempotency=str(uuid.uuid4()),
        )
        order_id = order.get("id", "")
        if not ORDER_ID_RE.fullmatch(order_id):
            raise ValueError("PayPal returned an invalid order ID")
        cur.execute("""
            INSERT INTO paypal_pending_orders
              (order_id,account_id,agreement_id,amount,currency,points,created)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (order_id, account_id, agreement_id, amount,
              PAYPAL_UI["currency"], PRICE_MAP[price],
              datetime.now(timezone.utc).replace(tzinfo=None)))
        conn.commit()
        return jsonify({"success": True, "id": order_id})
    except (requests.RequestException, ValueError, KeyError, mysql.connector.Error):
        conn.rollback()
        log.exception("Order creation failure")
        return response_error("Unable to create PayPal order", 502)
    finally:
        conn.close()


@app.post("/internal/orders/capture")
def capture_order():
    data, account_id = verify_internal_request("capture")
    order_id = str(data.get("orderID") or "")
    if not ORDER_ID_RE.fullmatch(order_id):
        return response_error("Invalid order ID", 400)

    conn = connect_db()
    try:
        conn.start_transaction()
        cur = conn.cursor()
        assert_unique_capture_index(cur)
        cur.execute("""
            SELECT amount, currency, points FROM paypal_pending_orders
            WHERE order_id=%s AND account_id=%s FOR UPDATE
        """, (order_id, account_id))
        row = cur.fetchone()
        if not row:
            conn.rollback()
            return response_error("Order does not belong to this account", 403)
        expected_amount = Decimal(str(row[0])).quantize(Decimal("0.01"))
        expected_currency, points = row[1], int(row[2])

        # Read first to recover safely after capture succeeded but local DB commit failed.
        token = paypal_token()
        order = paypal_request("GET", "/v2/checkout/orders/" + order_id, token)
        if order.get("status") != "COMPLETED":
            order = paypal_request(
                "POST", "/v2/checkout/orders/" + order_id + "/capture", token,
                data={},
                idempotency=str(uuid.uuid5(uuid.NAMESPACE_URL, "paypal-capture:" + order_id)),
            )
            # PayPal's capture response can omit fields; fetch the authoritative order.
            order = paypal_request("GET", "/v2/checkout/orders/" + order_id, token)

        txn_id = validate_capture(order, account_id, expected_amount, expected_currency)
        cur.execute("SELECT account_id FROM myaac_paypal WHERE txn_id=%s", (txn_id,))
        previous = cur.fetchone()
        if previous:
            conn.rollback()
            if int(previous[0]) != account_id:
                return response_error("Capture already belongs to another account", 409)
            return jsonify({"success": True, "already_processed": True, "points": points})

        payer_email = str(((order.get("payer") or {}).get("email_address")) or "unknown@paypal.com")[:255]
        cur.execute("""
            INSERT INTO myaac_paypal
              (txn_id,email,account_id,price,currency,points,payer_status,payment_status,created)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (txn_id, payer_email, account_id, expected_amount, expected_currency,
              points, "verified", "Completed", datetime.now(timezone.utc).replace(tzinfo=None)))
        column = "premium_points" if Currency == "points" else "coins_transferable"
        cur.execute(
            "UPDATE accounts SET " + column + " = " + column + " + %s WHERE id=%s",
            (points, account_id),
        )
        if cur.rowcount != 1:
            raise ValueError("Target account missing during capture")
        conn.commit()
        return jsonify({"success": True, "points": points, "currency": Currency})
    except (requests.RequestException, ValueError, KeyError, mysql.connector.Error, RuntimeError):
        conn.rollback()
        log.exception("Capture processing failed for order %s", order_id)
        return response_error(
            "Payment processing needs attention. Do not pay again; retry this order or contact support.",
            503,
        )
    finally:
        conn.close()


@app.post("/paypal-complete")
def disabled_legacy_complete():
    return response_error("Legacy checkout disabled; update coins.php", 410)


@app.post("/api/agreement")
def disabled_legacy_agreement():
    return response_error("Legacy agreement endpoint disabled; update coins.php", 410)


@app.post("/paypal-ipn")
def disabled_legacy_ipn():
    # The old IPN integration cannot securely bind a payment to an order.
    # Do not re-enable without a dedicated, verified migration.
    return response_error("Legacy IPN crediting disabled", 410)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=FLASK_PORT, debug=False)
