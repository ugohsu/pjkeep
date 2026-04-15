# -*- coding: utf-8 -*-
from collections import defaultdict
from datetime import date as dt
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from helpers import get_db, db_required

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
