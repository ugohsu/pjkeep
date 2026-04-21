# -*- coding: utf-8 -*-
from calendar import monthrange as cal_monthrange
from collections import defaultdict
from datetime import date as dt
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from helpers import get_db, db_required, write_required

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.get('/dashboard')
@login_required
@db_required
def dashboard():
    return render_template('dashboard.html')


@dashboard_bp.get('/api/dashboard/pl_monthly')
@login_required
@db_required
def api_dashboard_pl_monthly():
    range_param = request.args.get('range', '6m')
    db = get_db()

    # 期間フィルタの起点月を計算
    if range_param in ('3m', '6m', '12m'):
        n = {'3m': 3, '6m': 6, '12m': 12}[range_param]
        today = dt.today()
        year, month = today.year, today.month
        month -= (n - 1)
        while month <= 0:
            month += 12
            year -= 1
        start_ym = f'{year:04d}-{month:02d}'
    else:
        start_ym = None

    accounts = db.execute(
        'SELECT id, name, element FROM accounts '
        'WHERE element IN ("revenues","expenses") '
        'ORDER BY element, sort_order, name'
    ).fetchall()
    acc_element = {a['id']: a['element'] for a in accounts}

    if start_ym:
        pl_rows = db.execute('''
            SELECT strftime('%Y-%m', j.entry_date) as ym, j.account_id, a.element,
                   SUM(CASE WHEN j.debit_credit='debit'  THEN j.amount ELSE 0 END) as dt,
                   SUM(CASE WHEN j.debit_credit='credit' THEN j.amount ELSE 0 END) as ct
            FROM journal j JOIN accounts a ON j.account_id = a.id
            WHERE a.element IN ('revenues','expenses')
              AND strftime('%Y-%m', j.entry_date) >= ?
            GROUP BY ym, j.account_id ORDER BY ym
        ''', (start_ym,)).fetchall()
    else:
        pl_rows = db.execute('''
            SELECT strftime('%Y-%m', j.entry_date) as ym, j.account_id, a.element,
                   SUM(CASE WHEN j.debit_credit='debit'  THEN j.amount ELSE 0 END) as dt,
                   SUM(CASE WHEN j.debit_credit='credit' THEN j.amount ELSE 0 END) as ct
            FROM journal j JOIN accounts a ON j.account_id = a.id
            WHERE a.element IN ('revenues','expenses')
            GROUP BY ym, j.account_id ORDER BY ym
        ''').fetchall()

    monthly_pl = defaultdict(dict)
    months_set = set()
    for r in pl_rows:
        amt = (r['ct'] - r['dt']) if r['element'] == 'revenues' else (r['dt'] - r['ct'])
        monthly_pl[r['ym']][r['account_id']] = amt
        months_set.add(r['ym'])

    months = sorted(months_set)
    monthly = []
    for ym in months:
        pl_data = monthly_pl.get(ym, {})
        month_rev = sum(v for acc_id, v in pl_data.items() if acc_element.get(acc_id) == 'revenues')
        month_exp = sum(v for acc_id, v in pl_data.items() if acc_element.get(acc_id) == 'expenses')
        monthly.append({
            'ym': ym,
            'total_revenues': month_rev,
            'total_expenses': month_exp,
            'net_income': month_rev - month_exp,
            'by_account': {str(acc_id): amt for acc_id, amt in pl_data.items()}
        })

    return jsonify({
        'accounts': [{'id': a['id'], 'name': a['name'], 'element': a['element']}
                     for a in accounts],
        'monthly': monthly
    })


