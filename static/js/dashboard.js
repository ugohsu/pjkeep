// dashboard.js - 比例縮尺損益計算書 / 予算実績ウィジェット
'use strict';

function escHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

let plChart = null;

// 収益：Rmd に合わせた薄オレンジ（単色）
const REVENUE_COLOR = '#FFE0B2';
// 費用：Rmd に合わせた淡い黄色（単色）
const EXPENSE_COLOR = '#FFF9C4';
const NET_INCOME_COLOR = '#DCEDC8'; // Rmd の営業利益色
const NET_LOSS_COLOR   = 'red';     // Rmd の営業損失色（純赤）

function loadPlChart(range) {
    // ボタン状態を更新
    $('.range-btn').removeClass('btn-primary').addClass('btn-outline-secondary');
    $(`.range-btn[data-range="${range}"]`).removeClass('btn-outline-secondary').addClass('btn-primary');

    $.getJSON('/api/dashboard/pl_monthly', { range })
        .then(renderPlChart)
        .fail(function() {
            $('#pl-chart-area').html('<div class="text-danger p-3">読み込みに失敗しました</div>');
        });
}

function renderPlChart(data) {
    const monthly  = data.monthly;
    const accounts = data.accounts;

    if (monthly.length === 0) {
        $('#pl-chart-area').html('<div class="p-3 text-muted">データがありません</div>');
        return;
    }

    const months          = monthly.map(function(m) { return m.ym; });
    const revenueAccounts = accounts.filter(function(a) { return a.element === 'revenues'; });
    const expenseAccounts = accounts.filter(function(a) { return a.element === 'expenses'; });

    const datasets = [];

    // 借方スタック（左）：当期純利益を最初に追加（グラフ最下段）
    datasets.push({
        label: '当期純利益',
        stack: 'debit',
        backgroundColor: NET_INCOME_COLOR,
        borderColor: '#555',
        borderWidth: 0.5,
        borderSkipped: false,
        data: monthly.map(function(m) { return m.net_income > 0 ? m.net_income : 0; })
    });

    // 借方スタック（左）：費用科目を逆順で追加（財務諸表の上位科目がグラフ上段に来るよう）
    expenseAccounts.slice().reverse().forEach(function(acc, i) {
        datasets.push({
            label: acc.name,
            stack: 'debit',
            backgroundColor: EXPENSE_COLOR,
            borderColor: '#555',
            borderWidth: 0.5,
            borderSkipped: false,
            data: monthly.map(function(m) { return m.by_account[acc.id] || 0; })
        });
    });

    // 貸方スタック（右）：当期純損失を最初に追加（グラフ最下段）
    datasets.push({
        label: '当期純損失',
        stack: 'credit',
        backgroundColor: NET_LOSS_COLOR,
        borderColor: '#555',
        borderWidth: 0.5,
        borderSkipped: false,
        data: monthly.map(function(m) { return m.net_income < 0 ? -m.net_income : 0; })
    });

    // 貸方スタック（右）：収益科目を逆順で追加（財務諸表の上位科目がグラフ上段に来るよう）
    revenueAccounts.slice().reverse().forEach(function(acc) {
        datasets.push({
            label: acc.name,
            stack: 'credit',
            backgroundColor: REVENUE_COLOR,
            borderColor: '#555',
            borderWidth: 0.5,
            borderSkipped: false,
            data: monthly.map(function(m) { return m.by_account[acc.id] || 0; })
        });
    });

    // Y軸上限：全月の max(収益合計, 費用合計) に 5% マージン
    const yMax = Math.max.apply(null, monthly.map(function(m) {
        return Math.max(m.total_revenues, m.total_expenses);
    }));

    // キャンバス幅：1月あたり 80px、最小はコンテナ幅
    const container  = document.getElementById('pl-chart-area');
    const minWidth   = container ? container.offsetWidth - 4 : 600;
    const canvasWidth = Math.max(minWidth, months.length * 80);

    // DOM を組み替えてからキャンバスサイズを設定
    $('#pl-chart-area').html(
        '<div id="pl-chart-wrapper"><canvas id="pl-chart"></canvas></div>'
    );
    const canvas = document.getElementById('pl-chart');
    canvas.width        = canvasWidth;
    canvas.height       = 300;
    canvas.style.width  = canvasWidth + 'px';
    canvas.style.height = '300px';

    if (plChart) { plChart.destroy(); plChart = null; }

    plChart = new Chart(canvas, {
        type: 'bar',
        data: { labels: months, datasets: datasets },
        options: {
            responsive: false,
            maintainAspectRatio: false,
            animation: false,
            scales: {
                x: {
                    stacked: true,
                    grid: { display: false },
                    ticks: { font: { size: 11 } }
                },
                y: {
                    stacked: true,
                    min: 0,
                    max: yMax > 0 ? Math.ceil(yMax * 1.05) : undefined,
                    ticks: {
                        font: { size: 11 },
                        callback: function(v) {
                            if (v >= 1000000) return (v / 1000000).toFixed(1) + 'M';
                            if (v >= 1000)    return (v / 1000).toFixed(0) + 'K';
                            return v;
                        }
                    }
                }
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'bottom',
                    labels: { boxWidth: 12, font: { size: 11 }, padding: 8 }
                },
                tooltip: {
                    mode: 'nearest',
                    intersect: true,
                    callbacks: {
                        title: function(items) {
                            if (!items.length) return '';
                            var m = monthly[items[0].dataIndex];
                            return m.ym;
                        },
                        label: function(ctx) {
                            var val  = ctx.raw;
                            if (val === 0) return null;
                            var m    = monthly[ctx.dataIndex];
                            var base = m.total_revenues > 0 ? m.total_revenues : m.total_expenses;
                            var pct  = base > 0 ? (val / base * 100).toFixed(1) : '-';
                            return ' ' + ctx.dataset.label + ': ¥' +
                                   val.toLocaleString('ja-JP') + ' (' + pct + '%)';
                        }
                    }
                }
            }
        }
    });
}

