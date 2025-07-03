<?php
defined('MYAAC') or die('Direct access not allowed!');
$title = 'Buy Coins';

if (! $logged || ! isset($account_logged)) {
    header('Location: /index.php');
    exit;
}

$username = $account_logged->getName();

// Load .env secrets
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
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title><?= htmlspecialchars($title) ?></title>
  <link rel="stylesheet" href="/css/bootstrap.min.css">
  <style>
    /* Agreement badge */
    #agreement-status {
      position: absolute;
      top: 20px; right: 20px;
      padding: 6px 14px;
      font-size: .95em;
      color: #fff;
      background: #c03;
      border-radius: 4px;
      z-index: 1;
    }
    #agreement-status.accepted { background: #3a6; }

    /* Package buttons */
    #packages {
      display: flex;
      flex-wrap: wrap;
      gap: 16px;
      justify-content: center;
      margin-bottom: 24px;
    }
    .package-btn {
      width: 140px;
      text-align: center;
      border: 2px solid #7f5a2a;
      background: #fdf9f3;
      border-radius: 8px;
      padding: 12px 8px;
      cursor: pointer;
      transition: background .2s, border-color .2s;
      font-family: Tahoma, sans-serif;
    }
    .package-btn.selected {
      background: #7f5a2a;
      border-color: #503d20;
      color: #fff;
    }
    .package-btn img {
      max-width: 80px;
      display: block;
      margin: 0 auto 8px;
    }

    /* PayPal container */
    #paypal-button-container {
      min-height: 60px;
      opacity: 0.5;
      pointer-events: none;
    }

    /* Overlay */
    .terms-overlay {
      position: fixed; top:0; left:0;
      width:100vw; height:100vh;
      background: rgba(0,0,0,0.7);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 10000;
    }
    .terms-box {
      background: #fdf9f3;
      border:1px solid #b08b57;
      border-radius:8px;
      width:90%; max-width:800px;
      max-height:85vh; overflow-y:auto;
      box-shadow:0 4px 20px rgba(0,0,0,0.3);
      font-family: Tahoma, sans-serif;
      color:#333;
    }
    .terms-header {
      background:#7f5a2a; color:#fff;
      padding:12px 20px;
      font-size:1.4em;
      border-top-left-radius:6px;
      border-top-right-radius:6px;
    }
    .terms-content {
      padding:20px; line-height:1.5em; font-size:0.95em;
    }
    .terms-content h3 {
      margin-top:1.2em; color:#7f5a2a;
      border-bottom:1px solid #b08b57; padding-bottom:4px;
    }
    .terms-footer {
      padding:12px 20px; text-align:right;
      border-top:1px solid #e0d6c8;
    }
    .terms-btn {
      background:#7f5a2a; color:#fff; border:none;
      padding:8px 18px; font-size:1em;
      border-radius:4px; cursor:pointer;
    }
    .terms-btn:disabled { opacity:0.6; cursor:not-allowed; }
  </style>