@dashboard_bp.get('/api/dashboard/equity_monthly')
@login_required
@db_required
def api_dashboard_equity_monthly():
    range_param = request.args.get('range', '12m')
    db = get_db()

    if range_param in ('3m', '6m', '12m'):
        n = {'3m': 3, '6m': 6, '12m': 12}[range_param]
        today = dt.today()
        year, month = today.year, today.month
        month -= (n - 1)
        while month <= 0:
            month += 12
            year -= 1
        start_ym = f'{year:04d}-{month:02d}'
    else:
        start_ym = None

    # 仕訳が存在する全月を昇順で取得
    all_months = [r['ym'] for r in db.execute(
        "SELECT DISTINCT strftime('%Y-%m', entry_date) as ym FROM journal ORDER BY ym"
    ).fetchall()]

    if not all_months:
        return jsonify({'monthly': []})

    # 純資産科目の月次増減（累計のために全期間取得）
    equity_rows = db.execute('''
        SELECT strftime('%Y-%m', j.entry_date) as ym, j.account_id,
               SUM(CASE WHEN j.debit_credit='debit'  THEN j.amount ELSE 0 END) as dt,
               SUM(CASE WHEN j.debit_credit='credit' THEN j.amount ELSE 0 END) as ct
        FROM journal j JOIN accounts a ON j.account_id = a.id
        WHERE a.element = 'equity'
        GROUP BY ym, j.account_id ORDER BY ym
    ''').fetchall()

    equity_incremental = defaultdict(dict)
    for r in equity_rows:
        equity_incremental[r['ym']][r['account_id']] = r['ct'] - r['dt']

    # 収益・費用の月次合計（累計のために全期間取得）
    pl_rows = db.execute('''
        SELECT strftime('%Y-%m', j.entry_date) as ym, a.element,
               SUM(CASE WHEN j.debit_credit='debit'  THEN j.amount ELSE 0 END) as dt,
               SUM(CASE WHEN j.debit_credit='credit' THEN j.amount ELSE 0 END) as ct
        FROM journal j JOIN accounts a ON j.account_id = a.id
        WHERE a.element IN ('revenues','expenses')
        GROUP BY ym, a.element ORDER BY ym
    ''').fetchall()

    monthly_net = defaultdict(int)
    for r in pl_rows:
        if r['element'] == 'revenues':
            monthly_net[r['ym']] += r['ct'] - r['dt']
        else:
            monthly_net[r['ym']] -= r['dt'] - r['ct']

    # 月ごとの累計純資産合計を計算
    # 純資産合計 = 純資産科目の累計残高 + 累計純損益（振替は相殺されるため不要）
    running_equity = defaultdict(int)
    running_net = 0
    cum_equity = {}
    for ym in all_months:
        for acc_id, delta in equity_incremental.get(ym, {}).items():
            running_equity[acc_id] += delta
        running_net += monthly_net.get(ym, 0)
        cum_equity[ym] = sum(running_equity.values()) + running_net

    display_months = [ym for ym in all_months if not start_ym or ym >= start_ym]

    return jsonify({
        'monthly': [{'ym': ym, 'total_equity': cum_equity[ym]} for ym in display_months]
    })


# ========== 予算実績ウィジェット ==========

@dashboard_bp.get('/api/dashboard/budget_widgets')
@login_required
@db_required
def api_budget_widgets_list():
    db = get_db()
    widgets = db.execute(
        'SELECT id, title, sort_order FROM budget_widgets WHERE user_id=? ORDER BY sort_order, id',
        (current_user.id,)
    ).fetchall()
    return jsonify([dict(w) for w in widgets])


@dashboard_bp.post('/api/dashboard/budget_widgets')
@login_required
@db_required
@write_required
def api_budget_widgets_create():
    data = request.json or {}
    title = data.get('title', '').strip()
    accounts = data.get('accounts', [])
    if not title:
        return jsonify({'error': 'タイトルは必須です'}), 400
    if not accounts:
        return jsonify({'error': '科目を1つ以上指定してください'}), 400

    db = get_db()
    max_sort = db.execute(
        'SELECT COALESCE(MAX(sort_order), 0) FROM budget_widgets WHERE user_id=?',
        (current_user.id,)
    ).fetchone()[0]

    cur = db.execute(
        'INSERT INTO budget_widgets (user_id, title, sort_order) VALUES (?,?,?)',
        (current_user.id, title, max_sort + 1)
    )
    widget_id = cur.lastrowid

    for i, acc in enumerate(accounts):
        db.execute(
            'INSERT INTO budget_widget_accounts (widget_id, account_id, default_amount, sort_order) '
            'VALUES (?,?,?,?)',
            (widget_id, int(acc['account_id']), int(acc.get('default_amount', 0)), i)
        )

    db.commit()
    return jsonify({'id': widget_id})


