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
    'user': 'youruser',
    'password': 'yourdbpass',
    'database': 'yourdb'
}

# PayPal settings
PAYPAL = {
    'sandbox': False, # Enable to true for sandbox testing
    # Do not change, paypal official links
    'sandbox_url': 'https://ipnpb.sandbox.paypal.com/cgi-bin/webscr',
    'live_url': 'https://ipnpb.paypal.com/cgi-bin/webscr',
    
    # Sandbox account, used to testing
    #'receiver_email': 'example@business.example.com' # sandbox
    
    # Live, change if live payments
    'receiver_email': 'your@paypal.com' # live
}

# Flask settings
FLASK_PORT = 5000

# Amount to points mapping
PAYPAL_UI = {
    'enabled': True,
    # Sandbox application, required!
    #'secret': 'Your-Sandbox-Secret', # Sandbox
    #'client_id': 'Your-Sandbox-ID', # Sandbox application
    
    # Live application, required!
    'secret': 'Your-Live-Secret', # Live 
    'client_id': 'Your-Live-ID', # Live application
    'currency': 'EUR'
}

# Change this if you want other payment for coins
AMOUNT_TO_POINTS = {
    1.00: 100,
    5.00: 1000,
    10.00: 2200,
    20.00: 4800,
    40.00: 10000,
    60.00: 16000
}

# Log settings
ORDER_LOG_DIR = 'order_logs'

# IPN listener endpoint (used for documentation, not dynamic)
PAYPAL_IPN_URL = 'https://yourserverdomain.com/paypal-ipn'
