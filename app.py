# -*- coding: utf-8 -*-
import os
import json
import uuid
import sqlite3
from flask import Flask, render_template, request, jsonify, redirect, url_for, g, Response
from functools import wraps
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.environ.get('DATA_DIR', os.path.join(BASE_DIR, 'data'))
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')

DEFAULT_ACCOUNTS = [
    # 資産
    ('現金',       'cash',         'assets',      10),
    ('普通預金',   'bank',         'assets',      20),
    # 負債
    ('未払金',     'payable',      'liabilities', 10),
    ('預り金',     'deposit',      'liabilities', 20),
    # 純資産
    ('基本金',     'capital',      'equity',      10),
    ('繰越金',     'retained',     'equity',      20),
    # 収益
    ('保育料収入', 'childcare_fee','revenues',    10),
    ('補助金収入', 'subsidy',      'revenues',    20),
    # 費用
    ('人件費',     'personnel',    'expenses',    10),
    ('事業費',     'operating',    'expenses',    20),
]

# ---------- config ----------

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_config(updates):
    config = load_config()
    config.update(updates)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def get_db_path():
    filename = request.cookies.get('active_db')
    if filename:
        return os.path.join(DATA_DIR, filename)
    return None

# ---------- DB ----------

def get_db():
    db_path = get_db_path()
    if not db_path or not os.path.exists(db_path):
        return None
    if 'db' not in g:
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db

@app.context_processor
def inject_active_db():
    filename = request.cookies.get('active_db')
    if not filename:
        return {'active_db_name': None}
    descriptions = load_config().get('descriptions', {})
    label = descriptions.get(filename) or filename
    return {'active_db_name': label}

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def db_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if get_db() is None:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'DBが設定されていません'}), 503
            return redirect(url_for('init'))
        return f(*args, **kwargs)
    return decorated

def init_db(db_path, insert_defaults=True):
    schema = open(os.path.join(BASE_DIR, 'schema.sql'), encoding='utf-8').read()
    conn = sqlite3.connect(db_path)
    conn.executescript(schema)
    if insert_defaults:
        for name, code, element, sort_order in DEFAULT_ACCOUNTS:
            conn.execute(
                'INSERT OR IGNORE INTO accounts (name, code, element, sort_order) VALUES (?,?,?,?)',
                (name, code, element, sort_order)
            )
    conn.commit()
    conn.close()

# ---------- pages ----------

@app.route('/')
def index():
    if get_db() is None:
        return redirect(url_for('init'))
    return redirect(url_for('entry'))

@app.route('/init')
def init():
    db_path = get_db_path()
    configured = bool(db_path and os.path.exists(db_path))
    return render_template('init.html', configured=configured, db_path=db_path or '')

@app.route('/entry')
@db_required
def entry():
    return render_template('entry.html')

@app.route('/journal')
@db_required
def journal():
    return render_template('journal.html')

@app.route('/report')
@db_required
def report():
    return render_template('report.html')

@app.route('/accounts')
@db_required
def accounts():
    return render_template('accounts.html')

# ---------- init API ----------

@app.post('/api/init/create')
def api_init_create():
    from werkzeug.utils import secure_filename
    data = request.json or {}
    filename = data.get('db_path', '').strip()
    if not filename:
        filename = 'pjkeep.db'
    # フルパスやディレクトリ指定を禁止
    if os.path.isabs(filename) or '/' in filename or '\\' in filename:
        return jsonify({'error': 'ファイル名のみ指定してください（パスは指定できません）'}), 400
    filename = secure_filename(filename)
    if not filename.endswith('.db'):
        filename += '.db'
    db_path = os.path.join(DATA_DIR, filename)
    if os.path.exists(db_path):
        return jsonify({'error': f'ファイルが既に存在します: {filename}'}), 400
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        init_db(db_path, insert_defaults=data.get('insert_defaults', True))
        description = data.get('description', '').strip()
        if description:
            config = load_config()
            descriptions = config.get('descriptions', {})
            descriptions[filename] = description
            save_config({'descriptions': descriptions})
        resp = jsonify({'ok': True, 'db_path': db_path})
        resp.set_cookie('active_db', filename)
        return resp
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.get('/api/init/list')
def api_init_list():
    import glob as glob_mod
    files = []
    if os.path.isdir(DATA_DIR):
        current = get_db_path()
        descriptions = load_config().get('descriptions', {})
        for path in sorted(glob_mod.glob(os.path.join(DATA_DIR, '*.db'))):
            name = os.path.basename(path)
            files.append({
                'path': path,
                'name': name,
                'active': os.path.abspath(path) == (os.path.abspath(current) if current else None),
                'description': descriptions.get(name, ''),
            })
    return jsonify(files)

