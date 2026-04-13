// ledger.js - 総勘定元帳

let accountsList = [];
let selectedAccountId = null;
let editingTid = null;

const ELEMENT_LABELS = {
  assets:      '資産',
  liabilities: '負債',
  equity:      '純資産',
  revenues:    '収益',
  expenses:    '費用',
};
const ELEMENT_ORDER = ['assets', 'liabilities', 'equity', 'revenues', 'expenses'];

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

// ---- 科目ツリー（サイドバー） ----

function loadAccounts() {
  return $.getJSON('/api/accounts').then(function(data) {
    accountsList = data;
    renderSidebar(data);
    renderMobileSelect(data);
  });
}

function renderSidebar(accounts) {
  const grouped = {};
  accounts.forEach(function(a) {
    if (!grouped[a.element]) grouped[a.element] = [];
    grouped[a.element].push(a);
  });

  let html = '';
  ELEMENT_ORDER.forEach(function(el) {
    if (!grouped[el] || grouped[el].length === 0) return;
    html += `<div class="text-muted small px-2 pt-2 pb-1 fw-bold">${escHtml(ELEMENT_LABELS[el] || el)}</div>`;
    grouped[el].forEach(function(a) {
      html += `<div class="px-2 py-1 rounded account-item ${a.id === selectedAccountId ? 'bg-primary text-white' : ''}"
                   style="cursor:pointer;font-size:.9rem" data-id="${a.id}">${escHtml(a.name)}</div>`;
    });
  });
  $('#account-tree').html(html || '<div class="text-muted small p-2">科目がありません</div>');
}

function renderMobileSelect(accounts) {
  const sel = $('#account-select-mobile');
  sel.empty().append('<option value="">科目を選択してください</option>');
  const grouped = {};
  accounts.forEach(function(a) {
    if (!grouped[a.element]) grouped[a.element] = [];
    grouped[a.element].push(a);
  });
  ELEMENT_ORDER.forEach(function(el) {
    if (!grouped[el] || grouped[el].length === 0) return;
    const og = $(`<optgroup label="${escHtml(ELEMENT_LABELS[el] || el)}">`);
    grouped[el].forEach(function(a) {
      og.append(`<option value="${a.id}">${escHtml(a.name)}</option>`);
    });
    sel.append(og);
  });
  if (selectedAccountId) sel.val(selectedAccountId);
}

function selectAccount(accountId) {
  selectedAccountId = accountId;

  // サイドバーのハイライト更新
  $('#account-tree .account-item').each(function() {
    const isSelected = parseInt($(this).data('id'), 10) === accountId;
    $(this).toggleClass('bg-primary text-white', isSelected);
  });

  // モバイルセレクト同期
  $('#account-select-mobile').val(accountId);

  const acc = accountsList.find(a => a.id === accountId);
  $('#selected-account-name').text(acc ? acc.name : '');
  $('#btn-export').prop('disabled', false);

  loadLedger();
}

// ---- 元帳データ取得・表示 ----

function loadLedger() {
  if (!selectedAccountId) return;
  const from = $('#filter-from').val();
  const to   = $('#filter-to').val();

  const params = { account_id: selectedAccountId };
  if (from) params.from = from;
  if (to)   params.to   = to;

  $('#ledger-area').html('<div class="text-muted p-3">読み込み中...</div>');

  $.getJSON('/api/ledger', params).then(function(data) {
    renderLedger(data);
  }).fail(function(xhr) {
    $('#ledger-area').html(
      `<div class="text-danger p-3">${escHtml(xhr.responseJSON?.error || '読み込みに失敗しました')}</div>`
    );
  });
}

