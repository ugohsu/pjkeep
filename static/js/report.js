// report.js - 財務諸表

function fmt(n) {
  return Number(n).toLocaleString('ja-JP');
}

function sign(n) {
  return n < 0 ? 'text-danger' : '';
}

function loadMonths() {
  return $.getJSON('/api/months').then(function(months) {
    const sel = $('#ym-select').empty();
    const today = new Date().toISOString().slice(0,7);
    let hasCurrent = false;
    months.forEach(function(ym) {
      const opt = $(`<option value="${ym}">${ym}</option>`);
      if (ym === today) { opt.prop('selected', true); hasCurrent = true; }
      sel.append(opt);
    });
    // 当月データがなくても当月を選択肢に追加
    if (!hasCurrent) {
      sel.prepend(`<option value="${today}" selected>${today}（未記帳）</option>`);
    }
  });
}

function loadReports(ym) {
  $('#pl-content').html('<div class="p-3 text-muted">読み込み中...</div>');
  $('#bs-content').html('<div class="p-3 text-muted">読み込み中...</div>');
  $('#pl-ym').text(ym);
  $('#bs-ym').text(`${ym} 末時点（累計）`);

  $.when(
    $.getJSON('/api/report/pl', { ym }),
    $.getJSON('/api/report/bs', { ym })
  ).then(function(plRes, bsRes) {
    renderPL(plRes[0]);
    renderBS(bsRes[0]);
  }).fail(function() {
    $('#pl-content, #bs-content').html('<div class="text-danger p-3">読み込みに失敗しました</div>');
  });
}

function renderPL(data) {
  let html = '<table class="table table-sm mb-0">';

  // 収益
  html += '<tbody><tr class="table-light"><th colspan="2">収益</th></tr>';
  if (data.revenues.length === 0) {
    html += '<tr><td colspan="2" class="text-muted ps-3">（なし）</td></tr>';
  }
  data.revenues.forEach(function(r) {
    html += `<tr><td class="ps-3">${r.name}</td><td class="text-end">¥${fmt(r.amount)}</td></tr>`;
  });
  html += `<tr class="fw-bold"><td>収益合計</td><td class="text-end">¥${fmt(data.total_revenues)}</td></tr>`;

  // 費用
  html += '<tr class="table-light"><th colspan="2">費用</th></tr>';
  if (data.expenses.length === 0) {
    html += '<tr><td colspan="2" class="text-muted ps-3">（なし）</td></tr>';
  }
  data.expenses.forEach(function(e) {
    html += `<tr><td class="ps-3">${e.name}</td><td class="text-end">¥${fmt(e.amount)}</td></tr>`;
  });
  html += `<tr class="fw-bold"><td>費用合計</td><td class="text-end">¥${fmt(data.total_expenses)}</td></tr>`;

  // 純利益
  const ni = data.net_income;
  html += `<tr class="table-primary fw-bold">
    <td>当期純利益</td>
    <td class="text-end ${sign(ni)}">¥${fmt(ni)}</td>
  </tr>`;

  html += '</tbody></table>';
  $('#pl-content').html(html);
}

function renderBS(data) {
  let html = '<table class="table table-sm mb-0">';

  // 資産
  html += '<tbody><tr class="table-light"><th colspan="2">資産</th></tr>';
  data.assets.forEach(function(a) {
    html += `<tr><td class="ps-3">${a.name}</td><td class="text-end">¥${fmt(a.amount)}</td></tr>`;
  });
  html += `<tr class="fw-bold"><td>資産合計</td><td class="text-end">¥${fmt(data.total_assets)}</td></tr>`;

  // 負債
  html += '<tr class="table-light"><th colspan="2">負債</th></tr>';
  data.liabilities.forEach(function(l) {
    html += `<tr><td class="ps-3">${l.name}</td><td class="text-end">¥${fmt(l.amount)}</td></tr>`;
  });
  html += `<tr class="fw-bold"><td>負債合計</td><td class="text-end">¥${fmt(data.total_liabilities)}</td></tr>`;

  // 純資産
  html += '<tr class="table-light"><th colspan="2">純資産</th></tr>';
  data.equity.forEach(function(e) {
    html += `<tr><td class="ps-3">${e.name}</td><td class="text-end">¥${fmt(e.amount)}</td></tr>`;
  });
  const ni = data.cumulative_net_income;
  html += `<tr><td class="ps-3 text-muted">累計純損益</td><td class="text-end ${sign(ni)}">¥${fmt(ni)}</td></tr>`;
  html += `<tr class="fw-bold"><td>純資産合計</td><td class="text-end">¥${fmt(data.total_equity)}</td></tr>`;

  // 貸借バランス確認
  const diff = data.total_assets - data.total_liabilities - data.total_equity;
  if (Math.abs(diff) > 0) {
    html += `<tr class="table-warning"><td colspan="2" class="small">⚠ 貸借差額: ¥${fmt(diff)}</td></tr>`;
  }

  html += '</tbody></table>';
  $('#bs-content').html(html);
}

$('#ym-select').on('change', function() {
  loadReports($(this).val());
});

// エクスポート：メインボタン（指定月）
$('#btn-export').on('click', function() {
  const ym = $('#ym-select').val();
  if (!ym) return;
  window.location.href = `/api/export/report?ym=${ym}`;
});

// エクスポート：指定月のみ（ドロップダウン）
$('#btn-export-month-rpt').on('click', function(e) {
  e.preventDefault();
  const ym = $('#ym-select').val();
  if (!ym) return;
  window.location.href = `/api/export/report?ym=${ym}`;
});

