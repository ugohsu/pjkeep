# -*- coding: utf-8 -*-
import io
import os
import sqlite3
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, Response, g, jsonify, redirect, request, url_for
from flask_login import LoginManager, UserMixin, current_user

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


# ---------- App factory ----------

def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get('SECRET_KEY', 'dev-insecure-key-change-me')

    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        try:
            row = get_users_db().execute(
                'SELECT id, username, role FROM users WHERE id=?', (user_id,)
            ).fetchone()
            if row:
                return User(row['id'], row['username'], row['role'])
        except Exception:
            pass
        return None

    @login_manager.unauthorized_handler
    def unauthorized():
        if request.path.startswith('/api/'):
            return jsonify({'error': '認証が必要です'}), 401
        return redirect(url_for('auth.login'))

    @app.teardown_appcontext
    def close_dbs(e=None):
        for key in ('db', 'users_db'):
            conn = g.pop(key, None)
            if conn:
                conn.close()

    @app.context_processor
    def inject_context():
        active_db_name = None
        filename = request.cookies.get('active_db')
        if filename:
            try:
                proj = get_users_db().execute(
                    'SELECT description FROM projects WHERE filename=?', (filename,)
                ).fetchone()
                active_db_name = (proj['description'] if proj and proj['description'] else filename)
            except Exception:
                active_db_name = filename
        return {'active_db_name': active_db_name}

    @app.before_request
    def check_setup():
        """ユーザーが 0 人のときはセットアップページへ誘導する。"""
        if request.endpoint == 'static':
            return
        if request.path in ('/setup', '/api/auth/setup'):
            return
        try:
            count = get_users_db().execute('SELECT COUNT(*) FROM users').fetchone()[0]
            if count == 0:
                return redirect('/setup')
        except Exception:
            pass

    from blueprints.auth import auth_bp
    from blueprints.admin import admin_bp
    from blueprints.init_bp import init_bp
    from blueprints.accounts import accounts_bp
    from blueprints.journal import journal_bp
    from blueprints.report import report_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(init_bp)
    app.register_blueprint(accounts_bp)
    app.register_blueprint(journal_bp)
    app.register_blueprint(report_bp)

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
