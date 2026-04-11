# -*- coding: utf-8 -*-
import calendar
from collections import defaultdict
from datetime import date as dt
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from app import get_db, db_required, tsv_response

report_bp = Blueprint('report', __name__)


@report_bp.get('/report')
@login_required
@db_required
def report():
    return render_template('report.html')


# ---------- report API ----------

@report_bp.get('/api/report/pl')
@login_required
@db_required
def api_report_pl():
    ym = request.args.get('ym') or dt.today().strftime('%Y-%m')
    db = get_db()
    rows = db.execute('''
        SELECT a.id, a.name, a.element, a.sort_order,
               SUM(CASE WHEN j.debit_credit='debit'  THEN j.amount ELSE 0 END) as debit_total,
               SUM(CASE WHEN j.debit_credit='credit' THEN j.amount ELSE 0 END) as credit_total
        FROM journal j
        JOIN accounts a ON j.account_id = a.id
        WHERE a.element IN ('revenues','expenses')
          AND strftime('%Y-%m', j.entry_date) = ?
        GROUP BY a.id
        ORDER BY a.element, a.sort_order, a.name
    ''', (ym,)).fetchall()

    revenues, expenses = [], []
    for row in rows:
        amount = (row['credit_total'] - row['debit_total']) if row['element'] == 'revenues' \
                 else (row['debit_total'] - row['credit_total'])
        item = {'id': row['id'], 'name': row['name'], 'amount': amount}
        (revenues if row['element'] == 'revenues' else expenses).append(item)

    total_rev = sum(r['amount'] for r in revenues)
    total_exp = sum(e['amount'] for e in expenses)
    return jsonify({
        'ym': ym,
        'revenues': revenues, 'expenses': expenses,
        'total_revenues': total_rev, 'total_expenses': total_exp,
        'net_income': total_rev - total_exp
    })


@report_bp.get('/api/report/bs')
@login_required
@db_required
def api_report_bs():
    ym = request.args.get('ym') or dt.today().strftime('%Y-%m')
    year, month = int(ym[:4]), int(ym[5:7])
    last_day = calendar.monthrange(year, month)[1]
    end_date = f'{ym}-{last_day:02d}'
    db = get_db()

    bs_rows = db.execute('''
        SELECT a.id, a.name, a.element, a.sort_order,
               SUM(CASE WHEN j.debit_credit='debit'  THEN j.amount ELSE 0 END) as debit_total,
               SUM(CASE WHEN j.debit_credit='credit' THEN j.amount ELSE 0 END) as credit_total
        FROM journal j
        JOIN accounts a ON j.account_id = a.id
        WHERE a.element IN ('assets','liabilities','equity')
          AND j.entry_date <= ?
        GROUP BY a.id
        ORDER BY a.element, a.sort_order, a.name
    ''', (end_date,)).fetchall()

    pl_row = db.execute('''
        SELECT
            SUM(CASE WHEN a.element='revenues' AND j.debit_credit='credit' THEN  j.amount
                     WHEN a.element='revenues' AND j.debit_credit='debit'  THEN -j.amount
                     ELSE 0 END) as revenues,
            SUM(CASE WHEN a.element='expenses' AND j.debit_credit='debit'  THEN  j.amount
                     WHEN a.element='expenses' AND j.debit_credit='credit' THEN -j.amount
                     ELSE 0 END) as expenses
        FROM journal j
        JOIN accounts a ON j.account_id = a.id
        WHERE a.element IN ('revenues','expenses') AND j.entry_date <= ?
    ''', (end_date,)).fetchone()

    assets, liabilities, equity = [], [], []
    for row in bs_rows:
        amount = (row['debit_total'] - row['credit_total']) if row['element'] == 'assets' \
                 else (row['credit_total'] - row['debit_total'])
        item = {'id': row['id'], 'name': row['name'], 'amount': amount}
        {'assets': assets, 'liabilities': liabilities, 'equity': equity}[row['element']].append(item)

    cum_rev = pl_row['revenues'] or 0
    cum_exp = pl_row['expenses'] or 0
    cum_net = cum_rev - cum_exp

    return jsonify({
        'ym': ym,
        'assets': assets, 'liabilities': liabilities, 'equity': equity,
        'cumulative_net_income': cum_net,
        'total_assets': sum(a['amount'] for a in assets),
        'total_liabilities': sum(l['amount'] for l in liabilities),
        'total_equity': sum(e['amount'] for e in equity) + cum_net,
    })


