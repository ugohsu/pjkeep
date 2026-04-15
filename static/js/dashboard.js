// dashboard.js - 比例縮尺損益計算書
'use strict';

let plChart = null;

// Rmd の配色をベースにしたグラデーションパレット
// 収益：#FFE0B2（薄オレンジ）から濃いオレンジへ
const REVENUE_PALETTE = [
    '#FFE0B2', '#FFCC80', '#FFB74D', '#FFA726',
    '#FF9800', '#FB8C00', '#F57C00', '#EF6C00'
];
// 費用：薄青から濃い青へ
const EXPENSE_PALETTE = [
    '#E3F2FD', '#BBDEFB', '#90CAF9', '#64B5F6',
    '#42A5F5', '#2196F3', '#1E88E5', '#1565C0'
];
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
        borderColor: 'rgba(0,0,0,0.15)',
        borderWidth: 0.5,
        data: monthly.map(function(m) { return m.net_income > 0 ? m.net_income : 0; })
    });

    // 借方スタック（左）：費用科目を逆順で追加（財務諸表の上位科目がグラフ上段に来るよう）
    expenseAccounts.slice().reverse().forEach(function(acc, i) {
        var colorIdx = expenseAccounts.length - 1 - i;
        datasets.push({
            label: acc.name,
            stack: 'debit',
            backgroundColor: EXPENSE_PALETTE[colorIdx % EXPENSE_PALETTE.length],
            borderColor: 'rgba(0,0,0,0.15)',
            borderWidth: 0.5,
            data: monthly.map(function(m) { return m.by_account[acc.id] || 0; })
        });
    });

    // 貸方スタック（右）：当期純損失を最初に追加（グラフ最下段）
    datasets.push({
        label: '当期純損失',
        stack: 'credit',
        backgroundColor: NET_LOSS_COLOR,
        borderColor: 'rgba(0,0,0,0.15)',
        borderWidth: 0.5,
        data: monthly.map(function(m) { return m.net_income < 0 ? -m.net_income : 0; })
    });

    // 貸方スタック（右）：収益科目を逆順で追加（財務諸表の上位科目がグラフ上段に来るよう）
    revenueAccounts.slice().reverse().forEach(function(acc, i) {
        var colorIdx = revenueAccounts.length - 1 - i;
        datasets.push({
            label: acc.name,
            stack: 'credit',
            backgroundColor: REVENUE_PALETTE[colorIdx % REVENUE_PALETTE.length],
            borderColor: 'rgba(0,0,0,0.15)',
            borderWidth: 0.5,
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
});
