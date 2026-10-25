"""Offline, no live PayPal or database calls."""
import hmac
import json
import os
import sys
import time
import unittest
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update({
 "PAYPAL_INTERNAL_SECRET":"unit-test-internal-secret-only-1234567890123456",
 "SECRET_KEY":"unit-test-flask-secret-only-123456789012345678",
 "DB_USER":"test_user","DB_PASSWORD":"test_password","DB_NAME":"test_db",
 "PAYPAL_CLIENT_ID":"sandbox-client","PAYPAL_CLIENT_SECRET":"sandbox-secret",
 "PAYPAL_MERCHANT_ID":"MERCHANT-TEST-123","PAYPAL_SANDBOX":"true"
})
import app as checkout

def completed(account=42, price="5.00", currency="EUR", merchant="MERCHANT-TEST-123"):
 return {"status":"COMPLETED","purchase_units":[{
  "custom_id":str(account),"amount":{"value":price,"currency_code":currency},
  "payee":{"merchant_id":merchant},
  "payments":{"captures":[{"id":"CAPTURE-TEST-123","status":"COMPLETED",
     "amount":{"value":price,"currency_code":currency}}]}
 }]}

class SecurityTests(unittest.TestCase):
 def setUp(self): self.client=checkout.app.test_client()
 def signed(self,action,path,payload,ts=None,remote="127.0.0.1"):
  raw=json.dumps(payload,separators=(",",":")).encode()
  timestamp=str(ts if ts is not None else int(time.time()))
  sig=hmac.new(checkout.PAYPAL_INTERNAL_SECRET.encode(),
      timestamp.encode()+b"."+action.encode()+b"."+raw,sha256).hexdigest()
  return self.client.post(path,data=raw,content_type="application/json",
      headers={"X-Paypal-Timestamp":timestamp,"X-Paypal-Signature":sig},
      environ_overrides={"REMOTE_ADDR":remote})
 def test_unsigned_rejected(self):
  self.assertEqual(self.client.post("/internal/orders/create",json={"account_id":42}).status_code,403)
 def test_stale_signature_rejected(self):
  self.assertEqual(self.signed("create","/internal/orders/create",{"account_id":42},
                   ts=int(time.time())-500).status_code,403)
 def test_not_loopback_rejected(self):
  self.assertEqual(self.signed("create","/internal/orders/create",{"account_id":42},
                   remote="203.0.113.2").status_code,403)
 def test_invalid_package_rejected(self):
  self.assertEqual(self.signed("create","/internal/orders/create",
                   {"account_id":42,"price":"0.01","agreement_id":1}).status_code,400)
 def test_valid_capture(self):
  self.assertEqual(checkout.validate_capture(completed(),42,Decimal("5.00"),"EUR"),"CAPTURE-TEST-123")
 def test_wrong_account_rejected(self):
  with self.assertRaises(ValueError):
   checkout.validate_capture(completed(account=99),42,Decimal("5.00"),"EUR")
 def test_wrong_price_rejected(self):
  with self.assertRaises(ValueError):
   checkout.validate_capture(completed(price="1.00"),42,Decimal("5.00"),"EUR")
 def test_wrong_currency_rejected(self):
  with self.assertRaises(ValueError):
   checkout.validate_capture(completed(currency="USD"),42,Decimal("5.00"),"EUR")
 def test_wrong_merchant_rejected(self):
  with self.assertRaises(ValueError):
   checkout.validate_capture(completed(merchant="WRONG"),42,Decimal("5.00"),"EUR")
 def test_legacy_crediting_disabled(self):
  for path in ("/paypal-complete","/paypal-ipn","/api/agreement"):
   self.assertEqual(self.client.post(path).status_code,410)
if __name__=="__main__":unittest.main()
