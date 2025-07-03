# myacc_paypal_api
Paypal API written with Python for MyAcc ( Live + Sandbox )

## 🔧 Setup Instructions

### 1. Install Dependencies
```bash
sudo apt update
sudo apt install -y python3-pip python3-venv nginx
```

### 2. Assuming your app will live at /var/www/html/paypal:
```
sudo mkdir -p /var/www/html/paypal
cd /var/www/html/paypal
python3 -m venv venv
source venv/bin/activate
```

### 3. Create a requirements.txt file with:
```
flask
requests
mysql-connector-python
gunicorn
```

### 4. Then install:
```
pip install -r requirements.txt
```

### 5. Give correct permissions
```
sudo chmod 600 /var/www/html/paypal/.env
sudo chown www-data:www-data /var/www/html/paypal/.env
sudo chmod 775 /var/www/html/paypal/.env
```

### 6. Add rate limiting, required for server block
```
# /etc/nginx/nginx.conf
http {
    # … your other http settings …

    # ─── RATE LIMITING ZONE ─────────────────────────────────
    # 5 requests per second per IP, 10 MB of state
    limit_req_zone $binary_remote_addr zone=apilimit:10m rate=5r/s;

    # include your sites-available/*.conf etc.
}
```

### Running the server ( Development )
```
python app.py
```

### Running the server ( Production )
```
gunicorn --workers 3 --bind 127.0.0.1:5000 app:app
```

# Webhooks and paypal setup
```
Use the default application already provided on your paypal account
Take the client id and secret id, paste it into the config, swap out your email to the correct one,
boot the script and sit back, relax

# For Live and Sandbox
This API does not use any webhooks anymore, so you do not have to edit the application, do the same for live/sandbox,
Use your paypal email for live, use your sandbox buisiness account for sandbox and pay using a personal sandbox account

You find both at the same spot, at developer paypal,
Simply press the button up right corner between sandbox and live mode.
```
