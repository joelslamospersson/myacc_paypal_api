<?php
defined('MYAAC') or die('Direct access not allowed!');
$title = 'Buy Coins';
if (!$logged || !isset($account_logged)) {
    header('Location: /index.php');
    exit;
}
if (session_status() !== PHP_SESSION_ACTIVE) {
    session_start();
}
$accountId = (int)$account_logged->getId();
if ($accountId <= 0) {
    http_response_code(403);
    exit('Not authenticated');
}
if (empty($_SESSION['paypal_csrf'])) {
    $_SESSION['paypal_csrf'] = bin2hex(random_bytes(32));
}
$csrf = $_SESSION['paypal_csrf'];

/**
 * Read the same private server-side secret as the local Flask service.
 * Do not ever render this secret (or any hash of it) into HTML.
 */
function paypalInternalSecret(): string {
    $secret = getenv('PAYPAL_INTERNAL_SECRET');
    if (is_string($secret) && strlen($secret) >= 32) {
        return $secret;
    }
    $path = __DIR__ . '/../../paypal/.env';
    if (!is_readable($path)) {
        throw new RuntimeException('PayPal server configuration missing');
    }
    $settings = parse_ini_file($path, false, INI_SCANNER_RAW);
    if (!is_array($settings) || empty($settings['PAYPAL_INTERNAL_SECRET']) ||
        strlen($settings['PAYPAL_INTERNAL_SECRET']) < 32) {
        throw new RuntimeException('PayPal internal signing secret missing');
    }
    return trim($settings['PAYPAL_INTERNAL_SECRET'], "\"'");
}

function paypalInternalCall(string $action, array $payload): array {
    $json = json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);
    $timestamp = (string)time();
    $signature = hash_hmac('sha256', $timestamp . '.' . $action . '.' . $json, paypalInternalSecret());
    $paths = array(
        'agreement' => '/internal/agreement',
        'create' => '/internal/orders/create',
        'capture' => '/internal/orders/capture',
    );
    if (!isset($paths[$action])) {
        throw new RuntimeException('Invalid action');
    }
    if (!function_exists('curl_init')) {
        throw new RuntimeException('PHP curl extension is required');
    }
    $ch = curl_init('http://127.0.0.1:5000' . $paths[$action]);
    curl_setopt_array($ch, array(
        CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => $json,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_CONNECTTIMEOUT => 3,
        CURLOPT_TIMEOUT => 35,
        CURLOPT_HTTPHEADER => array(
            'Content-Type: application/json',
            'X-Paypal-Timestamp: ' . $timestamp,
            'X-Paypal-Signature: ' . $signature,
        ),
    ));
    $response = curl_exec($ch);
    $status = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $err = curl_error($ch);
    curl_close($ch);
    if ($response === false || $status === 0) {
        error_log('PayPal backend unavailable: ' . $err);
        return array(503, array('success' => false, 'error' => 'Payment service unavailable'));
    }
    $decoded = json_decode((string)$response, true);
    if (!is_array($decoded)) {
        return array(502, array('success' => false, 'error' => 'Unexpected payment service response'));
    }
    return array($status, $decoded);
}

if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_GET['paypal_action'])) {
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    $provided = $_SERVER['HTTP_X_CSRF_TOKEN'] ?? '';
    if (!is_string($provided) || !hash_equals($csrf, $provided)) {
        http_response_code(403);
        echo json_encode(array('success' => false, 'error' => 'Invalid session token'));
        exit;
    }
    $body = json_decode(file_get_contents('php://input'), true);
    if (!is_array($body)) {
        http_response_code(400);
        echo json_encode(array('success' => false, 'error' => 'Invalid JSON'));
        exit;
    }

    $action = (string)$_GET['paypal_action'];
    $payload = array('account_id' => $accountId);
    if ($action === 'agreement') {
        $payload['ip_address'] = $_SERVER['REMOTE_ADDR'] ?? 'unknown';
        $payload['user_agent'] = $_SERVER['HTTP_USER_AGENT'] ?? 'unknown';
    } elseif ($action === 'create') {
        $payload['price'] = $body['price'] ?? '';
        $payload['agreement_id'] = $body['agreement_id'] ?? '';
    } elseif ($action === 'capture') {
        $payload['orderID'] = $body['orderID'] ?? '';
    } else {
        http_response_code(404);
        echo json_encode(array('success' => false, 'error' => 'Unknown action'));
        exit;
    }

    try {
        list($status, $result) = paypalInternalCall($action, $payload);
        http_response_code($status);
        echo json_encode($result, JSON_UNESCAPED_SLASHES);
    } catch (Throwable $e) {
        error_log('Payment integration error: ' . $e->getMessage());
        http_response_code(503);
        echo json_encode(array('success' => false, 'error' => 'Checkout temporarily unavailable'));
    }
    exit;
}
?>
<div class="container my-5" style="max-width:850px;margin:auto;padding:20px">
    <h1><?= htmlspecialchars($title, ENT_QUOTES, 'UTF-8') ?></h1>
    <p>Choose your package and pay securely using PayPal.</p>
    <p id="paypal-message" role="status"></p>
    <div id="packages" style="display:flex;gap:12px;flex-wrap:wrap;margin:20px 0"></div>
    <div id="paypal-button-container"></div>
    <div id="agreement-panel" style="border:1px solid #888;padding:18px;margin:18px 0">
        <h3>Purchase agreement</h3>
        <p>These purchases provide digital in-game currency. Payments are processed by PayPal.
        Refunds and statutory consumer rights are governed by applicable law and PayPal's terms.</p>
        <label><input type="checkbox" id="agree-checkbox"> I agree to the purchase terms.</label>
        <button type="button" id="agree-button" disabled>Accept and continue</button>
    </div>
