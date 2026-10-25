# MyAAC PayPal Checkout — Security Hardening

**BREAKING MIGRATION. DO NOT DEPLOY DIRECTLY TO PRODUCTION.**

The new flow authenticates the customer with a MyAAC PHP session and CSRF token,
uses a short-lived HMAC to call Flask from PHP over loopback, and creates/captures
Orders v2 server-side. Every order is bound to an immutable account ID, agreement,
fixed server-side amount, currency and the intended PayPal merchant. Account credits
require a verified PayPal capture and a unique transaction ID in MySQL.

## Mandatory migration checklist

1. Back up the live MyAAC database and current PHP, Python and Nginx files.
2. Copy .env.example to a PRIVATE server-only .env (outside public web access);
   generate independent random SECRET_KEY and PAYPAL_INTERNAL_SECRET values
   (at least 32 characters each). Python and PHP must use the same HMAC secret.
   Rotate any formerly exposed live secrets.
3. Configure DB credentials, PayPal client ID/secret, merchant ID (preferred) or
   receiver email, currency and correct points/coins field. Use PAYPAL_SANDBOX=true
   for initial tests.
4. Apply migrations/001_checkout_tables.sql to the verified database. Confirm
   myaac_paypal(txn_id) has a single-column UNIQUE index; CREATE TABLE IF NOT
   EXISTS never upgrades an existing ledger. Resolve duplicates before adding.
5. Install dependencies (pip install -r requirements.txt) and PHP cURL.
   Deploy app.py, config.py, coins.php and Nginx locations AS ONE CHANGE.
   Never expose /internal/* publicly; Gunicorn binds to 127.0.0.1:5000.
6. Confirm this MyAAC version uses PHP sessions and routes authenticated POST
   /index.php?subtopic=coins&paypal_action=... requests to coins.php.
7. Offline checks: python -m py_compile app.py config.py;
   python -m unittest discover -s tests -v;
   php -l system/pages/coins.php; nginx -t after incorporating Nginx changes.
8. Sandbox acceptance tests: each package, duplicate capture, different account,
   wrong currency/amount/merchant, invalid agreement, failed PayPal API requests,
   DB outage after capture with safe retry, missing unique index, concurrent calls.
9. Deploy LIVE only after all tests pass and a rollback/reconciliation plan exists.

Run Gunicorn: gunicorn --workers 3 --bind 127.0.0.1:5000 app:app

## Remaining work / limitations

Old /paypal-complete, /api/agreement and /paypal-ipn endpoints deliberately return
410. If IPN is used in production, the migration must first introduce verified
webhooks and reconciliation; this branch does NOT process IPN. Refunds, disputes and
chargebacks are not automated. No live PayPal tests were performed.

The previously tracked .env was removed from the branch but may still exist in
Git history. Deleting a file in a new commit does not remove historical secrets.
Python requirements have bounded version ranges rather than a production lockfile.