@report_bp.get('/api/months')
@login_required
@db_required
def api_months():
    db = get_db()
    rows = db.execute(
        "SELECT DISTINCT strftime('%Y-%m', entry_date) as ym FROM journal ORDER BY ym DESC"
    ).fetchall()
    return jsonify([r['ym'] for r in rows])


# ---------- export ----------

@report_bp.get('/api/export/journal')
@login_required
@db_required
def api_export_journal():
    ym        = request.args.get('ym', '')
    from_date = request.args.get('from', '')
    to_date   = request.args.get('to', '')
    db = get_db()

    if ym:
        rows = db.execute('''
            SELECT j.entry_date, j.note, j.transaction_id, j.debit_credit, a.name, j.amount
            FROM journal j JOIN accounts a ON j.account_id = a.id
            WHERE strftime('%Y-%m', j.entry_date) = ?
            ORDER BY j.entry_date, j.transaction_id, j.debit_credit DESC
        ''', (ym,)).fetchall()
        filename_suffix = ym
    elif from_date and to_date:
        rows = db.execute('''
            SELECT j.entry_date, j.note, j.transaction_id, j.debit_credit, a.name, j.amount
            FROM journal j JOIN accounts a ON j.account_id = a.id
            WHERE j.entry_date >= ? AND j.entry_date <= ?
            ORDER BY j.entry_date, j.transaction_id, j.debit_credit DESC
        ''', (from_date, to_date)).fetchall()
        filename_suffix = f'{from_date}_{to_date}'
    else:
        rows = db.execute('''
            SELECT j.entry_date, j.note, j.transaction_id, j.debit_credit, a.name, j.amount
            FROM journal j JOIN accounts a ON j.account_id = a.id
            ORDER BY j.entry_date, j.transaction_id, j.debit_credit DESC
        ''').fetchall()
        filename_suffix = 'all'

    tid_map = {}
    seq = 0
    data = []
    for row in rows:
        tid = row[2]
        if tid not in tid_map:
            seq += 1
            tid_map[tid] = seq
        dc = '借方' if row[3] == 'debit' else '貸方'
        data.append([row[0], row[1] or '', tid_map[tid], dc, row[4], row[5]])

    return tsv_response(data, ['取引日', '備考', '取引番号', '借貸', '勘定科目', '金額'],
                        f'journal_{filename_suffix}.tsv')


