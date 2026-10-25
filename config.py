"""Production configuration. No real credentials belong in Git."""
import os
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

def required(name):
    value = os.getenv(name, "").strip()
    if not value or value.lower().startswith(("replace_", "example_", "changeme", "your_")):
        raise RuntimeError("Required environment variable is missing: " + name)
    return value

PAYPAL_INTERNAL_SECRET = required("PAYPAL_INTERNAL_SECRET")
if len(PAYPAL_INTERNAL_SECRET) < 32:
    raise RuntimeError("PAYPAL_INTERNAL_SECRET must contain at least 32 characters")
SECRET_KEY = required("SECRET_KEY")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": required("DB_USER"),
    "password": required("DB_PASSWORD"),
    "database": required("DB_NAME"),
    "connection_timeout": 5,
}

PAYPAL = {
    "sandbox": os.getenv("PAYPAL_SANDBOX", "true").lower() in ("1", "true", "yes"),
    "merchant_id": os.getenv("PAYPAL_MERCHANT_ID", "").strip(),
    "receiver_email": os.getenv("PAYPAL_RECEIVER_EMAIL", "").strip(),
}
if not PAYPAL["merchant_id"] and not PAYPAL["receiver_email"]:
    raise RuntimeError("Set PAYPAL_MERCHANT_ID or PAYPAL_RECEIVER_EMAIL")
PAYPAL_UI = {
    "client_id": required("PAYPAL_CLIENT_ID"),
    "secret": required("PAYPAL_CLIENT_SECRET"),
    "currency": os.getenv("PAYPAL_CURRENCY", "EUR").upper(),
}
if len(PAYPAL_UI["currency"]) != 3 or not PAYPAL_UI["currency"].isalpha():
    raise RuntimeError("PAYPAL_CURRENCY must be an ISO 4217 currency code")

FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
Currency = os.getenv("MYAAC_CURRENCY_FIELD", "points").lower()
if Currency not in ("points", "coins"):
    raise RuntimeError("MYAAC_CURRENCY_FIELD must be points or coins")

AMOUNT_TO_POINTS = {
    Decimal("1.00"): 100, Decimal("5.00"): 1000, Decimal("10.00"): 2200,
    Decimal("20.00"): 4800, Decimal("40.00"): 10000, Decimal("60.00"): 16000,
}
COIN_IMAGES = {
    "1.00": "/images/coins_100.png",
    "5.00": "/images/coins_1000.png",
    "10.00": "/images/coins_2200.png",
    "20.00": "/images/coins_4800.png",
    "40.00": "/images/coins_10000.png",
    "60.00": "/images/coins_16000.png",
}
