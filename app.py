from flask import Flask, request, jsonify, abort
import mysql.connector
import requests
import os
import re
from datetime import datetime
from config import DB_CONFIG, PAYPAL, PAYPAL_UI, FLASK_PORT, ORDER_LOG_DIR, AMOUNT_TO_POINTS
from hashlib import sha256
from werkzeug.middleware.proxy_fix import ProxyFix

from config import PAYPAL_SHARED_SECRET as SHARED_SECRET

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)
os.makedirs(ORDER_LOG_DIR, exist_ok=True)

def log_order(content):
    try:
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        with open(f'{ORDER_LOG_DIR}/order_{timestamp}.log', 'w') as f:
            f.write(content)
    except Exception as e:
        print(f"[log_order ERROR] {e}")

def is_valid_email(email):
    return re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email) is not None

def verify_token():
    token = request.headers.get('X-Auth-Token')
    expected = sha256(SHARED_SECRET.encode()).hexdigest()
    if token != expected:
        abort(403, description='Unauthorized')

@app.route('/api/paypal/config')
def get_paypal_config():
    return jsonify({
        'client_id': PAYPAL_UI['client_id'],
        'currency': PAYPAL_UI['currency'],
        'sandbox': PAYPAL_UI.get('sandbox', True)
    })

@app.route('/api/paypal/prices')
def get_paypal_prices():
    return jsonify(AMOUNT_TO_POINTS)

@app.route('/paypal-complete', methods=['POST'])
def paypal_complete():
    verify_token()
    raw_data = request.data.decode(errors='ignore')
    log_order(f"RAW REQUEST: {raw_data}\n")

    try:
        data = request.get_json(force=True)
        username = data.get('username')
        payer_email = data.get('payer_email', 'unknown@paypal.com')
        amount = float(data.get('amount') or 0)
        points = AMOUNT_TO_POINTS.get(amount)
    except Exception as e:
        return jsonify({'error': f'Invalid input: {str(e)}'}), 400

    if not username or not points:
        return jsonify({'error': 'Missing username or amount'}), 400

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM accounts WHERE name = %s", (username,))
        result = cursor.fetchone()
        if not result:
            return jsonify({'error': 'User not found'}), 404

        account_id = result[0]

        cursor.execute("UPDATE accounts SET coins_transferable = coins_transferable + %s WHERE id = %s", (points, account_id))
        cursor.execute("""
            INSERT INTO myaac_paypal (txn_id, email, account_id, price, currency, points, payer_status, payment_status, created)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            'web_checkout',
            payer_email,
            account_id,
            amount,
            PAYPAL_UI['currency'],
            points,
            'verified',
            'Completed',
            datetime.utcnow()
        ))

        conn.commit()
        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

    finally:
        try:
            if conn.is_connected():
                cursor.close()
                conn.close()
        except:
            pass

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
    app.run(host='127.0.0.1', port=FLASK_PORT)