// ---------- 純資産推移グラフ ----------

let eqChart = null;

function loadEquityChart(range) {
    $('.eq-range-btn').removeClass('btn-primary').addClass('btn-outline-secondary');
    $(`.eq-range-btn[data-range="${range}"]`).removeClass('btn-outline-secondary').addClass('btn-primary');

    $.getJSON('/api/dashboard/equity_monthly', { range })
        .then(renderEquityChart)
        .fail(function() {
            $('#eq-chart-area').html('<div class="text-danger p-3">読み込みに失敗しました</div>');
        });
}

function renderEquityChart(data) {
    var monthly = data.monthly;

    if (monthly.length === 0) {
        $('#eq-chart-area').html('<div class="p-3 text-muted">データがありません</div>');
        return;
    }

    var months  = monthly.map(function(m) { return m.ym; });
    var values  = monthly.map(function(m) { return m.total_equity; });

    var container  = document.getElementById('eq-chart-area');
    var minWidth   = container ? container.offsetWidth - 4 : 600;
    var canvasWidth = Math.max(minWidth, months.length * 80);

    $('#eq-chart-area').html(
        '<div id="eq-chart-wrapper"><canvas id="eq-chart"></canvas></div>'
    );
    var canvas = document.getElementById('eq-chart');
    canvas.width        = canvasWidth;
    canvas.height       = 240;
    canvas.style.width  = canvasWidth + 'px';
    canvas.style.height = '240px';

    if (eqChart) { eqChart.destroy(); eqChart = null; }

    eqChart = new Chart(canvas, {
        type: 'line',
        data: {
            labels: months,
            datasets: [{
                label: '純資産合計',
                data: values,
                borderColor: '#1E88E5',
                backgroundColor: 'rgba(30,136,229,0.1)',
                borderWidth: 2,
                pointRadius: 3,
                pointHoverRadius: 5,
                fill: true,
                tension: 0.2
            }]
        },
        options: {
            responsive: false,
            maintainAspectRatio: false,
            animation: false,
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { font: { size: 11 } }
                },
                y: {
                    ticks: {
                        font: { size: 11 },
                        callback: function(v) {
                            if (Math.abs(v) >= 1000000) return (v / 1000000).toFixed(1) + 'M';
                            if (Math.abs(v) >= 1000)    return (v / 1000).toFixed(0) + 'K';
                            return v;
                        }
                    }
                }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(ctx) {
                            return ' 純資産合計: ¥' + ctx.raw.toLocaleString('ja-JP');
                        }
                    }
                }
            }
        }
    });
}

// ---------- 予算実績ウィジェット ----------

const BUDGET_COLORS = [
    { fill: '#E0F2F1', stroke: '#00695C' },  // ティール
    { fill: '#F3E5F5', stroke: '#6A1B9A' },  // パープル
    { fill: '#FFF8E1', stroke: '#F57F17' },  // アンバー
    { fill: '#FFEBEE', stroke: '#B71C1C' },  // レッド
    { fill: '#E8EAF6', stroke: '#283593' },  // インディゴ
    { fill: '#E8F5E9', stroke: '#1B5E20' },  // グリーン
];
const budgetCharts = {};
let bwAllExpenseAccounts = null;
let bwEditingId = null;
let bwSelectedAccounts = [];
let bwOverrides = [];

