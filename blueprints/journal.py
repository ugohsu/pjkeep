# -*- coding: utf-8 -*-
import uuid
from datetime import date as dt, timedelta
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from helpers import get_db, db_required, write_required

journal_bp = Blueprint('journal', __name__)


# ---------- pages ----------

@journal_bp.get('/entry')
@login_required
@db_required
def entry():
    return render_template('entry.html')


@journal_bp.get('/journal')
@login_required
@db_required
def journal():
    return render_template('journal.html')


@journal_bp.get('/import')
@login_required
@db_required
def import_page():
    return render_template('import.html')


# ---------- journal API ----------

@journal_bp.get('/api/journal')
@login_required
@db_required
def api_journal_list():
    ym = request.args.get('ym', '')
    db = get_db()
    if ym:
        rows = db.execute('''
            SELECT j.id, j.transaction_id, j.entry_date, j.debit_credit, j.amount, j.note,
                   a.id as account_id, a.name as account_name, a.element
            FROM journal j
            JOIN accounts a ON j.account_id = a.id
            WHERE strftime('%Y-%m', j.entry_date) = ?
            ORDER BY j.entry_date, j.transaction_id, j.debit_credit DESC
        ''', (ym,)).fetchall()
    else:
        rows = db.execute('''
            SELECT j.id, j.transaction_id, j.entry_date, j.debit_credit, j.amount, j.note,
                   a.id as account_id, a.name as account_name, a.element
            FROM journal j
            JOIN accounts a ON j.account_id = a.id
            ORDER BY j.entry_date DESC, j.transaction_id, j.debit_credit DESC
            LIMIT 200
        ''').fetchall()

    transactions = {}
    order = []
    for row in rows:
        tid = row['transaction_id']
        if tid not in transactions:
            transactions[tid] = {
                'transaction_id': tid,
                'entry_date': row['entry_date'],
                'note': row['note'] or '',
                'lines': []
            }
            order.append(tid)
        transactions[tid]['lines'].append({
            'id': row['id'],
            'account_id': row['account_id'],
            'account_name': row['account_name'],
            'element': row['element'],
            'debit_credit': row['debit_credit'],
            'amount': row['amount'],
        })
    return jsonify([transactions[tid] for tid in order])


@journal_bp.post('/api/journal')
@login_required
@db_required
@write_required
def api_journal_create():
    data = request.json or {}
    entry_date = data.get('entry_date', '').strip()
    note = data.get('note', '').strip()
    lines = data.get('lines', [])
    if not entry_date:
        return jsonify({'error': '取引日は必須です'}), 400
    if len(lines) < 2:
        return jsonify({'error': '2行以上入力してください'}), 400
    for line in lines:
        if not line.get('account_id') or not line.get('debit_credit') or not line.get('amount'):
            return jsonify({'error': '各行に勘定科目・借貸・金額が必要です'}), 400
        if line['debit_credit'] not in ('debit', 'credit'):
            return jsonify({'error': '借貸の値が不正です'}), 400
        if int(line['amount']) <= 0:
            return jsonify({'error': '金額は1以上の整数を入力してください'}), 400
    debit_total  = sum(int(l['amount']) for l in lines if l['debit_credit'] == 'debit')
    credit_total = sum(int(l['amount']) for l in lines if l['debit_credit'] == 'credit')
    if debit_total != credit_total:
        return jsonify({'error': f'借方合計 {debit_total:,} と貸方合計 {credit_total:,} が一致しません'}), 400
    tid = str(uuid.uuid4())
    db = get_db()
    try:
        for line in lines:
            db.execute(
                'INSERT INTO journal (transaction_id, entry_date, account_id, debit_credit, amount, note) '
                'VALUES (?,?,?,?,?,?)',
                (tid, entry_date, int(line['account_id']), line['debit_credit'], int(line['amount']), note)
            )
        db.commit()
        return jsonify({'ok': True, 'transaction_id': tid})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500


@journal_bp.get('/api/journal/transaction/<transaction_id>')
@login_required
@db_required
def api_journal_get(transaction_id):
    db = get_db()
    rows = db.execute('''
        SELECT j.id, j.transaction_id, j.entry_date, j.debit_credit, j.amount, j.note,
               a.id as account_id, a.name as account_name, a.element
        FROM journal j
        JOIN accounts a ON j.account_id = a.id
        WHERE j.transaction_id = ?
        ORDER BY j.debit_credit DESC, j.id
    ''', (transaction_id,)).fetchall()
    if not rows:
        return jsonify({'error': '取引が見つかりません'}), 404
    tx = {
        'transaction_id': transaction_id,
        'entry_date': rows[0]['entry_date'],
        'note': rows[0]['note'] or '',
        'lines': [{
            'id': r['id'],
            'account_id': r['account_id'],
            'account_name': r['account_name'],
            'element': r['element'],
            'debit_credit': r['debit_credit'],
            'amount': r['amount'],
        } for r in rows]
    }
    return jsonify(tx)


