-- Apply to a backed-up MyAAC database before deploying checkout.
CREATE TABLE IF NOT EXISTS coin_purchase_agreement_log (
 id INT AUTO_INCREMENT PRIMARY KEY, user_id INT NOT NULL, accepted_at DATETIME NOT NULL,
 ip_address VARCHAR(45) NOT NULL, user_agent VARCHAR(255) NOT NULL,
 order_id VARCHAR(255) NULL, payer_email VARCHAR(255) NULL, INDEX(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS myaac_paypal (
 id INT AUTO_INCREMENT PRIMARY KEY, txn_id VARCHAR(255) NOT NULL,
 email VARCHAR(255) NOT NULL, account_id INT NOT NULL, price DECIMAL(10,2) NOT NULL,
 currency VARCHAR(10) NOT NULL, points INT NOT NULL, payer_status VARCHAR(50) DEFAULT 'verified',
 payment_status VARCHAR(50) DEFAULT 'Completed', created DATETIME NOT NULL,
 UNIQUE KEY uq_txn_id(txn_id), INDEX(account_id), INDEX(created)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS paypal_pending_orders (
 order_id VARCHAR(64) PRIMARY KEY, account_id INT NOT NULL,
 agreement_id INT NOT NULL, amount DECIMAL(10,2) NOT NULL,
 currency CHAR(3) NOT NULL, points INT NOT NULL, created DATETIME NOT NULL,
 INDEX(account_id), INDEX(created)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- WARNING: Existing myaac_paypal tables are NOT altered by CREATE TABLE IF NOT EXISTS.
-- SELECT txn_id, COUNT(*) FROM myaac_paypal GROUP BY txn_id HAVING COUNT(*) > 1;
-- SHOW INDEX FROM myaac_paypal;
-- After resolving duplicates, if the unique txn_id index is missing:
-- ALTER TABLE myaac_paypal ADD UNIQUE KEY uq_txn_id(txn_id);
