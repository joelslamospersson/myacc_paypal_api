from flask import Flask, request, jsonify, abort, session
import mysql.connector
import requests
import os
import re
from datetime import datetime
from hashlib import sha256
from werkzeug.middleware.proxy_fix import ProxyFix

from config import (
    DB_CONFIG,
    PAYPAL,        # sandbox/live flags & IPN URLs
    PAYPAL_UI,     # JS-SDK client_id & REST secret
    FLASK_PORT,
    ORDER_LOG_DIR,
    AMOUNT_TO_POINTS,
    COIN_IMAGES,
    SECRET_KEY,
    PAYPAL_SHARED_SECRET as SHARED_SECRET
)

app = Flask(__name__)
app.secret_key = SECRET_KEY

# production-safe cookies
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,    # JS can’t read the cookie
    SESSION_COOKIE_SECURE=True,      # only send over HTTPS
    SESSION_COOKIE_SAMESITE='Lax',   # or 'Strict' if you prefer
)

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)
os.makedirs(ORDER_LOG_DIR, exist_ok=True)

def log_order(content):
    try:
        ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        with open(f'{ORDER_LOG_DIR}/order_{ts}.log', 'w') as f:
            f.write(content)
    except Exception as e:
        print(f"[log_order ERROR] {e}")

def is_valid_email(email):
    return re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email) is not None

def verify_token():
    token   = request.headers.get('X-Auth-Token', '')
    expected= sha256(SHARED_SECRET.encode()).hexdigest()
    if token != expected:
        abort(403)