@journal_bp.delete('/api/journal/transaction/<transaction_id>')
@login_required
@db_required
@write_required
def api_journal_delete(transaction_id):
    db = get_db()
    count = db.execute(
        'SELECT COUNT(*) FROM journal WHERE transaction_id=?', (transaction_id,)
    ).fetchone()[0]
    if count == 0:
        return jsonify({'error': '取引が見つかりません'}), 404
    db.execute('DELETE FROM journal WHERE transaction_id=?', (transaction_id,))
    db.commit()
    return jsonify({'ok': True})


@journal_bp.put('/api/journal/transaction/<transaction_id>')
@login_required
@db_required
@write_required
def api_journal_update(transaction_id):
    db = get_db()
    if not db.execute(
        'SELECT COUNT(*) FROM journal WHERE transaction_id=?', (transaction_id,)
    ).fetchone()[0]:
        return jsonify({'error': '取引が見つかりません'}), 404

    data = request.json or {}
    entry_date = data.get('entry_date', '').strip()
    note = data.get('note', '').strip()
    lines = data.get('lines', [])
    if not entry_date:
        return jsonify({'error': '取引日は必須です'}), 400
    if len(lines) < 2:
        return jsonify({'error': '2行以上入力してください'}), 400
    for line in lines:
        if not line.get('account_id') or not line.get('debit_credit') or not line.get('amount'):
            return jsonify({'error': '各行に勘定科目・借貸・金額が必要です'}), 400
        if line['debit_credit'] not in ('debit', 'credit'):
            return jsonify({'error': '借貸の値が不正です'}), 400
        if int(line['amount']) <= 0:
            return jsonify({'error': '金額は1以上の整数を入力してください'}), 400
    debit_total  = sum(int(l['amount']) for l in lines if l['debit_credit'] == 'debit')
    credit_total = sum(int(l['amount']) for l in lines if l['debit_credit'] == 'credit')
    if debit_total != credit_total:
        return jsonify({'error': f'借方合計 {debit_total:,} と貸方合計 {credit_total:,} が一致しません'}), 400
    try:
        db.execute('DELETE FROM journal WHERE transaction_id=?', (transaction_id,))
        for line in lines:
            db.execute(
                'INSERT INTO journal (transaction_id, entry_date, account_id, debit_credit, amount, note) '
                'VALUES (?,?,?,?,?,?)',
                (transaction_id, entry_date, int(line['account_id']),
                 line['debit_credit'], int(line['amount']), note)
            )
        db.commit()
        return jsonify({'ok': True})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500


# ---------- import API ----------

def detect_duplicate(db, date_val, import_note, lines, n_max_days=7):
    try:
        target_date = dt.fromisoformat(date_val)
    except ValueError:
        return None
    target_amount = sum(l['amount'] for l in lines if l['debit_credit'] == 'debit')
    target_structure = frozenset((l['account_code'], l['debit_credit']) for l in lines)
    date_from = (target_date - timedelta(days=n_max_days)).isoformat()
    date_to   = (target_date + timedelta(days=n_max_days)).isoformat()
    rows = db.execute('''
        SELECT j.transaction_id, j.entry_date, j.debit_credit, j.amount,
               a.code AS account_code, a.name AS account_name, j.note
        FROM journal j
        JOIN accounts a ON a.id = j.account_id
        WHERE j.entry_date BETWEEN ? AND ?
    ''', (date_from, date_to)).fetchall()

    by_txn = {}
    for r in rows:
        tid = r['transaction_id']
        if tid not in by_txn:
            by_txn[tid] = {'date': r['entry_date'], 'note': r['note'], 'lines': []}
        by_txn[tid]['lines'].append({
            'account_code': r['account_code'],
            'account_name': r['account_name'],
            'debit_credit': r['debit_credit'],
            'amount':       r['amount'],
        })

    def jaccard(set_a, set_b):
        union = set_a | set_b
        return len(set_a & set_b) / len(union) if union else 1.0

    target_debit_codes  = {l['account_code'] for l in lines if l['debit_credit'] == 'debit'}
    target_credit_codes = {l['account_code'] for l in lines if l['debit_credit'] == 'credit'}

    best, best_prob = None, 0.0
    for tid, txn in by_txn.items():
        cand_amount = sum(l['amount'] for l in txn['lines'] if l['debit_credit'] == 'debit')
        if cand_amount != target_amount:
            continue
        try:
            cand_date = dt.fromisoformat(txn['date'])
        except ValueError:
            continue

        cand_debit_codes  = {l['account_code'] for l in txn['lines'] if l['debit_credit'] == 'debit'}
        cand_credit_codes = {l['account_code'] for l in txn['lines'] if l['debit_credit'] == 'credit'}
        structure_score = (jaccard(target_debit_codes, cand_debit_codes) +
                           jaccard(target_credit_codes, cand_credit_codes)) / 2
        if structure_score < 0.3:
            continue

        date_diff = abs((target_date - cand_date).days)
        date_score = max(0.0, 1.0 - date_diff / n_max_days)
        i_note = (import_note or '').strip()
        t_note = (txn['note'] or '').strip()
        bonus = 1.1 if (i_note and t_note and (i_note in t_note or t_note in i_note)) else 1.0
        probability = min(1.0, date_score * structure_score * bonus)
        if probability > best_prob:
            best_prob = probability
            best = {
                'probability':    round(probability, 2),
                'date_diff_days': date_diff,
                'matched': {
                    'transaction_id': tid,
                    'date':  txn['date'],
                    'note':  txn['note'] or '',
                    'lines': txn['lines'],
                },
            }
    return best if best_prob > 0.0 else None