@dashboard_bp.get('/api/dashboard/budget_widgets/<int:widget_id>')
@login_required
@db_required
def api_budget_widget_get(widget_id):
    db = get_db()
    widget = db.execute(
        'SELECT id, title FROM budget_widgets WHERE id=? AND user_id=?',
        (widget_id, current_user.id)
    ).fetchone()
    if not widget:
        return jsonify({'error': 'Not found'}), 404

    accounts = db.execute(
        '''SELECT bwa.id, bwa.account_id, bwa.default_amount, bwa.sort_order, a.name
           FROM budget_widget_accounts bwa
           JOIN accounts a ON a.id = bwa.account_id
           WHERE bwa.widget_id=? ORDER BY bwa.sort_order''',
        (widget_id,)
    ).fetchall()

    wa_ids = [a['id'] for a in accounts]
    overrides = []
    if wa_ids:
        ov_rows = db.execute(
            f'''SELECT bmo.widget_account_id, bmo.year_month, bmo.amount, bwa.account_id
                FROM budget_monthly_overrides bmo
                JOIN budget_widget_accounts bwa ON bwa.id = bmo.widget_account_id
                WHERE bmo.widget_account_id IN ({",".join("?" * len(wa_ids))})
                ORDER BY bmo.year_month''',
            wa_ids
        ).fetchall()
        overrides = [dict(r) for r in ov_rows]

    return jsonify({
        'id': widget['id'],
        'title': widget['title'],
        'accounts': [dict(a) for a in accounts],
        'overrides': overrides
    })


@dashboard_bp.put('/api/dashboard/budget_widgets/<int:widget_id>')
@login_required
@db_required
@write_required
def api_budget_widget_update(widget_id):
    db = get_db()
    widget = db.execute(
        'SELECT id FROM budget_widgets WHERE id=? AND user_id=?',
        (widget_id, current_user.id)
    ).fetchone()
    if not widget:
        return jsonify({'error': 'Not found'}), 404

    data = request.json or {}
    title = data.get('title', '').strip()
    accounts = data.get('accounts', [])
    overrides = data.get('overrides', [])

    if not title:
        return jsonify({'error': 'タイトルは必須です'}), 400
    if not accounts:
        return jsonify({'error': '科目を1つ以上指定してください'}), 400

    db.execute('UPDATE budget_widgets SET title=? WHERE id=?', (title, widget_id))

    # accounts を差し替え（CASCADE で overrides も削除される）
    db.execute('DELETE FROM budget_widget_accounts WHERE widget_id=?', (widget_id,))
    wa_id_map = {}
    for i, acc in enumerate(accounts):
        acc_id = int(acc['account_id'])
        cur = db.execute(
            'INSERT INTO budget_widget_accounts (widget_id, account_id, default_amount, sort_order) '
            'VALUES (?,?,?,?)',
            (widget_id, acc_id, int(acc.get('default_amount', 0)), i)
        )
        wa_id_map[acc_id] = cur.lastrowid

    for ov in overrides:
        acc_id = int(ov.get('account_id', 0))
        wa_id = wa_id_map.get(acc_id)
        ym = str(ov.get('year_month', '')).strip()
        amount = int(ov.get('amount', 0))
        if wa_id and ym:
            db.execute(
                'INSERT OR REPLACE INTO budget_monthly_overrides '
                '(widget_account_id, year_month, amount) VALUES (?,?,?)',
                (wa_id, ym, amount)
            )

    db.commit()
    return jsonify({'ok': True})


@dashboard_bp.delete('/api/dashboard/budget_widgets/<int:widget_id>')
@login_required
@db_required
@write_required
def api_budget_widget_delete(widget_id):
    db = get_db()
    widget = db.execute(
        'SELECT id FROM budget_widgets WHERE id=? AND user_id=?',
        (widget_id, current_user.id)
    ).fetchone()
    if not widget:
        return jsonify({'error': 'Not found'}), 404
    db.execute('DELETE FROM budget_widgets WHERE id=?', (widget_id,))
    db.commit()
    return jsonify({'ok': True})