function loadBudgetWidgets() {
    $.getJSON('/api/dashboard/budget_widgets').then(function(widgets) {
        Object.keys(budgetCharts).forEach(function(id) {
            budgetCharts[id].destroy();
            delete budgetCharts[id];
        });
        var $container = $('#budget-widgets-container');
        $container.empty();
        widgets.forEach(function(w) {
            $container.append(buildWidgetCard(w));
            loadBudgetChart(w.id, '3m');
        });
    });
}

function buildWidgetCard(widget) {
    return [
        '<div class="card mb-3" id="budget-widget-card-' + widget.id + '">',
        '  <div class="card-header d-flex align-items-center gap-2 flex-wrap">',
        '    <span class="fw-bold">' + escHtml(widget.title) + '</span>',
        '    <div class="ms-auto d-flex gap-2 align-items-center flex-wrap">',
        '      <div class="btn-group btn-group-sm bw-range-btns" data-widget-id="' + widget.id + '">',
        '        <button class="btn btn-primary bw-range-btn" data-range="3m">3ヶ月</button>',
        '        <button class="btn btn-outline-secondary bw-range-btn" data-range="6m">半年</button>',
        '        <button class="btn btn-outline-secondary bw-range-btn" data-range="12m">1年</button>',
        '        <button class="btn btn-outline-secondary bw-range-btn" data-range="all">全期間</button>',
        '      </div>',
        '      <button class="btn btn-outline-secondary btn-sm bw-edit-btn" data-widget-id="' + widget.id + '">編集</button>',
        '      <button class="btn btn-outline-danger btn-sm bw-delete-btn" data-widget-id="' + widget.id + '">削除</button>',
        '    </div>',
        '  </div>',
        '  <div class="card-body p-2">',
        '    <div id="budget-chart-area-' + widget.id + '"><div class="p-3 text-muted">読み込み中...</div></div>',
        '  </div>',
        '</div>'
    ].join('\n');
}

function loadBudgetChart(widgetId, range) {
    var $card = $('#budget-widget-card-' + widgetId);
    $card.find('.bw-range-btn').removeClass('btn-primary').addClass('btn-outline-secondary');
    $card.find('.bw-range-btn[data-range="' + range + '"]').removeClass('btn-outline-secondary').addClass('btn-primary');

    $.getJSON('/api/dashboard/budget_widgets/' + widgetId + '/data', { range: range })
        .then(function(data) { renderBudgetChart(widgetId, data); })
        .fail(function() {
            $('#budget-chart-area-' + widgetId).html('<div class="text-danger p-3">読み込みに失敗しました</div>');
        });
}