@app.post('/api/init/open')
def api_init_open():
    data = request.json or {}
    db_path = data.get('db_path', '').strip()
    if not db_path:
        return jsonify({'error': 'パスを指定してください'}), 400
    if not os.path.isabs(db_path):
        db_path = os.path.join(DATA_DIR, db_path)
    if not os.path.exists(db_path):
        return jsonify({'error': f'ファイルが見つかりません: {db_path}'}), 404
    resp = jsonify({'ok': True, 'db_path': db_path})
    resp.set_cookie('active_db', os.path.basename(db_path))
    return resp

@app.post('/api/init/upload')
def api_init_upload():
    from werkzeug.utils import secure_filename
    f = request.files.get('db_file')
    if not f or not f.filename:
        return jsonify({'error': 'ファイルが指定されていません'}), 400
    filename = secure_filename(f.filename)
    if not filename.lower().endswith('.db'):
        return jsonify({'error': '.db ファイルのみアップロードできます'}), 400
    os.makedirs(DATA_DIR, exist_ok=True)
    dest = os.path.join(DATA_DIR, filename)
    if os.path.exists(dest):
        return jsonify({'error': f'同名のファイルが既に存在します: {filename}'}), 400
    f.save(dest)
    description = request.form.get('description', '').strip()
    if description:
        config = load_config()
        descriptions = config.get('descriptions', {})
        descriptions[filename] = description
        save_config({'descriptions': descriptions})
    resp = jsonify({'ok': True, 'db_path': dest})
    resp.set_cookie('active_db', filename)
    return resp

@app.post('/api/init/description')
def api_init_description():
    data = request.json or {}
    filename = data.get('filename', '').strip()
    description = data.get('description', '').strip()
    if not filename or os.path.isabs(filename) or '/' in filename or '\\' in filename:
        return jsonify({'error': '不正なファイル名です'}), 400
    config = load_config()
    descriptions = config.get('descriptions', {})
    descriptions[filename] = description
    save_config({'descriptions': descriptions})
    return jsonify({'ok': True})

# ---------- db download ----------

@app.get('/api/db/download')
@db_required
def api_db_download():
    from flask import send_file
    from datetime import date as dt
    db_path = get_db_path()
    stem = os.path.splitext(os.path.basename(db_path))[0]
    filename = f'{stem}_{dt.today().strftime("%Y%m%d")}.db'
    return send_file(db_path, as_attachment=True, download_name=filename)

# ---------- accounts API ----------