</div>
<script>
(function() {
    'use strict';
    const csrf = <?= json_encode($csrf, JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT) ?>;
    const agreementStoreKey = 'paypalAgreementAccount-' + <?= json_encode((string)$accountId) ?>;
    const message = document.getElementById('paypal-message');
    const packageArea = document.getElementById('packages');
    const paypalArea = document.getElementById('paypal-button-container');
    const agreePanel = document.getElementById('agreement-panel');
    const agreeButton = document.getElementById('agree-button');
    const agreeCheckbox = document.getElementById('agree-checkbox');
    let agreementId = Number(localStorage.getItem(agreementStoreKey)) || null;
    let selectedPrice = null;
    let paypalConfig = null;
    let paypalLoaded = false;

    function show(messageText) { message.textContent = messageText; }
    async function callApi(action, payload) {
        const response = await fetch('/index.php?subtopic=coins&paypal_action=' + encodeURIComponent(action), {
            method: 'POST',
            credentials: 'same-origin',
            headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
            body: JSON.stringify(payload)
        });
        let result;
        try { result = await response.json(); }
        catch (_) { throw new Error('The payment service returned an invalid response'); }
        if (!response.ok || !result.success) {
            throw new Error(result.error || 'Payment could not be processed');
        }
        return result;
    }

    agreeCheckbox.addEventListener('change', function() {
        agreeButton.disabled = !agreeCheckbox.checked;
    });
    agreeButton.addEventListener('click', async function() {
        agreeButton.disabled = true;
        try {
            const result = await callApi('agreement', {});
            agreementId = result.agreement_id;
            localStorage.setItem(agreementStoreKey, String(agreementId));
            agreePanel.hidden = true;
            show('Agreement recorded. Please select a package.');
        } catch (err) {
            show(err.message);
            agreeButton.disabled = false;
        }
    });

    function renderPackages(prices, images, currency) {
        packageArea.replaceChildren();
        Object.entries(prices).forEach(function(entry) {
            const price = entry[0], points = entry[1];
            const button = document.createElement('button');
            button.type = 'button';
            button.style.cssText = 'cursor:pointer;border:1px solid #888;border-radius:6px;padding:12px;min-width:130px';
            const img = document.createElement('img');
            img.src = images[price] || '/images/coins_default.png';
            img.alt = '';
            img.width = 65;
            img.height = 65;
            button.appendChild(img);
            const label = document.createElement('div');
            label.textContent = price + ' ' + currency + ' - ' + points + ' coins';
            button.appendChild(label);
            button.addEventListener('click', function() {
                if (!agreementId) { show('Accept the purchase terms first.'); return; }
                selectedPrice = price;
                paypalArea.replaceChildren();
                show('Selected package: ' + price + ' ' + currency);
                if (paypalLoaded) renderButton();
            });
            packageArea.appendChild(button);
        });
    }
    function renderButton() {
        if (!selectedPrice || !agreementId || !window.paypal) return;
        window.paypal.Buttons({
            createOrder: async function() {
                const result = await callApi('create', {price: selectedPrice, agreement_id: agreementId});
                return result.id;
            },
            onApprove: async function(data) {
                try {
                    const result = await callApi('capture', {orderID: data.orderID});
                    show(result.already_processed
                        ? 'Purchase already credited to your account.'
                        : 'Purchase successful: ' + result.points + ' coins added.');
                } catch (err) {
                    show(err.message + ' If you paid, contact support rather than paying a second time.');
                }
            },
            onError: function(err) {
                console.error('PayPal checkout error', err);
                show('The payment could not be completed. Please try again or contact support.');
            }
        }).render('#paypal-button-container');
    }

    if (agreementId) agreePanel.hidden = true;
    Promise.all([
        fetch('/api/paypal/config', {credentials:'same-origin'}).then(function(r){if(!r.ok)throw new Error('Config unavailable');return r.json();}),
        fetch('/api/paypal/prices', {credentials:'same-origin'}).then(function(r){if(!r.ok)throw new Error('Prices unavailable');return r.json();})
    ]).then(function(results) {
        paypalConfig = results[0];
        renderPackages(results[1], paypalConfig.images || {}, paypalConfig.currency);
        const sdk = document.createElement('script');
        sdk.src = 'https://www.paypal.com/sdk/js?client-id=' +
            encodeURIComponent(paypalConfig.client_id) +
            '&currency=' + encodeURIComponent(paypalConfig.currency) +
            '&intent=capture';
        sdk.onload = function() { paypalLoaded = true; show('Select a package to continue.'); };
        sdk.onerror = function() { show('PayPal checkout is temporarily unavailable.'); };
        document.head.appendChild(sdk);
    }).catch(function(err) { show('Unable to load PayPal checkout: ' + err.message); });
})();
</script>