function renderBudgetChart(widgetId, data) {
    var areaId   = 'budget-chart-area-' + widgetId;
    var accounts = data.accounts;
    var monthly  = data.monthly;

    if (!monthly || monthly.length === 0) {
        $('#' + areaId).html('<div class="p-3 text-muted">データがありません</div>');
        return;
    }

    var months   = monthly.map(function(m) { return m.ym; });
    var reversed = accounts.slice().reverse();
    var datasets = [];

    // 有利差異（実績 stack の最下段 ― 実績 < 予算の月のみ露出）
    var rawFavorable = monthly.map(function(m) { return Math.max(0, m.budget_total - m.actual_total); });
    datasets.push({
        label: '有利差異',
        stack: 'actual',
        backgroundColor: '#DCEDC8',
        borderColor: '#555',
        borderWidth: 0.5,
        borderSkipped: false,
        rawData: rawFavorable,
        data: monthly.map(function(m, i) {
            var scale = Math.max(m.actual_total, m.budget_total);
            return scale > 0 ? rawFavorable[i] / scale * 100 : 0;
        })
    });

    // 借方（実績）
    reversed.forEach(function(acc, ri) {
        var colorIdx    = accounts.length - 1 - ri;
        var color       = BUDGET_COLORS[colorIdx % BUDGET_COLORS.length];
        var rawData     = monthly.map(function(m) { return m.by_account_actual[String(acc.id)] || 0; });
        var rawBudget   = monthly.map(function(m) { return m.by_account_budget[String(acc.id)] || 0; });
        datasets.push({
            label: acc.name + '（実績）',
            stack: 'actual',
            backgroundColor: color.fill,
            borderColor: color.stroke,
            borderWidth: 0.5,
            borderSkipped: false,
            rawData: rawData,
            rawBudgetData: rawBudget,
            data: monthly.map(function(m, i) {
                var scale = Math.max(m.actual_total, m.budget_total);
                return scale > 0 ? rawData[i] / scale * 100 : 0;
            })
        });
    });

    // 不利差異（予算 stack の最下段 ― 実績 > 予算の月のみ露出）
    var rawUnfavorable = monthly.map(function(m) { return Math.max(0, m.actual_total - m.budget_total); });
    datasets.push({
        label: '不利差異',
        stack: 'budget',
        backgroundColor: 'red',
        borderColor: '#555',
        borderWidth: 0.5,
        borderSkipped: false,
        rawData: rawUnfavorable,
        data: monthly.map(function(m, i) {
            var scale = Math.max(m.actual_total, m.budget_total);
            return scale > 0 ? rawUnfavorable[i] / scale * 100 : 0;
        })
    });

    // 貸方（予算）
    reversed.forEach(function(acc, ri) {
        var colorIdx = accounts.length - 1 - ri;
        var color    = BUDGET_COLORS[colorIdx % BUDGET_COLORS.length];
        var rawData  = monthly.map(function(m) { return m.by_account_budget[String(acc.id)] || 0; });
        datasets.push({
            label: acc.name + '（予算）',
            stack: 'budget',
            backgroundColor: color.fill,
            borderColor: color.stroke,
            borderWidth: 0.5,
            borderSkipped: false,
            rawData: rawData,
            data: monthly.map(function(m, i) {
                var scale = Math.max(m.actual_total, m.budget_total);
                return scale > 0 ? rawData[i] / scale * 100 : 0;
            })
        });
    });

    var container   = document.getElementById(areaId);
    var minWidth    = container ? container.offsetWidth - 4 : 600;
    var canvasWidth = Math.max(minWidth, months.length * 80);

    $('#' + areaId).html(
        '<div class="chart-scroll-wrapper"><canvas id="budget-chart-' + widgetId + '"></canvas></div>'
    );
    var canvas = document.getElementById('budget-chart-' + widgetId);
    canvas.width        = canvasWidth;
    canvas.height       = 300;
    canvas.style.width  = canvasWidth + 'px';
    canvas.style.height = '300px';

    if (budgetCharts[widgetId]) { budgetCharts[widgetId].destroy(); }
    budgetCharts[widgetId] = new Chart(canvas, {
        type: 'bar',
        data: { labels: months, datasets: datasets },
        options: {
            responsive: false,
            maintainAspectRatio: false,
            animation: false,
            scales: {
                x: {
                    stacked: true,
                    grid: { display: false },
                    ticks: { font: { size: 11 } }
                },
                y: {
                    stacked: true,
                    min: 0,
                    max: 100,
                    ticks: {
                        font: { size: 11 },
                        callback: function(v) { return v + '%'; }
                    }
                }
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'bottom',
                    labels: { boxWidth: 12, font: { size: 11 }, padding: 8 }
                },
                tooltip: {
                    mode: 'nearest',
                    intersect: true,
                    callbacks: {
                        title: function(items) {
                            return items.length ? monthly[items[0].dataIndex].ym : '';
                        },
                        label: function(ctx) {
                            if (ctx.raw === 0) return null;
                            var raw = ctx.dataset.rawData[ctx.dataIndex];
                            return ' ' + ctx.dataset.label + ': ¥' +
                                   raw.toLocaleString('ja-JP') + ' (' + ctx.raw.toFixed(1) + '%)';
                        },
                        afterLabel: function(ctx) {
                            if (ctx.raw === 0 || !ctx.dataset.rawBudgetData) return null;
                            var actual = ctx.dataset.rawData[ctx.dataIndex];
                            var budget = ctx.dataset.rawBudgetData[ctx.dataIndex];
                            var diff   = actual - budget;
                            if (diff > 0) return '   → 不利差異 ¥' + diff.toLocaleString('ja-JP');
                            if (diff < 0) return '   → 有利差異 ¥' + (-diff).toLocaleString('ja-JP');
                            return null;
                        }
                    }
                }
            }
        }
    });
}

// ---------- モーダル ----------

function loadExpenseAccounts(callback) {
    if (bwAllExpenseAccounts !== null) { callback(); return; }
    $.getJSON('/api/accounts').then(function(accounts) {
        bwAllExpenseAccounts = accounts.filter(function(a) { return a.element === 'expenses'; });
        callback();
    });
}

