<?php
defined('MYAAC') or die('Direct access not allowed!');
$title = 'Purchase History';

if (!$logged || !isset($account_logged)) {
    header('Location: /index.php');
    exit;
}

global $SQL;
$userId  = (int) $account_logged->getId();
$perPage = 25;

// sanitize & compute pagination
$page   = isset($_GET['page']) ? (int) $_GET['page'] : 1;
if ($page < 1) { $page = 1; }
$offset = ($page - 1) * $perPage;

// 1) total count
$totalStmt = $SQL->query(
    "SELECT COUNT(*) AS total
     FROM myaac_paypal
     WHERE account_id = {$userId}"
);
$total = 0;
if ($totalStmt instanceof PDOStatement) {
    $row    = $totalStmt->fetch(PDO::FETCH_ASSOC);
    $total  = isset($row['total']) ? (int) $row['total'] : 0;
}
$totalPages = (int) ceil($total / $perPage);

// 2) fetch only this page
$sql = "
  SELECT
    txn_id     AS order_id,
    DATE_FORMAT(created, '%Y-%m-%d %H:%i') AS purchased_at,
    price,
    currency,
    points
  FROM myaac_paypal
  WHERE account_id = {$userId}
  ORDER BY created DESC
  LIMIT {$perPage} OFFSET {$offset}
";
$stmt   = $SQL->query($sql);
$orders = [];
if ($stmt instanceof PDOStatement) {
    $orders = $stmt->fetchAll(PDO::FETCH_ASSOC);
}
?>

<!-- BEGIN table -->
<div class="TableContainer">
  <div class="CaptionContainer">
    <div class="CaptionInnerContainer">
      <span class="CaptionEdgeLeftTop"></span>
      <span class="CaptionEdgeRightTop"></span>
      <span class="CaptionBorderTop"></span>
      <span class="CaptionVerticalLeft"></span>
      <span class="CaptionVerticalRight"></span>
      <div class="Text"><?= $title ?></div>
    </div>
  </div>

  <table class="TableContent" cellpadding="4" cellspacing="1">
    <tr class="LabelH">
      <td style="width:150px;"><b>Date</b></td>
      <td style="width:200px;"><b>Order ID</b></td>
      <td style="width:100px;"><b>Amount</b></td>
      <td style="width:80px;"><b>Coins</b></td>
    </tr>

    <?php if (count($orders) > 0): ?>
      <?php foreach ($orders as $i => $row): ?>
        <?php $cls = ($i % 2 === 0 ? 'Even' : 'Odd'); ?>
        <tr class="<?= $cls ?>">
          <td><?= htmlspecialchars($row['purchased_at'], ENT_QUOTES) ?></td>
          <td><?= htmlspecialchars($row['order_id'],    ENT_QUOTES) ?></td>
          <td>
            <?= number_format((float)$row['price'], 2) ?>
            <?= htmlspecialchars($row['currency'],    ENT_QUOTES) ?>
          </td>
          <td><?= (int)$row['points'] ?></td>
        </tr>
      <?php endforeach; ?>
    <?php else: ?>
      <tr class="Odd">
        <td colspan="4" style="text-align:center;">
          You haven’t made any purchases yet.
        </td>
      </tr>
    <?php endif; ?>
  </table>

  <div class="TableFooter">
    <div class="FooterInnerContainer">
      <span class="FooterVerticalLeft"></span>
      <span class="FooterVerticalRight"></span>
      <span class="FooterEdgeLeftBottom"></span>
      <span class="FooterEdgeRightBottom"></span>
      <span class="FooterBorderBottom"></span>
    </div>
  </div>
</div>
<!-- END table -->

<?php if ($totalPages > 1): ?>
  <!-- Pagination -->
  <div class="PageNavigation">
    <?php if ($page > 1): ?>
      <a class="PageNavigationPrevious" href="?subtopic=purchase_history&amp;page=<?= $page-1 ?>">
        &laquo; Previous
      </a>
    <?php endif; ?>

    <span class="PageNavigationLabel">
      Page <?= $page ?> of <?= $totalPages ?>
    </span>

    <?php if ($page < $totalPages): ?>
      <a class="PageNavigationNext" href="?subtopic=purchase_history&amp;page=<?= $page+1 ?>">
        Next &raquo;
      </a>
    <?php endif; ?>
  </div>
<?php endif; ?>