// エクスポート：任意の期間（モーダルを開く）
$('#btn-export-period-rpt').on('click', function(e) {
  e.preventDefault();
  new bootstrap.Modal('#reportPeriodModal').show();
});

// エクスポート：全月一覧（横展開）
$('#btn-export-monthly-rpt').on('click', function(e) {
  e.preventDefault();
  window.location.href = '/api/export/report/monthly';
});

// モーダル内のエクスポートボタン
$('#btn-report-period-ok').on('click', function() {
  const from = $('#report-period-from').val();
  const to   = $('#report-period-to').val();
  if (!from || !to) {
    alert('開始日と終了日を入力してください');
    return;
  }
  if (from > to) {
    alert('開始日は終了日より前の日付を指定してください');
    return;
  }
  bootstrap.Modal.getInstance('#reportPeriodModal').hide();
  window.location.href = `/api/export/report?from=${from}&to=${to}`;
});

// ---------- 累計純損益の振替 ----------

function loadClosings() {
  $.getJSON('/api/closings').then(function(data) {
    renderClosings(data);
  }).fail(function() {
    $('#closing-list-area').html('<div class="text-danger p-3 small">読み込みに失敗しました</div>');
  });
}

function renderClosings(data) {
  if (data.length === 0) {
    $('#closing-list-area').html('<div class="p-3 text-muted small">振替の登録はありません。</div>');
    return;
  }
  let html = '<div class="table-responsive"><table class="table table-sm mb-0">';
  html += '<thead class="table-light"><tr><th>振替日</th><th>振替先科目</th><th class="text-end">振替金額</th><th>備考</th><th></th></tr></thead><tbody>';
  data.forEach(function(c) {
    html += `<tr>
      <td>${c.closing_date}</td>
      <td>${c.account_name}</td>
      <td class="text-end ${sign(c.amount)}">¥${fmt(c.amount)}</td>
      <td class="text-muted small">${c.note || ''}</td>
      <td><button class="btn btn-xs btn-outline-danger btn-closing-del" data-id="${c.id}" data-date="${c.closing_date}">削除</button></td>
    </tr>`;
  });
  html += '</tbody></table></div>';
  $('#closing-list-area').html(html);
}

// 新規登録ボタン
$('#btn-closing-new').on('click', function() {
  $('#closing-modal-alert').html('');
  $('#closing-date').val('');
  $('#closing-note').val('');
  $('#closing-preview-area').hide();
  $('#closing-preview-amount').text('');

  // 純資産科目を取得してセレクトに設定
  $.getJSON('/api/accounts').then(function(accounts) {
    const equity = accounts.filter(a => a.element === 'equity');
    const sel = $('#closing-account').empty();
    if (equity.length === 0) {
      sel.append('<option value="">（純資産科目がありません）</option>');
    } else {
      equity.forEach(function(a) {
        sel.append(`<option value="${a.id}">${a.name}</option>`);
      });
    }
  });

  new bootstrap.Modal('#closingModal').show();
});

// 振替日変更時にプレビュー金額を取得
$('#closing-date').on('change', function() {
  const d = $(this).val();
  $('#closing-preview-area').hide();
  if (!d) return;
  $.getJSON('/api/closings/preview', { closing_date: d })
    .then(function(res) {
      const amt = res.amount;
      $('#closing-preview-amount')
        .text(`¥${fmt(amt)}`)
        .removeClass('text-danger')
        .addClass(amt < 0 ? 'text-danger' : '');
      $('#closing-preview-area').show();
      $('#closing-modal-alert').html('');
    })
    .fail(function(xhr) {
      const msg = xhr.responseJSON?.error || 'プレビューの取得に失敗しました';
      $('#closing-modal-alert').html(`<div class="alert alert-warning py-1 small">${msg}</div>`);
      $('#closing-preview-area').hide();
    });
});

// 登録ボタン
$('#btn-closing-save').on('click', function() {
  const closing_date = $('#closing-date').val();
  const account_id   = $('#closing-account').val();
  const note         = $('#closing-note').val().trim();

  if (!closing_date) {
    $('#closing-modal-alert').html('<div class="alert alert-warning py-1 small">振替日を入力してください</div>');
    return;
  }
  if (!account_id) {
    $('#closing-modal-alert').html('<div class="alert alert-warning py-1 small">振替先科目を選択してください</div>');
    return;
  }

  $.ajax({
    url: '/api/closings',
    method: 'POST',
    contentType: 'application/json',
    data: JSON.stringify({ closing_date, account_id: parseInt(account_id), note }),
    success: function() {
      bootstrap.Modal.getInstance('#closingModal')?.hide();
      loadClosings();
      // BS 表示も再読み込み
      const ym = $('#ym-select').val();
      if (ym) loadReports(ym);
    },
    error: function(xhr) {
      const msg = xhr.responseJSON?.error || '登録に失敗しました';
      $('#closing-modal-alert').html(`<div class="alert alert-danger py-1 small">${msg}</div>`);
    }
  });
});

// 削除ボタン
$(document).on('click', '.btn-closing-del', function() {
  const id   = $(this).data('id');
  const date = $(this).data('date');
  if (!confirm(`${date} の振替を削除しますか？`)) return;
  $.ajax({
    url: `/api/closings/${id}`,
    method: 'DELETE',
    success: function() {
      loadClosings();
      const ym = $('#ym-select').val();
      if (ym) loadReports(ym);
    },
    error: function() {
      alert('削除に失敗しました');
    }
  });
});

$(function() {
  loadMonths().then(function() {
    const ym = $('#ym-select').val();
    if (ym) loadReports(ym);
  });
  loadClosings();
});