@app.get('/api/accounts')
@db_required
def api_accounts_list():
    db = get_db()
    rows = db.execute(
        'SELECT id, name, code, element, sort_order FROM accounts ORDER BY element, sort_order, name'
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@app.post('/api/accounts')
@db_required
def api_accounts_create():
    data = request.json or {}
    name = data.get('name', '').strip()
    code = data.get('code', '').strip()
    element = data.get('element', '').strip()
    sort_order = int(data.get('sort_order', 0))
    if not name or not code or not element:
        return jsonify({'error': '名前・コード・区分は必須です'}), 400
    if element not in ('assets', 'liabilities', 'equity', 'revenues', 'expenses'):
        return jsonify({'error': '区分が不正です'}), 400
    db = get_db()
    try:
        cur = db.execute(
            'INSERT INTO accounts (name, code, element, sort_order) VALUES (?,?,?,?)',
            (name, code, element, sort_order)
        )
        db.commit()
        return jsonify({'id': cur.lastrowid, 'name': name, 'code': code,
                        'element': element, 'sort_order': sort_order})
    except sqlite3.IntegrityError:
        return jsonify({'error': '同じ名前またはコードが既に存在します'}), 400

@app.put('/api/accounts/<int:account_id>')
@db_required
def api_accounts_update(account_id):
    data = request.json or {}
    name = data.get('name', '').strip()
    code = data.get('code', '').strip()
    element = data.get('element', '').strip()
    sort_order = int(data.get('sort_order', 0))
    if not name or not code or not element:
        return jsonify({'error': '名前・コード・区分は必須です'}), 400
    if element not in ('assets', 'liabilities', 'equity', 'revenues', 'expenses'):
        return jsonify({'error': '区分が不正です'}), 400
    db = get_db()
    try:
        db.execute(
            'UPDATE accounts SET name=?, code=?, element=?, sort_order=? WHERE id=?',
            (name, code, element, sort_order, account_id)
        )
        db.commit()
        return jsonify({'ok': True})
    except sqlite3.IntegrityError:
        return jsonify({'error': '同じ名前またはコードが既に存在します'}), 400

@app.delete('/api/accounts/<int:account_id>')
@db_required
def api_accounts_delete(account_id):
    db = get_db()
    count = db.execute(
        'SELECT COUNT(*) FROM journal WHERE account_id=?', (account_id,)
    ).fetchone()[0]
    if count > 0:
        return jsonify({'error': 'この科目には仕訳が存在するため削除できません'}), 400
    db.execute('DELETE FROM accounts WHERE id=?', (account_id,))
    db.commit()
    return jsonify({'ok': True})

# ---------- journal API ----------

@app.get('/api/journal')
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

@app.post('/api/journal')
@db_required
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

@app.delete('/api/journal/transaction/<transaction_id>')
@db_required
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

@app.put('/api/journal/transaction/<transaction_id>')
@db_required
def api_journal_update(transaction_id):
    db = get_db()
    count = db.execute(
        'SELECT COUNT(*) FROM journal WHERE transaction_id=?', (transaction_id,)
    ).fetchone()[0]
    if count == 0:
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

# ---------- duplicate detection ----------

def detect_duplicate(db, date_val, import_note, lines, n_max_days=7):
    """
    既存仕訳の中から重複候補を探し、最も確率の高いものを返す。
    必須条件：借方合計・勘定科目構成が完全一致。
    スコア：日付の近さ（± n_max_days 日）で算出し、摘要が両方非空で部分一致する場合は加点。
    """
    from datetime import date as dt, timedelta
    try:
        target_date = dt.fromisoformat(date_val)
    except ValueError:
        return None

    target_amount = sum(l['amount'] for l in lines if l['debit_credit'] == 'debit')
    target_structure = frozenset(
        (l['account_code'], l['debit_credit']) for l in lines
    )

    date_from = (target_date - timedelta(days=n_max_days)).isoformat()
    date_to   = (target_date + timedelta(days=n_max_days)).isoformat()

    rows = db.execute(
        '''
        SELECT j.transaction_id, j.entry_date, j.debit_credit, j.amount,
               a.code AS account_code, a.name AS account_name,
               j.note
        FROM journal j
        JOIN accounts a ON a.id = j.account_id
        WHERE j.entry_date BETWEEN ? AND ?
        ''',
        (date_from, date_to)
    ).fetchall()

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

    best = None
    best_prob = 0.0

    for tid, txn in by_txn.items():
        cand_amount = sum(l['amount'] for l in txn['lines'] if l['debit_credit'] == 'debit')
        if cand_amount != target_amount:
            continue

        cand_structure = frozenset(
            (l['account_code'], l['debit_credit']) for l in txn['lines']
        )
        if cand_structure != target_structure:
            continue

        try:
            cand_date = dt.fromisoformat(txn['date'])
        except ValueError:
            continue
        date_diff = abs((target_date - cand_date).days)
        date_score = max(0.0, 1.0 - date_diff / n_max_days)

        # 摘要ボーナス：両方非空かつ片方がもう片方を含む場合
        bonus = 1.0
        i_note = (import_note or '').strip()
        t_note = (txn['note'] or '').strip()
        if i_note and t_note and (i_note in t_note or t_note in i_note):
            bonus = 1.1

        probability = min(1.0, date_score * bonus)

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

# ---------- import API ----------

@app.route('/import')
@db_required
def import_page():
    return render_template('import.html')

@app.post('/api/import/preview')
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

    result = []
    errors = []

    for i, txn in enumerate(transactions):
        txn_errors = []

        date_val = str(txn.get('date', ''))
        if not date_re.match(date_val):
            txn_errors.append(f'date が YYYY-MM-DD 形式ではありません: {date_val!r}')

        lines = txn.get('lines', [])
        if not isinstance(lines, list) or len(lines) < 2:
            txn_errors.append('lines は 2 行以上必要です')

        resolved_lines = []
        debit_total = 0
        credit_total = 0

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
            resolved_lines.append({
                'account_code': code,
                'account_name': account_name,
                'debit_credit': dc,
                'amount': amount_int,
            })

            if dc == 'debit':
                debit_total += amount_int
            elif dc == 'credit':
                credit_total += amount_int

        if not txn_errors and debit_total != credit_total:
            txn_errors.append(f'借方合計 {debit_total:,} と貸方合計 {credit_total:,} が一致しません')

        duplicate = None
        if len(txn_errors) == 0:
            duplicate = detect_duplicate(db, date_val, txn.get('note', ''), resolved_lines)

        result.append({
            'index': i,
            'date': txn.get('date', ''),
            'note': txn.get('note', ''),
            '_comment': txn.get('_comment', ''),
            '_confidence': float(txn.get('_confidence', 1.0)),
            'lines': resolved_lines,
            'valid': len(txn_errors) == 0,
            '_duplicate': duplicate,
        })
        for msg in txn_errors:
            errors.append({'index': i, 'message': msg})

    return jsonify({'ok': True, 'transactions': result, 'errors': errors})

@app.post('/api/import/commit')
@db_required
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
                    (tid, date_val, accounts_map[code],
                     line.get('debit_credit'), int(line.get('amount', 0)), note)
                )
            committed += 1
        db.commit()
        return jsonify({'ok': True, 'committed': committed})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500