@journal_bp.post('/api/import/preview')
@login_required
@db_required
def api_import_preview():
    import re
    data = request.json or {}
    transactions = data.get('transactions', [])
    if not isinstance(transactions, list):
        return jsonify({'ok': False, 'errors': [{'index': -1, 'message': 'transactions は配列である必要があります'}]}), 400

    db = get_db()
    accounts_map = {r['code']: {'id': r['id'], 'name': r['name']}
                    for r in db.execute('SELECT id, name, code FROM accounts').fetchall()}
    date_re = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    result, errors = [], []

    for i, txn in enumerate(transactions):
        txn_errors = []
        date_val = str(txn.get('date', ''))
        if not date_re.match(date_val):
            txn_errors.append(f'date が YYYY-MM-DD 形式ではありません: {date_val!r}')
        lines = txn.get('lines', [])
        if not isinstance(lines, list) or len(lines) < 2:
            txn_errors.append('lines は 2 行以上必要です')
        resolved_lines = []
        debit_total = credit_total = 0
        for j, line in enumerate(lines):
            code = str(line.get('account_code', ''))
            dc = str(line.get('debit_credit', ''))
            amount_raw = line.get('amount')
            if code not in accounts_map:
                txn_errors.append(f'行{j+1}: account_code "{code}" が存在しません')
            if dc not in ('debit', 'credit'):
                txn_errors.append(f'行{j+1}: debit_credit は "debit" または "credit" にしてください')
            try:
                amount_int = int(amount_raw)
                if amount_int < 1:
                    raise ValueError
            except (TypeError, ValueError):
                txn_errors.append(f'行{j+1}: amount は 1 以上の整数にしてください')
                amount_int = 0
            account_name = accounts_map[code]['name'] if code in accounts_map else '(不明)'
            resolved_lines.append({'account_code': code, 'account_name': account_name,
                                    'debit_credit': dc, 'amount': amount_int})
            if dc == 'debit':   debit_total  += amount_int
            elif dc == 'credit': credit_total += amount_int
        if not txn_errors and debit_total != credit_total:
            txn_errors.append(f'借方合計 {debit_total:,} と貸方合計 {credit_total:,} が一致しません')
        duplicate = detect_duplicate(db, date_val, txn.get('note', ''), resolved_lines) \
                    if len(txn_errors) == 0 else None
        result.append({
            'index': i, 'date': txn.get('date', ''), 'note': txn.get('note', ''),
            '_comment': txn.get('_comment', ''), '_confidence': float(txn.get('_confidence', 1.0)),
            'lines': resolved_lines, 'valid': len(txn_errors) == 0, '_duplicate': duplicate,
        })
        for msg in txn_errors:
            errors.append({'index': i, 'message': msg})

    return jsonify({'ok': True, 'transactions': result, 'errors': errors})


@journal_bp.post('/api/import/commit')
@login_required
@db_required
@write_required
def api_import_commit():
    import re
    data = request.json or {}
    transactions = data.get('transactions', [])
    approved_indices = set(data.get('approved_indices', []))
    date_re = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    db = get_db()
    accounts_map = {r['code']: r['id']
                    for r in db.execute('SELECT id, code FROM accounts').fetchall()}
    committed = 0
    try:
        for i, txn in enumerate(transactions):
            if i not in approved_indices:
                continue
            date_val = str(txn.get('date', ''))
            if not date_re.match(date_val):
                return jsonify({'error': f'仕訳{i}: date フォーマットエラー'}), 400
            note = txn.get('note', '')
            lines = txn.get('lines', [])
            if len(lines) < 2:
                return jsonify({'error': f'仕訳{i}: lines は 2 行以上必要です'}), 400
            debit_total  = sum(int(l.get('amount', 0)) for l in lines if l.get('debit_credit') == 'debit')
            credit_total = sum(int(l.get('amount', 0)) for l in lines if l.get('debit_credit') == 'credit')
            if debit_total != credit_total:
                return jsonify({'error': f'仕訳{i}: 借方合計 {debit_total:,} と貸方合計 {credit_total:,} が一致しません'}), 400
            tid = str(uuid.uuid4())
            for line in lines:
                code = str(line.get('account_code', ''))
                if code not in accounts_map:
                    return jsonify({'error': f'仕訳{i}: account_code "{code}" が存在しません'}), 400
                db.execute(
                    'INSERT INTO journal (transaction_id, entry_date, account_id, debit_credit, amount, note) '
                    'VALUES (?,?,?,?,?,?)',
                    (tid, date_val, accounts_map[code], line.get('debit_credit'), int(line.get('amount', 0)), note)
                )
            committed += 1
        db.commit()
        return jsonify({'ok': True, 'committed': committed})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