# Auto generate database table for agreement if not exist
def ensure_agreement_table():
    """Create coin_purchase_agreement_log if it doesn’t already exist."""
    try:
        conn   = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS coin_purchase_agreement_log (
            id             INT AUTO_INCREMENT PRIMARY KEY,
            user_id        INT          NOT NULL,
            accepted_at    DATETIME     NOT NULL,
            ip_address     VARCHAR(45)  NOT NULL,
            user_agent     VARCHAR(255) NOT NULL,
            order_id       VARCHAR(255) NULL,
            payer_email    VARCHAR(255) NULL,
            INDEX (user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        conn.commit()
    except Exception as e:
        print(f"[DDL ERROR] {e}")
    finally:
        cursor.close()
        conn.close()
        
# Ensure unique index on txn_id in myaac_paypal
def ensure_paypal_index():
    try:
        conn   = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        # add unique index if missing
        cursor.execute("""
        ALTER TABLE myaac_paypal
          ADD UNIQUE KEY uq_txn_id (txn_id)
        """
        )
        conn.commit()
    except mysql.connector.Error as err:
        # error code 1061 = duplicate key name, ignore
        if err.errno != 1061:
            print(f"[DDL ERROR] {err}")
    finally:
        cursor.close()
        conn.close()

@app.route('/api/paypal/config')
def get_paypal_config():
    return jsonify({
        'client_id': PAYPAL_UI['client_id'],
        'currency':  PAYPAL_UI['currency'],
        'sandbox':   PAYPAL.get('sandbox', True),
        'images':    COIN_IMAGES
    })

# Agreement endpoint
@app.route('/api/agreement', methods=['POST'])
def log_agreement():
    # 1) Verify token header
    token    = request.headers.get('X-Auth-Token')
    expected = sha256(SHARED_SECRET.encode()).hexdigest()
    if token != expected:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    # 2) Extract username
    data = request.get_json(force=True)
    username = data.get('username')
    if not username:
        return jsonify({'success': False, 'error': 'Missing username'}), 400

    # 3) Gather metadata — use ProxyFix so remote_addr is the real client IP
    ip_address  = request.remote_addr or 'unknown'
    user_agent  = request.headers.get('User-Agent', 'unknown')
    accepted_at = datetime.utcnow()

    # 4) Log to DB
    try:
        conn   = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM accounts WHERE name = %s", (username,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'User not found'}), 404

        account_id = row[0]
        cursor.execute("""
          INSERT INTO coin_purchase_agreement_log
            (user_id, accepted_at, ip_address, user_agent)
          VALUES (%s, %s, %s, %s)
        """, (account_id, accepted_at, ip_address, user_agent))
        conn.commit()
        agreement_id = cursor.lastrowid

        # Now returns date:time:hour
        return jsonify({
            'success':      True,
            'agreement_id': agreement_id,
            'accepted_at':  accepted_at.replace(microsecond=0).isoformat()  # e.g. "2025-07-03T19:12:45"
        })

    except Exception:
        return jsonify({'success': False, 'error': 'Database error'}), 500

    finally:
        cursor.close()
        conn.close()

@app.route('/api/paypal/prices')
def get_paypal_prices():
    return jsonify(AMOUNT_TO_POINTS)

@app.route('/paypal-complete', methods=['POST'])
def paypal_complete():
    # 1) debug dump
    try:
        with open(f'{ORDER_LOG_DIR}/debug_{datetime.utcnow():%Y%m%d_%H%M%S}.log', 'w') as f:
            f.write("Headers:\n" + repr(request.headers) + "\n")
            f.write("Body:\n" + request.get_data(as_text=True))
    except:
        pass

    # 2) auth & parse
    verify_token()
    raw = request.get_json(force=True)
    log_order(f"RAW REQUEST: {raw}\n")

    order_id     = raw.get('orderID')
    username     = raw.get('username')
    payer_email  = raw.get('payer_email', 'unknown@paypal.com')
    agreement_id = raw.get('agreement_id')
    if not (order_id and username and agreement_id):
        return jsonify({'error': 'Missing orderID, username, or agreement_id'}), 400

    # 3) fetch PayPal order
    base = 'https://api-m.sandbox.paypal.com' if PAYPAL.get('sandbox',True) else 'https://api-m.paypal.com'
    auth = (PAYPAL_UI['client_id'], PAYPAL_UI['secret'])
    tkn = requests.post(f"{base}/v1/oauth2/token", auth=auth, data={'grant_type':'client_credentials'})
    if tkn.status_code!=200:
        log_order(f"AUTH ERROR: {tkn.text}\n")
        return jsonify({'error':'PayPal auth failed'}), 500
    access_token = tkn.json()['access_token']

    ord_res = requests.get(
        f"{base}/v2/checkout/orders/{order_id}",
        headers={'Authorization':f'Bearer {access_token}'}
    )
    if ord_res.status_code!=200:
        log_order(f"ORDER FETCH ERROR: {ord_res.text}\n")
        return jsonify({'error':'Failed to fetch order'}), 400
    order = ord_res.json()

    # 4) basic PayPal sanity checks
    if order.get('status') not in ('COMPLETED','CAPTURED'):
        log_order(f"ORDER NOT COMPLETED: {order}\n")
        return jsonify({'error':'Order not completed'}), 400

    pu = order['purchase_units'][0]

    # 4a) custom_id → user binding
    if pu.get('custom_id') != username:
        log_order(f"USER MISMATCH: expected {username}, got {pu.get('custom_id')}\n")
        return jsonify({'error':'User mismatch'}), 403

    # 4b) currency enforcement
    if pu['amount']['currency_code'] != PAYPAL_UI['currency']:
        log_order(f"BAD CURRENCY: {pu['amount']}\n")
        return jsonify({'error':'Invalid currency'}), 400

    # 4c) drill into capture
    caps = pu.get('payments',{}).get('captures',[])
    if not caps or caps[0].get('status')!='COMPLETED':
        log_order(f"CAPTURE MISSING/FAILED: {order}\n")
        return jsonify({'error':'Capture not completed'}), 400

    txn_id     = caps[0]['id']
    paid_value = float(caps[0]['amount']['value'])
    points     = AMOUNT_TO_POINTS.get(paid_value)
    if points is None:
        log_order(f"BAD AMOUNT {paid_value}: {order}\n")
        return jsonify({'error':'Invalid amount'}), 400

    # 5) open DB and do idempotent check
    try:
        conn   = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM myaac_paypal WHERE txn_id=%s", (txn_id,))
        if cursor.fetchone()[0] > 0:
            # already done
            return jsonify({'success': True, 'message':'Already processed'}), 200

        # 6) credit user
        cursor.execute("SELECT id FROM accounts WHERE name=%s", (username,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'error':'User not found'}), 404
        account_id = row[0]

        cursor.execute(
            "UPDATE accounts SET coins_transferable=coins_transferable+%s WHERE id=%s",
            (points, account_id)
        )
        cursor.execute("""
            INSERT INTO myaac_paypal
              (txn_id,email,account_id,price,currency,points,payer_status,payment_status,created)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            txn_id, payer_email, account_id, paid_value,
            PAYPAL_UI['currency'], points,
            'verified','Completed', datetime.utcnow()
        ))
        conn.commit()

        return jsonify({'success':True, 'points':points}), 200

    except Exception as e:
        log_order(f"DB ERROR: {e}\n")
        return jsonify({'error':str(e)}), 500

    finally:
        try: cursor.close(); conn.close()
        except: pass

@app.route('/paypal-ipn', methods=['POST'])
def paypal_ipn():
    ipn_data = request.form.to_dict()
    verify_payload = {'cmd': '_notify-validate'}
    verify_payload.update(ipn_data)

    paypal_url = PAYPAL['sandbox_url'] if PAYPAL['sandbox'] else PAYPAL['live_url']
    verify_response = requests.post(paypal_url, data=verify_payload)

    log_data = f"IPN RECEIVED:\n{ipn_data}\nVerification: {verify_response.text}\n"

    if verify_response.text != 'VERIFIED':
        log_order(log_data + "ERROR: IPN not verified.\n")
        return "Invalid IPN", 400

    txn_id = ipn_data.get('txn_id')
    payment_status = ipn_data.get('payment_status')
    payer_status = ipn_data.get('payer_status', '')
    receiver_email = ipn_data.get('receiver_email')
    custom_username = ipn_data.get('custom')
    try:
        mc_gross = float(ipn_data.get('mc_gross', '0.00'))
    except ValueError:
        return "Invalid amount", 400
    currency = ipn_data.get('mc_currency', PAYPAL_UI['currency'])

    if not txn_id or not is_valid_email(receiver_email) or not custom_username:
        log_order(log_data + "ERROR: Missing fields.\n")
        return "Invalid data", 400

    if payment_status != "Completed" or receiver_email != PAYPAL['receiver_email']:
        log_order(log_data + "ERROR: Unauthorized or incomplete.\n")
        return "Unauthorized", 403

    points = next((v for k, v in AMOUNT_TO_POINTS.items() if abs(k - mc_gross) < 0.01), None)
    if not points:
        log_order(log_data + f"ERROR: Unknown amount: {mc_gross}\n")
        return "Unknown amount", 400

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM accounts WHERE name = %s", (custom_username,))
        result = cursor.fetchone()
        if not result:
            log_order(log_data + f"ERROR: User '{custom_username}' not found.\n")
            return "User not found", 404

        account_id = result[0]

        cursor.execute("UPDATE accounts SET coins_transferable = coins_transferable + %s WHERE id = %s", (points, account_id))
        cursor.execute("""
            INSERT INTO myaac_paypal (txn_id, email, account_id, price, currency, points, payer_status, payment_status, created)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            txn_id, receiver_email, account_id, mc_gross, currency, points, payer_status, payment_status, datetime.utcnow()
        ))

        conn.commit()
        log_order(log_data + f"SUCCESS: {points} points added to '{custom_username}'.\n")
        return "OK", 200

    except Exception as e:
        log_order(log_data + f"ERROR: {e}\n")
        return "Server error", 500

    finally:
        try:
            if conn.is_connected():
                cursor.close()
                conn.close()
        except:
            pass

if __name__ == '__main__':
    # ensure the table is created before we start
    ensure_agreement_table()
    ensure_paypal_index()
    app.run(host='127.0.0.1', port=FLASK_PORT)
