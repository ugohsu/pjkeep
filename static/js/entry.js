// entry.js - 記帳フォーム

let accountMap = {}; // name -> {id, element, code}
let rowIndex = 0;

function fmt(n) {
  return Number(n).toLocaleString('ja-JP');
}

function showAlert(msg, type) {
  $('#alert-box').html(
    `<div class="alert alert-${type} alert-dismissible"><button type="button" class="btn-close" data-bs-dismiss="alert"></button>${msg}</div>`
  );
}

// アカウント一覧取得
function loadAccounts() {
  return $.getJSON('/api/accounts').then(function(data) {
    accountMap = {};
    const dl = $('#account-list').empty();
    data.forEach(function(a) {
      accountMap[a.name] = a;
      dl.append(`<option value="${$('<div>').text(a.name).html()}" label="${a.element}">`);
    });
  });
}

// 行を追加
function addRow(dcDefault) {
  rowIndex++;
  const ri = rowIndex;
  const row = $(`
    <tr data-row="${ri}">
      <td>
        <select class="form-select form-select-sm dc-select">
          <option value="debit"  ${dcDefault==='debit' ?'selected':''}>借方</option>
          <option value="credit" ${dcDefault==='credit'?'selected':''}>貸方</option>
        </select>
      </td>
      <td>
        <input type="text" class="form-control form-control-sm account-input"
               list="account-list" placeholder="勘定科目">
      </td>
      <td>
        <input type="number" class="form-control form-control-sm amount-input"
               min="1" step="1" placeholder="金額">
      </td>
      <td>
        <button type="button" class="btn btn-sm btn-outline-danger remove-row">×</button>
      </td>
    </tr>
  `);
  $('#lines-body').append(row);
  updateBalance();
}

// 残高表示更新
function updateBalance() {
  let debitSum = 0, creditSum = 0;
  let blankCount = 0;
  $('#lines-body tr').each(function() {
    const dc = $(this).find('.dc-select').val();
    const amtInput = $(this).find('.amount-input');
    // auto-filled の行はまだユーザーが確定していないので blank 扱い
    if (amtInput.hasClass('auto-filled')) { blankCount++; return; }
    const amt = parseInt(amtInput.val(), 10);
    if (isNaN(amt) || amt <= 0) { blankCount++; return; }
    if (dc === 'debit') debitSum += amt;
    else creditSum += amt;
  });

  // 自動補完: blank が1行のみ
  if (blankCount === 1) {
    $('#lines-body tr').each(function() {
      const amtInput = $(this).find('.amount-input');
      const val = amtInput.val();
      if (val === '' || val === '0' || amtInput.hasClass('auto-filled')) {
        const dc = $(this).find('.dc-select').val();
        let fill = (dc === 'debit') ? (creditSum - debitSum) : (debitSum - creditSum);
        if (fill > 0) {
          amtInput.val(fill).addClass('auto-filled');
          if (dc === 'debit') debitSum += fill; else creditSum += fill;
        } else {
          amtInput.val('').removeClass('auto-filled');
        }
      }
    });
  } else {
    $('.auto-filled').val('').removeClass('auto-filled');
  }

  const balanced = debitSum === creditSum && debitSum > 0;
  const cell = $('#balance-cell');
  if (debitSum === 0 && creditSum === 0) {
    cell.html('');
  } else {
    const cls = balanced ? 'text-success' : 'text-danger';
    cell.html(`<span class="${cls}">${fmt(debitSum)} / ${fmt(creditSum)}</span>`);
  }
}

// フォーム送信
$('#entry-form').on('submit', function(e) {
  e.preventDefault();
  $('#alert-box').empty();

  const entry_date = $('#entry-date').val();
  const note = $('#entry-note').val().trim();
  if (!entry_date) { showAlert('取引日を入力してください', 'warning'); return; }

  const lines = [];
  let valid = true;

  $('#lines-body tr').each(function() {
    const dc = $(this).find('.dc-select').val();
    const accName = $(this).find('.account-input').val().trim();
    const amt = parseInt($(this).find('.amount-input').val(), 10);

    if (!accName) { showAlert('勘定科目を入力してください', 'warning'); valid = false; return false; }
    if (!accountMap[accName]) { showAlert(`「${accName}」は登録されていない勘定科目です`, 'warning'); valid = false; return false; }
    if (isNaN(amt) || amt <= 0) { showAlert('金額を正しく入力してください', 'warning'); valid = false; return false; }

    lines.push({ account_id: accountMap[accName].id, debit_credit: dc, amount: amt });
  });

  if (!valid) return;

  $.ajax({
    url: '/api/journal',
    method: 'POST',
    contentType: 'application/json',
    data: JSON.stringify({ entry_date, note, lines }),
    success: function(res) {
      showConfirm(entry_date, note, lines);
      resetForm(entry_date);
    },
    error: function(xhr) {
      showAlert(xhr.responseJSON?.error || '登録に失敗しました', 'danger');
    }
  });
});

function showConfirm(entry_date, note, lines) {
  let html = `<p class="small text-muted mb-1">${entry_date}　${note}</p>`;
  html += '<table class="table table-sm table-bordered">';
  html += '<thead><tr><th>借/貸</th><th>勘定科目</th><th class="text-end">金額</th></tr></thead><tbody>';
  lines.forEach(function(l) {
    const accName = Object.keys(accountMap).find(k => accountMap[k].id === l.account_id);
    const dcLabel = l.debit_credit === 'debit' ? '借方' : '貸方';
    html += `<tr><td>${dcLabel}</td><td>${accName}</td><td class="text-end">¥${fmt(l.amount)}</td></tr>`;
  });
  html += '</tbody></table>';
  $('#confirm-table').html(html);
  $('#confirm-area').show();
}

function resetForm(keepDate) {
  $('#lines-body').empty();
  rowIndex = 0;
  addRow('debit');
  addRow('credit');
  $('#entry-note').val('');
  if (keepDate) $('#entry-date').val(keepDate);
}

// イベント委譲
$(document).on('click', '.remove-row', function() {
  if ($('#lines-body tr').length <= 2) { showAlert('最低2行必要です', 'warning'); return; }
  $(this).closest('tr').remove();
  updateBalance();
});

$(document).on('change input', '.dc-select, .amount-input', function() {
  // auto-filledを手動入力でクリア
  if ($(this).hasClass('amount-input') && $(this).hasClass('auto-filled')) {
    $(this).removeClass('auto-filled');
  }
  updateBalance();
});

$(document).on('change', '.account-input', updateBalance);

$('#btn-add-row').on('click', function() {
  addRow('debit');
});

// 初期化
$(function() {
  // 今日の日付をセット
  const today = new Date().toISOString().split('T')[0];
  $('#entry-date').val(today);

  loadAccounts().then(function() {
    addRow('debit');
    addRow('credit');
  });
});