</head>
<body>
  <div class="container my-5" style="position:relative;">
    <h1><?= htmlspecialchars($title) ?></h1>
    <div id="agreement-status">Agreement: Not accepted</div>

    <p>Select a package and pay with PayPal:</p>
    <div id="packages"></div>
    <div id="paypal-button-container"></div>
  </div>

  <script>
  (function(){
    const token    = <?= json_encode($token_hash) ?>;
    const username = <?= json_encode($username) ?>;

    // Load stored consent
    let agreementId   = localStorage.getItem('coinsAgreementId');
    let agreementTime = localStorage.getItem('coinsAgreementTime');

    let paypalCfg, pricesGlobal;
    let selectedPrice, paypalRendered = false;

    // Update badge with date/time
    function markAgreed(){
      const badge = document.getElementById('agreement-status');
      const ts = agreementTime
        ? new Date(agreementTime).toLocaleString()
        : '';
      badge.textContent = `Agreement: Accepted ${ts}`;
      badge.classList.add('accepted');
      document.getElementById('paypal-button-container')
              .style.cssText = 'opacity:1;pointer-events:auto;';
    }

    // Build package buttons
    function initPackages(prices, images){
      pricesGlobal = prices;
      const container = document.getElementById('packages');
      container.innerHTML = '';
      Object.entries(prices).forEach(([price, pts])=>{
        const btn = document.createElement('div');
        btn.className = 'package-btn';
        btn.dataset.price = price;
        btn.innerHTML = `
          <img src="${images[price]||'/images/coins_default.png'}" alt="">
          <div>${price} ${paypalCfg.currency}</div>
          <small>${pts} coins</small>`;
        btn.addEventListener('click', ()=>{
          if (!agreementId) return;
          container.querySelectorAll('.package-btn')
                   .forEach(b=>b.classList.remove('selected'));
          btn.classList.add('selected');
          selectedPrice  = price;
          paypalRendered = false;
          document.getElementById('paypal-button-container').innerHTML = '';
          renderPayPalButton();
        });
        container.appendChild(btn);
      });
    }

    // Render PayPal button
    function renderPayPalButton(){
	  if (!selectedPrice || paypalRendered) return;
	  paypalRendered = true;

	  paypal.Buttons({
		// 1) createOrder MUST return the purchase_units array
		createOrder: (data, actions) => {
		  return actions.order.create({
			purchase_units: [{
			  amount: {
				// ensure it’s a string or number with two decimals
				value: selectedPrice
			  },
			  custom_id: username
			}]
		  });
		},

		// 2) onApprove should capture once, using the details passed in
		onApprove: (data, actions) => {
		  return actions.order.capture().then(details => {
			const payer_email = details.payer.email_address || 'unknown@paypal.com';

			return fetch('/paypal-complete', {
			  method: 'POST',
			  headers: {
				'Content-Type': 'application/json',
				'X-Auth-Token': token
			  },
			  body: JSON.stringify({
				orderID:      data.orderID,
				username:     username,
				payer_email:  payer_email,
				agreement_id: agreementId
			  })
			})
			.then(r => r.json())
			.then(js => {
			  if (js.success) {
				alert(`✅ Purchase complete! ${js.points || ''} points added.`);
				location.reload();
			  } else {
				alert(`❌ Error: ${js.error}`);
			  }
			});
		  });
		}

	  }).render('#paypal-button-container');
	}

    // Show agreement overlay
    function showTermsOverlay(){
      const ov = document.createElement('div'); ov.className='terms-overlay';
      const bx = document.createElement('div'); bx.className='terms-box';
      bx.innerHTML = `
        <div class="terms-header">Virtual Legal Binding Agreement</div>
        <div class="terms-content">
          <p><strong>Product:</strong> MMO-RPG Virtual Coins (OTServer).</p>
          <h3>1. Offer & Acceptance</h3>
          <p>Seller offers to sell virtual coins; Buyer accepts by clicking “I Agree”.</p>
          <h3>2. Consideration</h3>
          <p>Payment via PayPal is valid consideration in exchange for in-game coins.</p>
          <h3>3. Intent</h3>
          <p>Both parties intend this clickwrap to be legally binding.</p>
          <h3>4. Legality & Capacity</h3>
          <p>Agreement is lawful. Buyer represents age ≥18 and capacity to contract.</p>
          <h3>5. Delivery & Refunds</h3>
          <ul>
            <li>Coins delivered instantly upon payment capture.</li>
            <li>All sales final. No refunds or chargebacks once transaction completes.</li>
          </ul>
          <h3>6. Governing Law</h3>
          <p>Governing law: [Your Jurisdiction]. Disputes in its courts.</p>
          <p><em>This electronic agreement is as binding as a handwritten contract.</em></p>
        </div>
        <div class="terms-footer">
          <button class="terms-btn" id="agree-btn">I Agree</button>
        </div>`;
      ov.appendChild(bx);
      document.body.appendChild(ov);

      bx.querySelector('#agree-btn').addEventListener('click', async e=>{
        const btn = e.target;
        btn.disabled = true;
        btn.textContent = 'Recording…';
        try {
          const res = await fetch('/api/agreement', {
            method:'POST',
            headers:{
              'Content-Type':'application/json',
              'X-Auth-Token': token
            },
            body: JSON.stringify({ username })
          });
          if (!res.ok) throw new Error('Status '+res.status);
          const js = await res.json();
          if (!js.success) throw new Error(js.error||'');
          agreementId   = js.agreement_id;
          agreementTime = js.accepted_at;
          localStorage.setItem('coinsAgreementId', agreementId);
          localStorage.setItem('coinsAgreementTime', agreementTime);

          document.body.removeChild(ov);
          markAgreed();
          initPackages(pricesGlobal, paypalCfg.images);
        } catch(err) {
          console.error(err);
          alert('Error recording agreement:\n'+err.message);
          btn.disabled = false;
          btn.textContent = 'I Agree';
        }
      });
    }

    // Load config & prices
    Promise.all([
      fetch('/api/paypal/config').then(r=>r.json()),
      fetch('/api/paypal/prices').then(r=>r.json())
    ]).then(([cfg, prices])=>{
      paypalCfg    = cfg;
      pricesGlobal = prices;

      initPackages(prices, cfg.images);
      if (agreementId) markAgreed();

      // load PayPal SDK
      const sdk = document.createElement('script');
      sdk.src = `https://www.paypal.com/sdk/js?client-id=${cfg.client_id}&currency=${cfg.currency}`;
      sdk.onload = ()=> {
        if (agreementId) {
          // auto-select first package to render
          const first = document.querySelector('#packages .package-btn');
          if (first) first.click();
        }
      };
      document.head.appendChild(sdk);
    }).catch(err=>{
      console.error('Load error',err);
      document.getElementById('paypal-button-container')
              .innerText = 'Failed to load payment options.';
    });

    window.addEventListener('DOMContentLoaded', ()=>{
      if (!agreementId) showTermsOverlay();
    });
  })();
  </script>
</body>
</html>
