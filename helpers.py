# -*- coding: utf-8 -*-
import io
import os
import sqlite3
from functools import wraps

from dotenv import load_dotenv
from flask import Response, g, jsonify, redirect, request, url_for
from flask_login import UserMixin, current_user

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get('DATA_DIR', os.path.join(BASE_DIR, 'data'))
USERS_DB_PATH = os.path.join(DATA_DIR, 'users.db')

USERS_SCHEMA = '''
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK(role IN ('admin','user')),
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY,
    filename    TEXT UNIQUE NOT NULL,
    description TEXT,
    owner_id    INTEGER REFERENCES users(id) ON DELETE SET NULL
);
'''

# ---------- User model ----------

class User(UserMixin):
    def __init__(self, id, username, role):
        self.id = id
        self.username = username
        self.role = role

    @property
    def is_admin(self):
        return self.role == 'admin'


# ---------- DB helpers ----------

def get_users_db():
    if 'users_db' not in g:
        os.makedirs(DATA_DIR, exist_ok=True)
        conn = sqlite3.connect(USERS_DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        conn.executescript(USERS_SCHEMA)
        conn.commit()
        g.users_db = conn
    return g.users_db


def get_db_path():
    filename = request.cookies.get('active_db')
    if filename:
        return os.path.join(DATA_DIR, filename)
    return None


def _apply_migrations(db):
    """既存 DB に対してスキーマ追加を冪等に適用する。"""
    db.execute('''CREATE TABLE IF NOT EXISTS closings (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        closing_date  TEXT    NOT NULL UNIQUE,
        account_id    INTEGER NOT NULL REFERENCES accounts(id),
        note          TEXT,
        created_at    TEXT    DEFAULT (datetime('now','localtime'))
    )''')
    db.execute('CREATE INDEX IF NOT EXISTS idx_closings_closing_date ON closings(closing_date)')
    db.commit()


def get_db():
    db_path = get_db_path()
    if not db_path or not os.path.exists(db_path):
        return None
    if 'db' not in g:
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
        _apply_migrations(g.db)
    return g.db


def db_required(f):
    """プロジェクト DB の存在チェック＋オーナーチェックを行うデコレーター。"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if get_db() is None:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'DBが設定されていません'}), 503
            return redirect(url_for('init_bp.init'))
        if not current_user.is_admin:
            filename = request.cookies.get('active_db')
            proj = get_users_db().execute(
                'SELECT owner_id FROM projects WHERE filename=?', (filename,)
            ).fetchone()
            if proj is None or proj['owner_id'] != current_user.id:
                if request.path.startswith('/api/'):
                    return jsonify({'error': 'アクセス権がありません'}), 403
                return redirect(url_for('init_bp.init'))
        return f(*args, **kwargs)
    return decorated


# ---------- Closing helpers ----------

def get_closing_amounts(db):
    """
    closings テーブルの全レコードについて振替金額を動的計算して返す。

    振替金額の定義:
        振替日 D の金額 = (entry_date < D の仕訳の収益−費用合計)
                         − (D より前の振替の合計)

    これは「前回振替後から今回振替日前日までの累計純損益」に相当する。

    戻り値: [{'id', 'closing_date', 'account_id', 'account_name', 'note', 'amount'}, ...]
    日付昇順。
    """
    rows = db.execute('''
        SELECT c.id, c.closing_date, c.account_id, c.note,
               a.name as account_name,
               COALESCE((
                   SELECT SUM(
                       CASE WHEN ac.element='revenues' AND j.debit_credit='credit' THEN  j.amount
                            WHEN ac.element='revenues' AND j.debit_credit='debit'  THEN -j.amount
                            WHEN ac.element='expenses' AND j.debit_credit='debit'  THEN -j.amount
                            WHEN ac.element='expenses' AND j.debit_credit='credit' THEN  j.amount
                            ELSE 0 END)
                   FROM journal j JOIN accounts ac ON j.account_id = ac.id
                   WHERE ac.element IN ('revenues','expenses')
                     AND j.entry_date < c.closing_date
               ), 0) as gross
        FROM closings c
        JOIN accounts a ON c.account_id = a.id
        ORDER BY c.closing_date
    ''').fetchall()

    result = []
    prev_gross = 0
    for r in rows:
        amount = r['gross'] - prev_gross
        prev_gross = r['gross']
        result.append({
            'id': r['id'],
            'closing_date': r['closing_date'],
            'account_id': r['account_id'],
            'account_name': r['account_name'],
            'note': r['note'] or '',
            'amount': amount,
        })
    return result


# ---------- Utilities ----------

def tsv_response(rows, headers, filename):
    buf = io.StringIO()
    buf.write('\t'.join(headers) + '\n')
    for row in rows:
        buf.write('\t'.join(str(v) for v in row) + '\n')
    return Response(
        buf.getvalue().encode('utf-8'),
        mimetype='text/tab-separated-values; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )
