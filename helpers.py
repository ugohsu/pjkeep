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


def get_db():
    db_path = get_db_path()
    if not db_path or not os.path.exists(db_path):
        return None
    if 'db' not in g:
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
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