# ---------- accounts batch API ----------

@app.post('/api/accounts/batch')
@db_required
def api_accounts_batch():
    data = request.json or {}
    accounts_list = data.get('accounts', [])
    if not isinstance(accounts_list, list):
        return jsonify({'error': 'accounts は配列である必要があります'}), 400

    db = get_db()
    results = []
    errors = []

    for i, acc in enumerate(accounts_list):
        name = str(acc.get('name', '')).strip()
        code = str(acc.get('code', '')).strip()
        element = str(acc.get('element', '')).strip()
        sort_order = int(acc.get('sort_order', 0))

        if not name or not code or not element:
            errors.append({'index': i, 'message': f'行{i+1}: 名前・コード・区分は必須です'})
            continue
        if element not in ('assets', 'liabilities', 'equity', 'revenues', 'expenses'):
            errors.append({'index': i, 'message': f'行{i+1}: 区分が不正です: {element!r}'})
            continue

        try:
            cur = db.execute(
                'INSERT INTO accounts (name, code, element, sort_order) VALUES (?,?,?,?)',
                (name, code, element, sort_order)
            )
            results.append({'index': i, 'id': cur.lastrowid, 'name': name, 'code': code})
        except sqlite3.IntegrityError:
            errors.append({'index': i, 'message': f'行{i+1}: "{name}" または "{code}" は既に存在します'})

    db.commit()
    return jsonify({'ok': True, 'inserted': len(results), 'results': results, 'errors': errors})

# ---------- report API ----------

@app.get('/api/report/pl')
@db_required
def api_report_pl():
    from datetime import date as dt
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

