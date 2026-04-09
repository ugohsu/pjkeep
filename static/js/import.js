/* バッチインポート */

const SAMPLE = {
  "transactions": [
    {
      "date": "2026-03-15",
      "note": "Amazon 事務用品",
      "_comment": "Amazonの購入。事業費と判断。",
      "_confidence": 0.9,
      "lines": [
        { "account_code": "operating", "debit_credit": "debit",  "amount": 3300 },
        { "account_code": "payable",   "debit_credit": "credit", "amount": 3300 }
      ]
    }
  ]
};

const DC_JA = { debit: '借方', credit: '貸方' };
const ELEM_JA = { assets: '資産', liabilities: '負債', equity: '純資産', revenues: '収益', expenses: '費用' };

let previewData = null;  // { transactions: [...], errors: [...] }

// ---- ファイル選択 ----
$('#json-file').on('change', function () {
  const file = this.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => $('#json-input').val(e.target.result);
  reader.readAsText(file, 'utf-8');
});

// ---- サンプル表示 ----
$('#btn-sample').on('click', function (e) {
  e.preventDefault();
  $('#json-input').val(JSON.stringify(SAMPLE, null, 2));
});

// ---- クリア ----
$('#btn-clear').on('click', function () {
  $('#json-input').val('');
  $('#step-preview').hide();
  $('#alert-box').html('');
  previewData = null;
  $('#json-file').val('');
});

// ---- プレビュー ----
$('#btn-preview').on('click', function () {
  $('#alert-box').html('');
  let payload;
  try {
    payload = JSON.parse($('#json-input').val());
  } catch (e) {
    showAlert('danger', 'JSON のパースに失敗しました: ' + e.message);
    return;
  }

  $.ajax({
    url: '/api/import/preview',
    method: 'POST',
    contentType: 'application/json',
    data: JSON.stringify(payload),
    success: function (res) {
      previewData = res;
      renderPreview(res);
    },
    error: function (xhr) {
      const msg = xhr.responseJSON?.error || xhr.responseText;
      showAlert('danger', 'エラー: ' + msg);
    }
  });
});

