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

### Running the server ( Development )
```
python app.py
```

### Running the server ( Production )
```
gunicorn --workers 3 --bind 127.0.0.1:5000 app:app
```