@report_bp.get('/api/export/report')
@login_required
@db_required
def api_export_report():
    from_date = request.args.get('from', '')
    to_date   = request.args.get('to', '')
    ym        = request.args.get('ym') or dt.today().strftime('%Y-%m')
    db = get_db()

    if from_date and to_date:
        pl_rows = db.execute('''
            SELECT a.name, a.element,
                   SUM(CASE WHEN j.debit_credit='debit'  THEN j.amount ELSE 0 END) as dt,
                   SUM(CASE WHEN j.debit_credit='credit' THEN j.amount ELSE 0 END) as ct
            FROM journal j JOIN accounts a ON j.account_id=a.id
            WHERE a.element IN ('revenues','expenses')
              AND j.entry_date >= ? AND j.entry_date <= ?
            GROUP BY a.id ORDER BY a.element, a.sort_order, a.name
        ''', (from_date, to_date)).fetchall()
        bs_rows = db.execute('''
            SELECT a.name, a.element,
                   SUM(CASE WHEN j.debit_credit='debit'  THEN j.amount ELSE 0 END) as dt,
                   SUM(CASE WHEN j.debit_credit='credit' THEN j.amount ELSE 0 END) as ct
            FROM journal j JOIN accounts a ON j.account_id=a.id
            WHERE a.element IN ('assets','liabilities','equity') AND j.entry_date <= ?
            GROUP BY a.id ORDER BY a.element, a.sort_order, a.name
        ''', (to_date,)).fetchall()
        pl_cum_row = db.execute('''
            SELECT
                SUM(CASE WHEN a.element='revenues' AND j.debit_credit='credit' THEN  j.amount
                         WHEN a.element='revenues' AND j.debit_credit='debit'  THEN -j.amount ELSE 0 END) as rev,
                SUM(CASE WHEN a.element='expenses' AND j.debit_credit='debit'  THEN  j.amount
                         WHEN a.element='expenses' AND j.debit_credit='credit' THEN -j.amount ELSE 0 END) as exp
            FROM journal j JOIN accounts a ON j.account_id=a.id
            WHERE a.element IN ('revenues','expenses') AND j.entry_date <= ?
        ''', (to_date,)).fetchone()
        label_pl = f'{from_date}〜{to_date}'
        label_bs = f'{to_date}時点（累計）'
        filename = f'report_{from_date}_{to_date}.tsv'
    else:
        year, month = int(ym[:4]), int(ym[5:7])
        last_day = calendar.monthrange(year, month)[1]
        end_date = f'{ym}-{last_day:02d}'
        pl_rows = db.execute('''
            SELECT a.name, a.element,
                   SUM(CASE WHEN j.debit_credit='debit'  THEN j.amount ELSE 0 END) as dt,
                   SUM(CASE WHEN j.debit_credit='credit' THEN j.amount ELSE 0 END) as ct
            FROM journal j JOIN accounts a ON j.account_id=a.id
            WHERE a.element IN ('revenues','expenses') AND strftime('%Y-%m', j.entry_date)=?
            GROUP BY a.id ORDER BY a.element, a.sort_order, a.name
        ''', (ym,)).fetchall()
        bs_rows = db.execute('''
            SELECT a.name, a.element,
                   SUM(CASE WHEN j.debit_credit='debit'  THEN j.amount ELSE 0 END) as dt,
                   SUM(CASE WHEN j.debit_credit='credit' THEN j.amount ELSE 0 END) as ct
            FROM journal j JOIN accounts a ON j.account_id=a.id
            WHERE a.element IN ('assets','liabilities','equity') AND j.entry_date<=?
            GROUP BY a.id ORDER BY a.element, a.sort_order, a.name
        ''', (end_date,)).fetchall()
        pl_cum_row = db.execute('''
            SELECT
                SUM(CASE WHEN a.element='revenues' AND j.debit_credit='credit' THEN  j.amount
                         WHEN a.element='revenues' AND j.debit_credit='debit'  THEN -j.amount ELSE 0 END) as rev,
                SUM(CASE WHEN a.element='expenses' AND j.debit_credit='debit'  THEN  j.amount
                         WHEN a.element='expenses' AND j.debit_credit='credit' THEN -j.amount ELSE 0 END) as exp
            FROM journal j JOIN accounts a ON j.account_id=a.id
            WHERE a.element IN ('revenues','expenses') AND j.entry_date<=?
        ''', (end_date,)).fetchone()
        label_pl = ym
        label_bs = f'{ym}末時点（累計）'
        filename = f'report_{ym}.tsv'

    ELEM_JA = {'revenues':'収益','expenses':'費用','assets':'資産','liabilities':'負債','equity':'純資産'}
    data = []
    data.append([f'【損益計算書】{label_pl}', '', ''])
    data.append(['区分', '勘定科目', '金額'])
    rev_total = exp_total = 0
    for r in pl_rows:
        amt = (r['ct'] - r['dt']) if r['element'] == 'revenues' else (r['dt'] - r['ct'])
        data.append([ELEM_JA[r['element']], r['name'], amt])
        if r['element'] == 'revenues': rev_total += amt
        else: exp_total += amt
    data.append(['収益合計', '', rev_total])
    data.append(['費用合計', '', exp_total])
    data.append(['当期純利益', '', rev_total - exp_total])
    data.append(['', '', ''])

    cum_net = (pl_cum_row['rev'] or 0) - (pl_cum_row['exp'] or 0)
    data.append([f'【貸借対照表】{label_bs}', '', ''])
    data.append(['区分', '勘定科目', '金額'])
    totals = {'assets': 0, 'liabilities': 0, 'equity': 0}
    for r in bs_rows:
        amt = (r['dt'] - r['ct']) if r['element'] == 'assets' else (r['ct'] - r['dt'])
        data.append([ELEM_JA[r['element']], r['name'], amt])
        totals[r['element']] += amt
    data.append(['資産合計', '', totals['assets']])
    data.append(['負債合計', '', totals['liabilities']])
    data.append(['純資産', '累計純損益', cum_net])
    data.append(['純資産合計', '', totals['equity'] + cum_net])

    return tsv_response(data, [], filename)


