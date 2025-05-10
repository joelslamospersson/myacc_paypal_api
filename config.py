# config.py
from dotenv import load_dotenv
import os

# Load .env from the same directory
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

PAYPAL_SHARED_SECRET = os.getenv("PAYPAL_SHARED_SECRET")

# Database settings
DB_CONFIG = {
    'host': 'localhost',
    'user': 'database_user',
    'password': 'database_password',
    'database': 'database'
}

# PayPal settings
PAYPAL = {
    'sandbox': False,
    'sandbox_url': 'https://ipnpb.sandbox.paypal.com/cgi-bin/webscr',
    'live_url': 'https://ipnpb.paypal.com/cgi-bin/webscr',
    #'receiver_email': 'sandbox@business.example.com' # sandbox
    'receiver_email': 'live_email@example.com' # live
}

# Flask settings
FLASK_PORT = 5000

# Amount to points mapping
PAYPAL_UI = {
    'enabled': True,
    #'client_id': 'example_token', # Sandbox application
    'client_id': 'example_token', # Live application
    'currency': 'EUR'
}

# Set your prices
AMOUNT_TO_POINTS = {
    1.00: 45,
    10.00: 100,
    15.00: 165,
    20.00: 240,
    25.00: 325,
    30.00: 420,
    50.00: 560
}

# Log settings
ORDER_LOG_DIR = 'order_logs'

# IPN listener endpoint (used for documentation, not dynamic)
PAYPAL_IPN_URL = 'https://yourdomain.com/paypal-ipn'