function renderLedger(data) {
  const entries = data.entries;
  const ob      = data.opening_balance;

  let html = '<div class="table-responsive"><table class="table table-sm table-bordered table-hover mb-0">';
  html += `<thead class="table-light">
    <tr>
      <th style="width:100px">日付</th>
      <th>備考</th>
      <th class="text-end" style="width:110px">借方</th>
      <th class="text-end" style="width:110px">貸方</th>
      <th class="text-end" style="width:120px">残高</th>
      <th class="d-none d-md-table-cell" style="width:120px">相手科目</th>
    </tr>
  </thead><tbody>`;

  // 前期残高行
  if (data.from_date && ob !== 0) {
    html += `<tr class="table-secondary">
      <td>${escHtml(data.from_date)}</td>
      <td class="text-muted fst-italic">（前期残高）</td>
      <td></td><td></td>
      <td class="text-end">${fmt(ob)}</td>
      <td class="d-none d-md-table-cell"></td>
    </tr>`;
  }

  if (entries.length === 0 && ob === 0) {
    html += `<tr><td colspan="6" class="text-muted text-center p-3">仕訳がありません</td></tr>`;
  }

  entries.forEach(function(e) {
    const cps = e.counterparts;
    const cpStr = cps.length === 0 ? '' : (cps.length === 1 ? cps[0] : '諸口');
    html += `<tr style="cursor:pointer" class="ledger-row" data-tid="${escHtml(e.transaction_id)}">
      <td>${escHtml(e.entry_date)}</td>
      <td>${escHtml(e.note)}</td>
      <td class="text-end">${e.debit  ? fmt(e.debit)  : ''}</td>
      <td class="text-end">${e.credit ? fmt(e.credit) : ''}</td>
      <td class="text-end">${fmt(e.balance)}</td>
      <td class="d-none d-md-table-cell text-muted small">${escHtml(cpStr)}</td>
    </tr>`;
  });

  html += '</tbody></table></div>';
  $('#ledger-area').html(html);
}

// ---- TSV エクスポート ----

$('#btn-export').on('click', function() {
  if (!selectedAccountId) return;
  const from = $('#filter-from').val();
  const to   = $('#filter-to').val();
  let url = `/api/export/ledger?account_id=${selectedAccountId}`;
  if (from) url += `&from=${encodeURIComponent(from)}`;
  if (to)   url += `&to=${encodeURIComponent(to)}`;
  window.location.href = url;
});

// ---- 表示ボタン ----

$('#btn-filter').on('click', function() {
  loadLedger();
});

// ---- イベント：サイドバー科目クリック ----

$(document).on('click', '.account-item', function() {
  selectAccount(parseInt($(this).data('id'), 10));
});

// ---- イベント：モバイルセレクト ----

$('#account-select-mobile').on('change', function() {
  const id = parseInt($(this).val(), 10);
  if (id) selectAccount(id);
});

// ---- イベント：元帳行クリック → 編集モーダル ----

$(document).on('click', '.ledger-row', function() {
  const tid = $(this).data('tid');
  openEditModal(tid);
});

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

function openEditModal(tid) {
  $.getJSON(`/api/journal/transaction/${tid}`).then(function(tx) {
    editingTid = tx.transaction_id;
    $('#edit-date').val(tx.entry_date);
    $('#edit-note').val(tx.note || '');
    $('#edit-lines-body').empty();
    tx.lines.forEach(function(line) {
      addEditRow(line.debit_credit, line.account_id, line.amount);
    });
    updateEditBalance();
    new bootstrap.Modal('#editTxnModal').show();
  }).fail(function() {
    showAlert('取引の読み込みに失敗しました', 'danger');
  });
}

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
      showAlert('更新しました', 'success');
      loadLedger();
    },
    error: function(xhr) {
      alert(xhr.responseJSON?.error || '更新に失敗しました');
    }
  });
});

$('#btn-edit-delete').on('click', function() {
  if (!confirm('この取引を削除しますか？\n（この操作は取り消せません）')) return;
  $.ajax({
    url: `/api/journal/transaction/${editingTid}`,
    method: 'DELETE',
    success: function() {
      bootstrap.Modal.getInstance('#editTxnModal').hide();
      showAlert('削除しました', 'success');
      loadLedger();
    },
    error: function(xhr) {
      showAlert(xhr.responseJSON?.error || '削除に失敗しました', 'danger');
    }
  });
});

// ---- 初期化 ----

$(function() {
  loadAccounts();
});