@report_bp.get('/api/export/report/monthly')
@login_required
@db_required
def api_export_report_monthly():
    db = get_db()
    accounts = db.execute(
        'SELECT id, name, element, sort_order FROM accounts ORDER BY element, sort_order, name'
    ).fetchall()
    acc_element = {a['id']: a['element'] for a in accounts}

    months = [r['ym'] for r in db.execute(
        "SELECT DISTINCT strftime('%Y-%m', entry_date) as ym FROM journal ORDER BY ym"
    ).fetchall()]

    if not months:
        return tsv_response([], ['決算月'], 'report_monthly.tsv')

    pl_rows = db.execute('''
        SELECT strftime('%Y-%m', j.entry_date) as ym, j.account_id, a.element,
               SUM(CASE WHEN j.debit_credit='debit'  THEN j.amount ELSE 0 END) as dt,
               SUM(CASE WHEN j.debit_credit='credit' THEN j.amount ELSE 0 END) as ct
        FROM journal j JOIN accounts a ON j.account_id = a.id
        WHERE a.element IN ('revenues','expenses')
        GROUP BY ym, j.account_id ORDER BY ym
    ''').fetchall()
    monthly_pl = defaultdict(dict)
    for r in pl_rows:
        amt = (r['ct'] - r['dt']) if r['element'] == 'revenues' else (r['dt'] - r['ct'])
        monthly_pl[r['ym']][r['account_id']] = amt

    bs_rows = db.execute('''
        SELECT strftime('%Y-%m', j.entry_date) as ym, j.account_id, a.element,
               SUM(CASE WHEN j.debit_credit='debit'  THEN j.amount ELSE 0 END) as dt,
               SUM(CASE WHEN j.debit_credit='credit' THEN j.amount ELSE 0 END) as ct
        FROM journal j JOIN accounts a ON j.account_id = a.id
        WHERE a.element IN ('assets','liabilities','equity')
        GROUP BY ym, j.account_id ORDER BY ym
    ''').fetchall()
    bs_incremental = defaultdict(dict)
    for r in bs_rows:
        amt = (r['dt'] - r['ct']) if r['element'] == 'assets' else (r['ct'] - r['dt'])
        bs_incremental[r['ym']][r['account_id']] = amt

    running = defaultdict(int)
    cum_bs = {}
    for ym in months:
        for acc_id, delta in bs_incremental.get(ym, {}).items():
            running[acc_id] += delta
        cum_bs[ym] = dict(running)

    running_net = 0
    cum_net = {}
    for ym in months:
        pl_data = monthly_pl.get(ym, {})
        month_rev = sum(v for acc_id, v in pl_data.items() if acc_element.get(acc_id) == 'revenues')
        month_exp = sum(v for acc_id, v in pl_data.items() if acc_element.get(acc_id) == 'expenses')
        running_net += (month_rev - month_exp)
        cum_net[ym] = running_net

    headers = ['決算月', '決算日', '当期純利益',
               '資産合計', '負債合計', '純資産合計',
               '収益合計', '費用合計', '累計純損益'] + [a['name'] for a in accounts]
    data = []
    for ym in months:
        year, month = int(ym[:4]), int(ym[5:7])
        last_day = calendar.monthrange(year, month)[1]
        end_date = f'{year}/{month:02d}/{last_day:02d}'

        pl_data = monthly_pl.get(ym, {})
        month_rev = sum(v for acc_id, v in pl_data.items() if acc_element.get(acc_id) == 'revenues')
        month_exp = sum(v for acc_id, v in pl_data.items() if acc_element.get(acc_id) == 'expenses')

        bs_data = cum_bs.get(ym, {})
        total_assets = sum(v for acc_id, v in bs_data.items() if acc_element.get(acc_id) == 'assets')
        total_liab   = sum(v for acc_id, v in bs_data.items() if acc_element.get(acc_id) == 'liabilities')
        total_equity = sum(v for acc_id, v in bs_data.items() if acc_element.get(acc_id) == 'equity') + cum_net.get(ym, 0)

        acc_values = [
            pl_data.get(a['id'], 0) if a['element'] in ('revenues', 'expenses')
            else bs_data.get(a['id'], 0)
            for a in accounts
        ]
        data.append([f'{year}{month:02d}', end_date, month_rev - month_exp,
                     total_assets, total_liab, total_equity,
                     month_rev, month_exp, cum_net.get(ym, 0)] + acc_values)

    return tsv_response(data, headers, f'report_monthly_{months[0]}_{months[-1]}.tsv')