@app.get('/api/report/bs')
@db_required
def api_report_bs():
    import calendar
    from datetime import date as dt
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
        WHERE a.element IN ('revenues','expenses')
          AND j.entry_date <= ?
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

@app.get('/api/months')
@db_required
def api_months():
    db = get_db()
    rows = db.execute(
        "SELECT DISTINCT strftime('%Y-%m', entry_date) as ym FROM journal ORDER BY ym DESC"
    ).fetchall()
    return jsonify([r['ym'] for r in rows])

# ---------- export ----------

def tsv_response(rows, headers, filename):
    import io
    buf = io.StringIO()
    buf.write('\t'.join(headers) + '\n')
    for row in rows:
        buf.write('\t'.join(str(v) for v in row) + '\n')
    return Response(
        buf.getvalue().encode('utf-8'),
        mimetype='text/tab-separated-values; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )

@app.get('/api/export/journal')
@db_required
def api_export_journal():
    ym        = request.args.get('ym', '')
    from_date = request.args.get('from', '')
    to_date   = request.args.get('to', '')
    db = get_db()

    if ym:
        rows = db.execute('''
            SELECT j.entry_date, j.note, j.transaction_id, j.debit_credit, a.name, j.amount
            FROM journal j
            JOIN accounts a ON j.account_id = a.id
            WHERE strftime('%Y-%m', j.entry_date) = ?
            ORDER BY j.entry_date, j.transaction_id, j.debit_credit DESC
        ''', (ym,)).fetchall()
        filename_suffix = ym
    elif from_date and to_date:
        rows = db.execute('''
            SELECT j.entry_date, j.note, j.transaction_id, j.debit_credit, a.name, j.amount
            FROM journal j
            JOIN accounts a ON j.account_id = a.id
            WHERE j.entry_date >= ? AND j.entry_date <= ?
            ORDER BY j.entry_date, j.transaction_id, j.debit_credit DESC
        ''', (from_date, to_date)).fetchall()
        filename_suffix = f'{from_date}_{to_date}'
    else:
        rows = db.execute('''
            SELECT j.entry_date, j.note, j.transaction_id, j.debit_credit, a.name, j.amount
            FROM journal j
            JOIN accounts a ON j.account_id = a.id
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

@app.get('/api/export/report')
@db_required
def api_export_report():
    from datetime import date as dt
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
            WHERE a.element IN ('assets','liabilities','equity')
              AND j.entry_date <= ?
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
        import calendar
        year, month = int(ym[:4]), int(ym[5:7])
        last_day = calendar.monthrange(year, month)[1]
        end_date = f'{ym}-{last_day:02d}'
        pl_rows = db.execute('''
            SELECT a.name, a.element,
                   SUM(CASE WHEN j.debit_credit='debit'  THEN j.amount ELSE 0 END) as dt,
                   SUM(CASE WHEN j.debit_credit='credit' THEN j.amount ELSE 0 END) as ct
            FROM journal j JOIN accounts a ON j.account_id=a.id
            WHERE a.element IN ('revenues','expenses')
              AND strftime('%Y-%m', j.entry_date)=?
            GROUP BY a.id ORDER BY a.element, a.sort_order, a.name
        ''', (ym,)).fetchall()

        bs_rows = db.execute('''
            SELECT a.name, a.element,
                   SUM(CASE WHEN j.debit_credit='debit'  THEN j.amount ELSE 0 END) as dt,
                   SUM(CASE WHEN j.debit_credit='credit' THEN j.amount ELSE 0 END) as ct
            FROM journal j JOIN accounts a ON j.account_id=a.id
            WHERE a.element IN ('assets','liabilities','equity')
              AND j.entry_date<=?
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

    data = []
    ELEM_JA = {'revenues':'収益','expenses':'費用','assets':'資産','liabilities':'負債','equity':'純資産'}

    data.append([f'【損益計算書】{label_pl}', '', ''])
    data.append(['区分', '勘定科目', '金額'])
    rev_total, exp_total = 0, 0
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

# ---------- run ----------

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
