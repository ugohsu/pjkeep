// journal.js - 仕訳帳一覧

let accountsList = [];
let currentTransactions = [];
let editingTid = null;

function fmt(n) {
  return Number(n).toLocaleString('ja-JP');
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function showAlert(msg, type) {
  $('#alert-box').html(
    `<div class="alert alert-${type} alert-dismissible"><button type="button" class="btn-close" data-bs-dismiss="alert"></button>${msg}</div>`
  );
}

function dcLabel(dc) {
  return dc === 'debit' ? '借方' : '貸方';
}

function loadAccounts() {
  return $.getJSON('/api/accounts').then(function(data) {
    accountsList = data;
  });
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
  currentTransactions = transactions;

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
        <td>${escHtml(line.account_name)}</td>
        <td class="text-end">¥${fmt(line.amount)}</td>
      </tr>`;
    });
    linesHtml += '</table>';

    html += `
      <div class="list-group-item list-group-item-action py-2 px-3" data-tid="${tx.transaction_id}">
        <div class="d-flex justify-content-between align-items-start gap-2">
          <div class="flex-grow-1">
            <div class="d-flex align-items-center gap-2 mb-1">
              <span class="fw-bold">${escHtml(tx.entry_date)}</span>
              <span class="text-muted small">${escHtml(tx.note || '')}</span>
              <span class="ms-auto text-end small text-muted">${escHtml(debitNames)} / ${escHtml(creditNames)}　¥${fmt(totalAmt)}</span>
            </div>
            <div class="collapse" id="detail-${tx.transaction_id}">
              ${linesHtml}
            </div>
          </div>
          <div class="d-flex gap-1 flex-shrink-0">
            <button class="btn btn-sm btn-outline-secondary btn-toggle"
                    data-bs-toggle="collapse" data-bs-target="#detail-${tx.transaction_id}">詳細</button>
            <button class="btn btn-sm btn-outline-primary btn-edit"
                    data-tid="${tx.transaction_id}">編集</button>
            <button class="btn btn-sm btn-outline-danger btn-delete"
                    data-tid="${tx.transaction_id}">削除</button>
          </div>
        </div>
      </div>`;
  });
  html += '</div>';
  $('#journal-list').html(html);
}

// ---- 編集モーダル ----

function accountOptions(selectedId) {
  return accountsList.map(function(a) {
    const sel = a.id === selectedId ? 'selected' : '';
    return `<option value="${a.id}" ${sel}>${escHtml(a.name)}</option>`;
  }).join('');
}

function addEditRow(dc, accountId, amount) {
  const row = $(`
    <tr>
      <td>
        <select class="form-select form-select-sm edit-dc">
          <option value="debit"  ${dc === 'debit'  ? 'selected' : ''}>借方</option>
          <option value="credit" ${dc === 'credit' ? 'selected' : ''}>貸方</option>
        </select>
      </td>
      <td>
        <select class="form-select form-select-sm edit-account">${accountOptions(accountId)}</select>
      </td>
      <td>
        <input type="number" class="form-control form-control-sm edit-amount" min="1" step="1" value="${amount || ''}">
      </td>
      <td>
        <button type="button" class="btn btn-sm btn-outline-danger edit-remove-row">×</button>
      </td>
    </tr>
  `);
  $('#edit-lines-body').append(row);
}

function updateEditBalance() {
  let debit = 0, credit = 0;
  $('#edit-lines-body tr').each(function() {
    const dc  = $(this).find('.edit-dc').val();
    const amt = parseInt($(this).find('.edit-amount').val(), 10);
    if (!isNaN(amt) && amt > 0) {
      if (dc === 'debit') debit += amt;
      else credit += amt;
    }
  });
  if (debit === 0 && credit === 0) {
    $('#edit-balance').html('');
    return;
  }
  const ok  = debit > 0 && debit === credit;
  const cls = ok ? 'text-success' : 'text-danger';
  $('#edit-balance').html(
    `借方合計 / 貸方合計: <span class="${cls} fw-bold">${fmt(debit)} / ${fmt(credit)}</span>`
  );
}

function openEditModal(tx) {
  editingTid = tx.transaction_id;
  $('#edit-date').val(tx.entry_date);
  $('#edit-note').val(tx.note || '');
  $('#edit-lines-body').empty();
  tx.lines.forEach(function(line) {
    addEditRow(line.debit_credit, line.account_id, line.amount);
  });
  updateEditBalance();
  new bootstrap.Modal('#editTxnModal').show();
}

$(document).on('click', '.btn-edit', function() {
  const tid = $(this).data('tid');
  const tx  = currentTransactions.find(t => t.transaction_id === tid);
  if (tx) openEditModal(tx);
});

$(document).on('change input', '#edit-lines-body .edit-dc, #edit-lines-body .edit-amount', updateEditBalance);

$(document).on('click', '.edit-remove-row', function() {
  if ($('#edit-lines-body tr').length <= 2) {
    alert('最低2行必要です');
    return;
  }
  $(this).closest('tr').remove();
  updateEditBalance();
});

$('#edit-add-row').on('click', function() {
  addEditRow('debit', accountsList[0]?.id, '');
  updateEditBalance();
});

$('#btn-edit-save').on('click', function() {
  const entry_date = $('#edit-date').val();
  const note       = $('#edit-note').val().trim();
  if (!entry_date) { alert('取引日を入力してください'); return; }

  const lines = [];
  let valid = true;
  $('#edit-lines-body tr').each(function() {
    const dc         = $(this).find('.edit-dc').val();
    const account_id = parseInt($(this).find('.edit-account').val(), 10);
    const amount     = parseInt($(this).find('.edit-amount').val(), 10);
    if (isNaN(amount) || amount <= 0) { alert('金額を正しく入力してください'); valid = false; return false; }
    lines.push({ account_id, debit_credit: dc, amount });
  });
  if (!valid) return;

  $.ajax({
    url: `/api/journal/transaction/${editingTid}`,
    method: 'PUT',
    contentType: 'application/json',
    data: JSON.stringify({ entry_date, note, lines }),
    success: function() {
      bootstrap.Modal.getInstance('#editTxnModal').hide();
      const ym = $('#ym-select').val();
      showAlert('更新しました', 'success');
      loadJournal(ym);
    },
    error: function(xhr) {
      alert(xhr.responseJSON?.error || '更新に失敗しました');
    }
  });
});

// ---- 削除 ----

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
  loadAccounts();
  loadMonths().then(function() {
    const ym = $('#ym-select').val();
    if (ym) loadJournal(ym);
  });
});