function bwPopulateAccountSelect() {
    var $sel = $('#bw-account-select').empty();
    bwAllExpenseAccounts.forEach(function(acc) {
        $sel.append($('<option>').val(acc.id).text(acc.name));
    });
}

function bwRenderAccountsList() {
    var $list = $('#bw-accounts-list').empty();
    if (bwSelectedAccounts.length === 0) { $('#bw-accounts-empty').show(); return; }
    $('#bw-accounts-empty').hide();
    bwSelectedAccounts.forEach(function(acc, idx) {
        $list.append([
            '<div class="d-flex align-items-center gap-2 mb-1">',
            '  <span class="flex-grow-1">' + escHtml(acc.name) + '</span>',
            '  <input type="number" class="form-control form-control-sm text-end bw-default-amount"',
            '         style="width:120px" min="0" value="' + acc.default_amount + '" data-idx="' + idx + '">',
            '  <span class="text-muted small text-nowrap">円/月</span>',
            '  <button type="button" class="btn btn-outline-danger btn-sm bw-remove-account" data-idx="' + idx + '">✕</button>',
            '</div>'
        ].join(''));
    });
}

function bwRenderOverridesList() {
    var $list = $('#bw-overrides-list').empty();
    if (bwOverrides.length === 0) return;
    var opts = bwSelectedAccounts.map(function(a) {
        return '<option value="' + a.account_id + '">' + escHtml(a.name) + '</option>';
    }).join('');
    bwOverrides.forEach(function(ov, idx) {
        $list.append([
            '<div class="d-flex align-items-center gap-1 mb-1 flex-wrap">',
            '  <select class="form-select form-select-sm bw-ov-account" style="width:150px" data-idx="' + idx + '">' + opts + '</select>',
            '  <input type="text" class="form-control form-control-sm bw-ov-ym" style="width:105px"',
            '         placeholder="YYYY-MM" value="' + escHtml(ov.year_month || '') + '" data-idx="' + idx + '">',
            '  <input type="number" class="form-control form-control-sm text-end bw-ov-amount" style="width:110px"',
            '         min="0" value="' + (ov.amount || 0) + '" data-idx="' + idx + '">',
            '  <span class="text-muted small">円</span>',
            '  <button type="button" class="btn btn-outline-danger btn-sm bw-remove-override" data-idx="' + idx + '">✕</button>',
            '</div>'
        ].join(''));
        $('.bw-ov-account[data-idx="' + idx + '"]').val(ov.account_id);
    });
}

function bwOpenModal() {
    bwPopulateAccountSelect();
    bwRenderAccountsList();
    bwRenderOverridesList();
    $('#bw-overrides-section').hide();
    $('#bw-overrides-caret').text('▶');
    $('#bw-error-msg').text('');
    new bootstrap.Modal(document.getElementById('budgetWidgetModal')).show();
}

function openAddModal() {
    loadExpenseAccounts(function() {
        bwEditingId = null;
        bwSelectedAccounts = [];
        bwOverrides = [];
        $('#budgetModalTitle').text('予算実績グラフの追加');
        $('#bw-title').val('');
        bwOpenModal();
    });
}

function openEditModal(widgetId) {
    loadExpenseAccounts(function() {
        $.getJSON('/api/dashboard/budget_widgets/' + widgetId).then(function(widget) {
            bwEditingId = widgetId;
            $('#budgetModalTitle').text('予算実績グラフの編集');
            $('#bw-title').val(widget.title);
            bwSelectedAccounts = widget.accounts.map(function(a) {
                return { account_id: a.account_id, name: a.name, default_amount: a.default_amount };
            });
            bwOverrides = widget.overrides.map(function(ov) {
                return { account_id: ov.account_id, year_month: ov.year_month, amount: ov.amount };
            });
            bwOpenModal();
        });
    });
}

function bwCollectFormState() {
    bwSelectedAccounts.forEach(function(acc, idx) {
        var $el = $('.bw-default-amount[data-idx="' + idx + '"]');
        if ($el.length) acc.default_amount = parseInt($el.val()) || 0;
    });
    bwOverrides.forEach(function(ov, idx) {
        var $acc = $('.bw-ov-account[data-idx="' + idx + '"]');
        var $ym  = $('.bw-ov-ym[data-idx="'      + idx + '"]');
        var $amt = $('.bw-ov-amount[data-idx="'  + idx + '"]');
        if ($acc.length) ov.account_id = parseInt($acc.val());
        if ($ym.length)  ov.year_month = $ym.val().trim();
        if ($amt.length) ov.amount     = parseInt($amt.val()) || 0;
    });
}