// ---- プレビュー描画 ----
function renderPreview(res) {
  const txns = res.transactions || [];
  const errors = res.errors || [];

  // エラーをインデックス別に整理
  const errorsByIdx = {};
  errors.forEach(e => {
    if (!errorsByIdx[e.index]) errorsByIdx[e.index] = [];
    errorsByIdx[e.index].push(e.message);
  });

  const validCount = txns.filter(t => t.valid).length;
  const invalidCount = txns.length - validCount;
  let summaryHtml = `${txns.length} 件中 <strong class="text-success">${validCount} 件</strong> が有効`;
  if (invalidCount > 0) summaryHtml += `、<strong class="text-danger">${invalidCount} 件</strong> にエラー`;
  $('#preview-summary').html(summaryHtml);

  let html = '';
  txns.forEach(function (txn, i) {
    const conf = txn._confidence;
    const lowConf = typeof conf === 'number' && conf < 0.8;
    const dup = txn._duplicate;
    const dupProb = dup ? dup.probability : 0;
    const highDup = dupProb >= 0.8;
    const midDup  = dupProb >= 0.5 && dupProb < 0.8;

    let cardClass, headerClass;
    if (!txn.valid) {
      cardClass = 'border-danger'; headerClass = 'bg-danger-subtle';
    } else if (highDup) {
      cardClass = 'border-warning'; headerClass = 'bg-warning-subtle';
    } else if (midDup) {
      cardClass = 'border-warning border-opacity-50'; headerClass = 'bg-warning-subtle bg-opacity-50';
    } else if (lowConf) {
      cardClass = 'border-warning'; headerClass = 'bg-warning-subtle';
    } else {
      cardClass = ''; headerClass = 'bg-light';
    }

    const checked  = (txn.valid && !highDup) ? 'checked' : '';
    const disabled = txn.valid ? '' : 'disabled';

    // 借方・貸方合計
    let debitTotal = 0, creditTotal = 0;
    (txn.lines || []).forEach(l => {
      if (l.debit_credit === 'debit') debitTotal += l.amount;
      else creditTotal += l.amount;
    });

    // ヘッダー行
    html += `<div class="card mb-2 ${cardClass}" data-idx="${i}">`;
    html += `<div class="card-header ${headerClass} d-flex align-items-center gap-2 py-2">`;
    html += `<input type="checkbox" class="form-check-input txn-check" ${checked} ${disabled} data-idx="${i}">`;
    html += `<span class="fw-bold">#${i + 1}</span>`;
    html += `<span>${escHtml(txn.date)}</span>`;
    if (txn.note) html += `<span class="text-muted">${escHtml(txn.note)}</span>`;
    if (lowConf) html += `<span class="badge bg-warning text-dark ms-1">確信度 ${(conf * 100).toFixed(0)}%</span>`;
    if (highDup) html += `<span class="badge bg-warning text-dark ms-1">⚠ 重複の可能性 ${(dupProb * 100).toFixed(0)}%</span>`;
    else if (midDup) html += `<span class="badge bg-warning text-dark ms-1" style="opacity:.7">重複の可能性 ${(dupProb * 100).toFixed(0)}%</span>`;
    if (!txn.valid) html += `<span class="badge bg-danger ms-1">エラー</span>`;
    html += `</div>`;  // card-header

    html += `<div class="card-body py-2">`;

    // コメント
    if (txn._comment) {
      html += `<p class="small text-muted mb-2"><em>${escHtml(txn._comment)}</em></p>`;
    }

    // 仕訳行テーブル
    html += `<table class="table table-sm table-bordered mb-1" style="max-width:600px">`;
    html += `<thead class="table-light"><tr><th>借/貸</th><th>勘定科目</th><th class="text-end">金額</th></tr></thead>`;
    html += `<tbody>`;
    (txn.lines || []).forEach(function (line) {
      const dcBadge = line.debit_credit === 'debit'
        ? '<span class="badge bg-primary">借方</span>'
        : '<span class="badge bg-secondary">貸方</span>';
      html += `<tr>`;
      html += `<td>${dcBadge}</td>`;
      html += `<td><code>${escHtml(line.account_code)}</code> ${escHtml(line.account_name)}</td>`;
      html += `<td class="text-end">${line.amount.toLocaleString()}</td>`;
      html += `</tr>`;
    });
    html += `</tbody>`;
    html += `<tfoot class="table-light"><tr>`;
    html += `<td colspan="2" class="text-end small text-muted">借方合計 / 貸方合計</td>`;
    const balOk = debitTotal === creditTotal;
    html += `<td class="text-end small fw-bold ${balOk ? '' : 'text-danger'}">`;
    html += `${debitTotal.toLocaleString()} / ${creditTotal.toLocaleString()}`;
    html += `</td></tr></tfoot>`;
    html += `</table>`;

    // 重複警告パネル
    if (dup && dupProb >= 0.5) {
      const m = dup.matched;
      const diffLabel = dup.date_diff_days === 0 ? '同日' : `日付差 ${dup.date_diff_days} 日`;
      html += `<div class="alert alert-warning py-2 px-3 mb-2 small">`;
      html += `<strong>⚠ 類似仕訳が既存データに存在します（${diffLabel}）</strong><br>`;
      html += `${escHtml(m.date)}`;
      if (m.note) html += `&nbsp;${escHtml(m.note)}`;
      html += `<br>`;
      const dupLines = (m.lines || []).map(l =>
        `${l.debit_credit === 'debit' ? '借方' : '貸方'} ${escHtml(l.account_name)} ${l.amount.toLocaleString()}`
      ).join('　／　');
      html += `<span class="text-muted">${dupLines}</span>`;
      html += `</div>`;
    }

    // エラー一覧
    const errs = errorsByIdx[i] || [];
    if (errs.length > 0) {
      html += `<ul class="mb-0 small text-danger">`;
      errs.forEach(msg => { html += `<li>${escHtml(msg)}</li>`; });
      html += `</ul>`;
    }

    html += `</div></div>`;  // card-body / card
  });

  $('#preview-list').html(html);
  $('#step-preview').show();
}

// ---- 全選択 / 全解除 ----
$('#btn-check-all').on('click', function () {
  $('.txn-check:not([disabled])').prop('checked', true);
});
$('#btn-uncheck-all').on('click', function () {
  $('.txn-check').prop('checked', false);
});

// ---- コミット ----
$('#btn-commit').on('click', function () {
  if (!previewData) return;

  const approved = [];
  $('.txn-check:checked').each(function () {
    approved.push(parseInt($(this).data('idx')));
  });

  if (approved.length === 0) {
    showAlert('warning', 'インポートする仕訳が選択されていません。');
    return;
  }

  if (!confirm(`${approved.length} 件の仕訳をインポートします。よろしいですか？`)) return;

  $.ajax({
    url: '/api/import/commit',
    method: 'POST',
    contentType: 'application/json',
    data: JSON.stringify({
      transactions: previewData.transactions,
      approved_indices: approved
    }),
    success: function (res) {
      showAlert('success', `${res.committed} 件の仕訳をインポートしました。`);
      $('#step-preview').hide();
      $('#json-input').val('');
      $('#json-file').val('');
      previewData = null;
    },
    error: function (xhr) {
      const msg = xhr.responseJSON?.error || xhr.responseText;
      showAlert('danger', 'エラー: ' + msg);
    }
  });
});

// ---- ユーティリティ ----
function showAlert(type, msg) {
  $('#alert-box').html(
    `<div class="alert alert-${type} alert-dismissible fade show" role="alert">
      ${escHtml(msg)}
      <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    </div>`
  );
  window.scrollTo(0, 0);
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