@dashboard_bp.get('/api/dashboard/budget_widgets/<int:widget_id>/data')
@login_required
@db_required
def api_budget_widget_data(widget_id):
    db = get_db()
    widget = db.execute(
        'SELECT id FROM budget_widgets WHERE id=? AND user_id=?',
        (widget_id, current_user.id)
    ).fetchone()
    if not widget:
        return jsonify({'error': 'Not found'}), 404

    range_param = request.args.get('range', '3m')
    today = dt.today()
    current_ym = f'{today.year:04d}-{today.month:02d}'

    if range_param in ('3m', '6m', '12m'):
        n = {'3m': 3, '6m': 6, '12m': 12}[range_param]
        y, m = today.year, today.month
        m -= (n - 1)
        while m <= 0:
            m += 12
            y -= 1
        start_ym = f'{y:04d}-{m:02d}'
    else:
        first = db.execute(
            "SELECT MIN(strftime('%Y-%m', entry_date)) as ym FROM journal"
        ).fetchone()
        start_ym = (first['ym'] if first and first['ym'] else current_ym)

    # start_ym ～ current_ym の月リストを生成
    months = []
    wy, wm = int(start_ym[:4]), int(start_ym[5:7])
    cy, cm = today.year, today.month
    while (wy, wm) <= (cy, cm):
        months.append(f'{wy:04d}-{wm:02d}')
        wm += 1
        if wm > 12:
            wm = 1
            wy += 1

    widget_accounts = db.execute(
        '''SELECT bwa.id, bwa.account_id, bwa.default_amount, bwa.sort_order, a.name
           FROM budget_widget_accounts bwa
           JOIN accounts a ON a.id = bwa.account_id
           WHERE bwa.widget_id=? ORDER BY bwa.sort_order''',
        (widget_id,)
    ).fetchall()

    if not widget_accounts:
        return jsonify({'accounts': [], 'monthly': []})

    wa_ids = [wa['id'] for wa in widget_accounts]
    acc_ids = [wa['account_id'] for wa in widget_accounts]

    ov_rows = db.execute(
        f'''SELECT widget_account_id, year_month, amount FROM budget_monthly_overrides
            WHERE widget_account_id IN ({",".join("?" * len(wa_ids))})''',
        wa_ids
    ).fetchall()
    overrides = {(r['widget_account_id'], r['year_month']): r['amount'] for r in ov_rows}

    if months and acc_ids:
        actual_rows = db.execute(
            f'''SELECT strftime('%Y-%m', j.entry_date) as ym, j.account_id,
                       SUM(CASE WHEN j.debit_credit='debit'  THEN j.amount ELSE 0 END) as dt,
                       SUM(CASE WHEN j.debit_credit='credit' THEN j.amount ELSE 0 END) as ct
                FROM journal j
                WHERE j.account_id IN ({",".join("?" * len(acc_ids))})
                  AND strftime('%Y-%m', j.entry_date) >= ?
                  AND strftime('%Y-%m', j.entry_date) <= ?
                GROUP BY ym, j.account_id''',
            (*acc_ids, months[0], months[-1])
        ).fetchall()
    else:
        actual_rows = []

    actual = defaultdict(dict)
    for r in actual_rows:
        actual[r['ym']][r['account_id']] = max(0, r['dt'] - r['ct'])

    monthly = []
    for ym in months:
        y_int, m_int = int(ym[:4]), int(ym[5:7])
        prorate = (today.day / cal_monthrange(y_int, m_int)[1]) if ym == current_ym else 1.0

        by_actual, by_budget = {}, {}
        for wa in widget_accounts:
            aid, waid = wa['account_id'], wa['id']
            by_actual[aid] = actual.get(ym, {}).get(aid, 0)
            base = overrides.get((waid, ym), wa['default_amount'])
            by_budget[aid] = round(base * prorate)

        monthly.append({
            'ym': ym,
            'actual_total': sum(by_actual.values()),
            'budget_total': sum(by_budget.values()),
            'by_account_actual': {str(k): v for k, v in by_actual.items()},
            'by_account_budget': {str(k): v for k, v in by_budget.items()},
        })

    return jsonify({
        'accounts': [{'id': wa['account_id'], 'name': wa['name']} for wa in widget_accounts],
        'monthly': monthly
    })