function saveBudgetWidget() {
    bwCollectFormState();
    var title = $('#bw-title').val().trim();
    if (!title)                        { $('#bw-error-msg').text('タイトルを入力してください'); return; }
    if (bwSelectedAccounts.length === 0) { $('#bw-error-msg').text('科目を1つ以上選択してください'); return; }

    var payload = {
        title: title,
        accounts: bwSelectedAccounts.map(function(a) {
            return { account_id: a.account_id, default_amount: a.default_amount };
        }),
        overrides: bwOverrides.filter(function(ov) { return ov.year_month; })
    };
    var url    = bwEditingId === null
        ? '/api/dashboard/budget_widgets'
        : '/api/dashboard/budget_widgets/' + bwEditingId;
    var method = bwEditingId === null ? 'POST' : 'PUT';

    $('#bw-error-msg').text('');
    $.ajax({ url: url, method: method, contentType: 'application/json', data: JSON.stringify(payload) })
        .then(function() {
            bootstrap.Modal.getInstance(document.getElementById('budgetWidgetModal')).hide();
            loadBudgetWidgets();
        })
        .fail(function(xhr) {
            $('#bw-error-msg').text((xhr.responseJSON && xhr.responseJSON.error) || '保存に失敗しました');
        });
}

function deleteBudgetWidget(widgetId) {
    $.ajax({ url: '/api/dashboard/budget_widgets/' + widgetId, method: 'DELETE' })
        .then(function() {
            if (budgetCharts[widgetId]) { budgetCharts[widgetId].destroy(); delete budgetCharts[widgetId]; }
            loadBudgetWidgets();
        })
        .fail(function() { alert('削除に失敗しました'); });
}

// ---------- 初期化 ----------

$(function() {
    $(document).on('click', '.range-btn', function() {
        loadPlChart($(this).data('range'));
    });
    $(document).on('click', '.eq-range-btn', function() {
        loadEquityChart($(this).data('range'));
    });
    loadPlChart('3m');
    loadEquityChart('12m');

    // 予算実績ウィジェット
    loadBudgetWidgets();

    $('#add-budget-widget-btn').on('click', function() { openAddModal(); });
    $('#bw-save-btn').on('click', function() { saveBudgetWidget(); });

    $(document).on('click', '.bw-range-btn', function() {
        var widgetId = $(this).closest('.bw-range-btns').data('widget-id');
        loadBudgetChart(widgetId, $(this).data('range'));
    });
    $(document).on('click', '.bw-edit-btn', function() {
        openEditModal($(this).data('widget-id'));
    });
    $(document).on('click', '.bw-delete-btn', function() {
        if (!confirm('このグラフを削除しますか？')) return;
        deleteBudgetWidget($(this).data('widget-id'));
    });

    // 科目の追加・削除
    $('#bw-add-account-btn').on('click', function() {
        var accId = parseInt($('#bw-account-select').val());
        if (!accId) return;
        if (bwSelectedAccounts.some(function(a) { return a.account_id === accId; })) return;
        var acc = bwAllExpenseAccounts.find(function(a) { return a.id === accId; });
        if (!acc) return;
        bwSelectedAccounts.push({ account_id: acc.id, name: acc.name, default_amount: 0 });
        bwRenderAccountsList();
    });
    $(document).on('click', '.bw-remove-account', function() {
        bwCollectFormState();
        bwSelectedAccounts.splice(parseInt($(this).data('idx')), 1);
        bwRenderAccountsList();
        bwRenderOverridesList();
    });

    // 月次上書き
    $('#bw-overrides-toggle').on('click', function() {
        var show = !$('#bw-overrides-section').is(':visible');
        $('#bw-overrides-section').toggle(show);
        $('#bw-overrides-caret').text(show ? '▼' : '▶');
    });
    $('#bw-add-override-btn').on('click', function() {
        if (bwSelectedAccounts.length === 0) return;
        bwCollectFormState();
        bwOverrides.push({ account_id: bwSelectedAccounts[0].account_id, year_month: '', amount: 0 });
        bwRenderOverridesList();
    });
    $(document).on('click', '.bw-remove-override', function() {
        bwCollectFormState();
        bwOverrides.splice(parseInt($(this).data('idx')), 1);
        bwRenderOverridesList();
    });
});
