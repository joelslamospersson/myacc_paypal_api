# config.py
from dotenv import load_dotenv
import os

# 1) Load .env from the same directory
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

# 2) .env Secrets + fails if missing
PAYPAL_SHARED_SECRET = os.getenv("PAYPAL_SHARED_SECRET")
if not PAYPAL_SHARED_SECRET:
    raise RuntimeError("PAYPAL_SHARED_SECRET is not set in your .env!")

SECRET_KEY           = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is not set in your .env!")

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
    'receiver_email': 'example@hotmail.com' # live
}

# Flask settings
FLASK_PORT = 5000

# Amount to points mapping
PAYPAL_UI = {
    'enabled': True,
    # Sandbox application, required!
    #'secret': '', # Sandbox
    #'client_id': '', # Sandbox application
    
    # Live application, required!
    'secret': '', # Live 
    'client_id': '', # Live application
    'currency': 'EUR'
}

# Amount → points
AMOUNT_TO_POINTS = {
    1.00: 100,
    5.00: 1000,
    10.00: 2200,
    20.00: 4800,
    40.00: 10000,
    60.00: 16000
}

# Add your image URLs here (keys must match the AMOUNT_TO_POINTS keys)
COIN_IMAGES = {
    "1.00":  "/images/coins_100.png",
    "5.00":  "/images/coins_1000.png",
    "10.00": "/images/coins_2200.png",
    "20.00": "/images/coins_4800.png",
    "40.00": "/images/coins_10000.png",
    "60.00": "/images/coins_16000.png",
}

# Log settings
ORDER_LOG_DIR = 'order_logs'

# IPN listener endpoint (used for documentation, not dynamic)
PAYPAL_IPN_URL = 'https://yourdomain.com/paypal-ipn'
