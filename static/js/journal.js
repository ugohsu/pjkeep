// journal.js - 仕訳帳一覧

function fmt(n) {
  return Number(n).toLocaleString('ja-JP');
}

function showAlert(msg, type) {
  $('#alert-box').html(
    `<div class="alert alert-${type} alert-dismissible"><button type="button" class="btn-close" data-bs-dismiss="alert"></button>${msg}</div>`
  );
}

function dcLabel(dc) {
  return dc === 'debit' ? '借方' : '貸方';
}

function loadMonths() {
  return $.getJSON('/api/months').then(function(months) {
    const sel = $('#ym-select').empty();
    if (months.length === 0) {
      sel.append('<option value="">（データなし）</option>');
      return;
    }
    months.forEach(function(ym) {
      sel.append(`<option value="${ym}">${ym}</option>`);
    });
  });
}

function loadJournal(ym) {
  $('#journal-list').html('<div class="text-muted p-2">読み込み中...</div>');
  $.getJSON('/api/journal', { ym: ym }).then(function(data) {
    if (data.length === 0) {
      $('#journal-list').html('<div class="text-muted p-3">この月の仕訳はありません。</div>');
      return;
    }
    renderJournal(data);
  }).fail(function() {
    $('#journal-list').html('<div class="text-danger p-2">読み込みに失敗しました</div>');
  });
}

function renderJournal(transactions) {
  // 日付でグループ化して表示
  let html = '<div class="list-group">';
  transactions.forEach(function(tx) {
    const debitLines  = tx.lines.filter(l => l.debit_credit === 'debit');
    const creditLines = tx.lines.filter(l => l.debit_credit === 'credit');
    const totalAmt = debitLines.reduce((s, l) => s + l.amount, 0);

    // 簡易サマリー（借方科目 / 貸方科目）
    const debitNames  = debitLines.map(l => l.account_name).join('・');
    const creditNames = creditLines.map(l => l.account_name).join('・');

    let linesHtml = '<table class="table table-sm mb-0">';
    tx.lines.forEach(function(line) {
      linesHtml += `<tr>
        <td style="width:50px"><span class="badge ${line.debit_credit==='debit'?'bg-primary':'bg-secondary'}">${dcLabel(line.debit_credit)}</span></td>
        <td>${line.account_name}</td>
        <td class="text-end">¥${fmt(line.amount)}</td>
      </tr>`;
    });
    linesHtml += '</table>';

    html += `
      <div class="list-group-item list-group-item-action py-2 px-3" data-tid="${tx.transaction_id}">
        <div class="d-flex justify-content-between align-items-start gap-2">
          <div class="flex-grow-1">
            <div class="d-flex align-items-center gap-2 mb-1">
              <span class="fw-bold">${tx.entry_date}</span>
              <span class="text-muted small">${tx.note || ''}</span>
              <span class="ms-auto text-end small text-muted">${debitNames} / ${creditNames}　¥${fmt(totalAmt)}</span>
            </div>
            <div class="collapse" id="detail-${tx.transaction_id}">
              ${linesHtml}
            </div>
          </div>
          <div class="d-flex gap-1 flex-shrink-0">
            <button class="btn btn-sm btn-outline-secondary btn-toggle"
                    data-bs-toggle="collapse" data-bs-target="#detail-${tx.transaction_id}">詳細</button>
            <button class="btn btn-sm btn-outline-danger btn-delete"
                    data-tid="${tx.transaction_id}">削除</button>
          </div>
        </div>
      </div>`;
  });
  html += '</div>';
  $('#journal-list').html(html);
}

$(document).on('click', '.btn-delete', function() {
  const tid = $(this).data('tid');
  if (!confirm('この取引を削除しますか？\n（この操作は取り消せません）')) return;
  $.ajax({
    url: `/api/journal/transaction/${tid}`,
    method: 'DELETE',
    success: function() {
      const ym = $('#ym-select').val();
      showAlert('削除しました', 'success');
      loadJournal(ym);
    },
    error: function(xhr) {
      showAlert(xhr.responseJSON?.error || '削除に失敗しました', 'danger');
    }
  });
});

$('#ym-select').on('change', function() {
  loadJournal($(this).val());
});

// エクスポート：メインボタン（指定月）
$('#btn-export').on('click', function() {
  const ym = $('#ym-select').val();
  if (!ym) return;
  window.location.href = `/api/export/journal?ym=${ym}`;
});

// エクスポート：指定月のみ（ドロップダウン）
$('#btn-export-month').on('click', function(e) {
  e.preventDefault();
  const ym = $('#ym-select').val();
  if (!ym) return;
  window.location.href = `/api/export/journal?ym=${ym}`;
});

// エクスポート：全仕訳
$('#btn-export-all').on('click', function(e) {
  e.preventDefault();
  window.location.href = '/api/export/journal';
});

// エクスポート：任意の期間（モーダルを開く）
$('#btn-export-period').on('click', function(e) {
  e.preventDefault();
  new bootstrap.Modal('#journalPeriodModal').show();
});

// モーダル内のエクスポートボタン
$('#btn-journal-period-ok').on('click', function() {
  const from = $('#journal-period-from').val();
  const to   = $('#journal-period-to').val();
  if (!from || !to) {
    alert('開始日と終了日を入力してください');
    return;
  }
  if (from > to) {
    alert('開始日は終了日より前の日付を指定してください');
    return;
  }
  bootstrap.Modal.getInstance('#journalPeriodModal').hide();
  window.location.href = `/api/export/journal?from=${from}&to=${to}`;
});

$(function() {
  loadMonths().then(function() {
    const ym = $('#ym-select').val();
    if (ym) loadJournal(ym);
  });
});
