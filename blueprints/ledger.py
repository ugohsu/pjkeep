# -*- coding: utf-8 -*-
from collections import defaultdict
from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required
from helpers import get_db, db_required, tsv_response

ledger_bp = Blueprint('ledger', __name__)

_DEBIT_NORMAL = ('assets', 'expenses')


@ledger_bp.get('/ledger')
@login_required
@db_required
def ledger():
    return render_template('ledger.html')


def _build_ledger(db, account_id, from_date, to_date):
    """
    元帳データを構築して返す。

    戻り値: (data_dict, None) または (None, 'not_found')
    """
    acc = db.execute(
        'SELECT id, name, element FROM accounts WHERE id=?', (account_id,)
    ).fetchone()
    if not acc:
        return None, 'not_found'

    is_debit_normal = acc['element'] in _DEBIT_NORMAL

    # --- 前期残高（from_date より前の累計） ---
    if from_date:
        ob = db.execute('''
            SELECT COALESCE(SUM(
                CASE WHEN debit_credit='debit' THEN amount ELSE -amount END
            ), 0) as net
            FROM journal WHERE account_id=? AND entry_date < ?
        ''', (account_id, from_date)).fetchone()
        raw = ob['net'] or 0
        opening_balance = raw if is_debit_normal else -raw
    else:
        opening_balance = 0

    # --- 対象期間の仕訳行 ---
    sql = '''
        SELECT j.id, j.entry_date, j.transaction_id,
               j.debit_credit, j.amount, j.note
        FROM journal j
        WHERE j.account_id = ?
    '''
    params = [account_id]
    if from_date:
        sql += ' AND j.entry_date >= ?'
        params.append(from_date)
    if to_date:
        sql += ' AND j.entry_date <= ?'
        params.append(to_date)
    sql += ' ORDER BY j.entry_date, j.id'

    rows = db.execute(sql, params).fetchall()

    # --- 相手科目を一括取得（N+1 回避） ---
    tids = list(dict.fromkeys(r['transaction_id'] for r in rows))
    counterpart_map = defaultdict(list)
    if tids:
        ph = ','.join('?' * len(tids))
        cp_rows = db.execute(f'''
            SELECT j.transaction_id, a.name
            FROM journal j JOIN accounts a ON j.account_id = a.id
            WHERE j.transaction_id IN ({ph}) AND j.account_id != ?
            ORDER BY j.id
        ''', tids + [account_id]).fetchall()
        for r in cp_rows:
            counterpart_map[r['transaction_id']].append(r['name'])

    # --- 残高を累積しながらエントリ構築 ---
    balance = opening_balance
    entries = []
    for row in rows:
        raw_delta = row['amount'] if row['debit_credit'] == 'debit' else -row['amount']
        delta = raw_delta if is_debit_normal else -raw_delta
        balance += delta

        # 相手科目（重複除去・順序保持）
        counterparts = list(dict.fromkeys(counterpart_map.get(row['transaction_id'], [])))

        entries.append({
            'entry_date':     row['entry_date'],
            'transaction_id': row['transaction_id'],
            'note':           row['note'] or '',
            'debit':          row['amount'] if row['debit_credit'] == 'debit'  else 0,
            'credit':         row['amount'] if row['debit_credit'] == 'credit' else 0,
            'balance':        balance,
            'counterparts':   counterparts,
        })

    return {
        'account':         {'id': acc['id'], 'name': acc['name'], 'element': acc['element']},
        'from_date':       from_date,
        'to_date':         to_date,
        'opening_balance': opening_balance,
        'entries':         entries,
    }, None


@ledger_bp.get('/api/ledger')
@login_required
@db_required
def api_ledger():
    account_id = request.args.get('account_id', type=int)
    from_date  = request.args.get('from', '').strip()
    to_date    = request.args.get('to',   '').strip()

    if not account_id:
        return jsonify({'error': '科目を指定してください'}), 400

    data, err = _build_ledger(get_db(), account_id, from_date, to_date)
    if err:
        return jsonify({'error': '科目が見つかりません'}), 404
    return jsonify(data)


@ledger_bp.get('/api/export/ledger')
@login_required
@db_required
def api_export_ledger():
    account_id = request.args.get('account_id', type=int)
    from_date  = request.args.get('from', '').strip()
    to_date    = request.args.get('to',   '').strip()

    if not account_id:
        return jsonify({'error': '科目を指定してください'}), 400

    db = get_db()
    acc = db.execute('SELECT code FROM accounts WHERE id=?', (account_id,)).fetchone()
    if not acc:
        return jsonify({'error': '科目が見つかりません'}), 404

    data, err = _build_ledger(db, account_id, from_date, to_date)
    if err:
        return jsonify({'error': '科目が見つかりません'}), 404

    headers = ['日付', '備考', '取引番号', '借方', '貸方', '残高', '相手科目']
    rows = []

    if from_date and data['opening_balance'] != 0:
        rows.append([from_date, '（前期残高）', '', '', '', data['opening_balance'], ''])

    for e in data['entries']:
        cps = e['counterparts']
        cp_str = cps[0] if len(cps) == 1 else ('諸口' if cps else '')
        rows.append([
            e['entry_date'],
            e['note'],
            e['transaction_id'],
            e['debit']  or '',
            e['credit'] or '',
            e['balance'],
            cp_str,
        ])

    code = acc['code']
    if from_date or to_date:
        f = from_date or 'start'
        t = to_date   or 'end'
        filename = f'ledger_{code}_{f}_{t}.tsv'
    else:
        filename = f'ledger_{code}_all.tsv'

    return tsv_response(rows, headers, filename)
