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

$(function() {
  loadMonths().then(function() {
    const ym = $('#ym-select').val();
    if (ym) loadReports(ym);
  });
});
