<?php
// Put this file at: /var/www/html/system/pages/coins.php
defined('MYAAC') or die('Direct access not allowed!');
$title = 'Buy Coins';

if (!$logged || !isset($account_logged)) {
    header('Location: /index.php');
    exit;
}

$username = $account_logged->getName();

// Load secret from .env
$envFile = __DIR__ . '/../../paypal/.env';
if (file_exists($envFile)) {
    foreach (file($envFile) as $line) {
        if (strpos($line, '=') !== false) {
            putenv(trim($line));
        }
    }
}
$token_hash = hash('sha256', getenv('PAYPAL_SHARED_SECRET'));
?>

<h1>Buy Coins</h1>
<p>Select a package and pay with PayPal:</p>

<select id="point-package" class="form-control" style="max-width: 300px; margin-bottom: 20px;"></select>

<div id="paypal-button-container" style="min-height: 60px;"></div>

<script>
const token = <?= json_encode($token_hash) ?>;
const username = <?= json_encode($username) ?>;

Promise.all([
    fetch('/api/paypal/config').then(res => res.json()),
    fetch('/api/paypal/prices').then(res => res.json())
]).then(([config, prices]) => {
    const select = document.getElementById('point-package');
    Object.entries(prices).forEach(([price, points]) => {
        const option = document.createElement('option');
        option.value = price;
        option.textContent = `${price} ${config.currency} - ${points} coins`;
        select.appendChild(option);
    });

    const script = document.createElement('script');
    script.src = `https://www.paypal.com/sdk/js?client-id=${config.client_id}&currency=${config.currency}`;
    script.onload = () => {
        paypal.Buttons({
            createOrder: function(data, actions) {
                const amount = select.value;
                return actions.order.create({
                    purchase_units: [{ amount: { value: amount } }]
                });
            },
            onApprove: function(data, actions) {
                const amount = select.value;
                return actions.order.capture().then(function(details) {
                    const payer_email = details.payer.email_address || 'unknown@paypal.com';

                    fetch('/paypal-complete', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-Auth-Token': token
                        },
                        body: JSON.stringify({ username, amount, payer_email })
                    })
                    .then(res => res.json())
                    .then(data => {
                        if (data.success) {
                            alert('✅ Coins added to your account!');
                            location.reload();
                        } else {
                            alert('❌ Error: ' + data.error);
                        }
                    });
                });
            }
        }).render('#paypal-button-container');
    };
    document.head.appendChild(script);
}).catch(err => {
    console.error('Error loading PayPal or prices:', err);
    document.getElementById('paypal-button-container').innerText = 'Failed to load PayPal.';
});
</script>
