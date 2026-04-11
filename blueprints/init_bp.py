# -*- coding: utf-8 -*-
import os
import sqlite3
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, send_file
from flask_login import login_required, current_user
from datetime import date as dt
from helpers import get_db, get_db_path, get_users_db, DATA_DIR, BASE_DIR

init_bp = Blueprint('init_bp', __name__)

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

@init_bp.get('/')
@login_required
def index():
    if get_db() is None:
        return redirect(url_for('init_bp.init'))
    return redirect(url_for('journal.entry'))


@init_bp.get('/init')
@login_required
def init():
    db_path = get_db_path()
    configured = False
    if db_path and os.path.exists(db_path):
        if current_user.is_admin:
            configured = True
        else:
            filename = os.path.basename(db_path)
            proj = get_users_db().execute(
                'SELECT owner_id FROM projects WHERE filename=?', (filename,)
            ).fetchone()
            configured = bool(proj and proj['owner_id'] == current_user.id)
    return render_template('init.html', configured=configured, db_path=db_path or '')


# ---------- API ----------

@init_bp.get('/api/init/list')
@login_required
def api_init_list():
    udb = get_users_db()
    current_filename = os.path.basename(get_db_path()) if get_db_path() else None
    if current_user.is_admin:
        rows = udb.execute(
            'SELECT filename, description, owner_id FROM projects ORDER BY filename'
        ).fetchall()
    else:
        rows = udb.execute(
            'SELECT filename, description, owner_id FROM projects WHERE owner_id=? ORDER BY filename',
            (current_user.id,)
        ).fetchall()
    files = []
    for r in rows:
        path = os.path.join(DATA_DIR, r['filename'])
        files.append({
            'path': path,
            'name': r['filename'],
            'description': r['description'] or '',
            'active': r['filename'] == current_filename,
        })
    return jsonify(files)


@init_bp.post('/api/init/create')
@login_required
def api_init_create():
    from werkzeug.utils import secure_filename
    data = request.json or {}
    filename = data.get('db_path', '').strip()
    if not filename:
        filename = 'pjkeep.db'
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
        udb = get_users_db()
        udb.execute(
            'INSERT INTO projects (filename, description, owner_id) VALUES (?,?,?)',
            (filename, description or None, current_user.id)
        )
        udb.commit()
        resp = jsonify({'ok': True, 'db_path': db_path})
        resp.set_cookie('active_db', filename)
        return resp
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@init_bp.post('/api/init/open')
@login_required
def api_init_open():
    data = request.json or {}
    db_path = data.get('db_path', '').strip()
    if not db_path:
        return jsonify({'error': 'パスを指定してください'}), 400
    if not os.path.isabs(db_path):
        db_path = os.path.join(DATA_DIR, db_path)
    if not os.path.exists(db_path):
        return jsonify({'error': f'ファイルが見つかりません: {db_path}'}), 404
    filename = os.path.basename(db_path)
    # アクセス権チェック
    if not current_user.is_admin:
        udb = get_users_db()
        proj = udb.execute(
            'SELECT owner_id FROM projects WHERE filename=?', (filename,)
        ).fetchone()
        if proj is None or proj['owner_id'] != current_user.id:
            return jsonify({'error': 'アクセス権がありません'}), 403
    resp = jsonify({'ok': True, 'db_path': db_path})
    resp.set_cookie('active_db', filename)
    return resp


@init_bp.post('/api/init/upload')
@login_required
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
    udb = get_users_db()
    udb.execute(
        'INSERT INTO projects (filename, description, owner_id) VALUES (?,?,?)',
        (filename, description or None, current_user.id)
    )
    udb.commit()
    resp = jsonify({'ok': True, 'db_path': dest})
    resp.set_cookie('active_db', filename)
    return resp


@init_bp.post('/api/init/description')
@login_required
def api_init_description():
    data = request.json or {}
    filename = data.get('filename', '').strip()
    description = data.get('description', '').strip()
    if not filename or os.path.isabs(filename) or '/' in filename or '\\' in filename:
        return jsonify({'error': '不正なファイル名です'}), 400
    udb = get_users_db()
    proj = udb.execute('SELECT owner_id FROM projects WHERE filename=?', (filename,)).fetchone()
    if proj is None:
        return jsonify({'error': 'プロジェクトが見つかりません'}), 404
    if not current_user.is_admin and proj['owner_id'] != current_user.id:
        return jsonify({'error': 'アクセス権がありません'}), 403
    udb.execute('UPDATE projects SET description=? WHERE filename=?', (description or None, filename))
    udb.commit()
    return jsonify({'ok': True})


@init_bp.get('/api/db/download')
@login_required
def api_db_download():
    from helpers import get_db, db_required
    db_path = get_db_path()
    if not db_path or not os.path.exists(db_path):
        return jsonify({'error': 'DBが設定されていません'}), 503
    filename = os.path.basename(db_path)
    if not current_user.is_admin:
        udb = get_users_db()
        proj = udb.execute('SELECT owner_id FROM projects WHERE filename=?', (filename,)).fetchone()
        if proj is None or proj['owner_id'] != current_user.id:
            return jsonify({'error': 'アクセス権がありません'}), 403
    stem = os.path.splitext(filename)[0]
    download_name = f'{stem}_{dt.today().strftime("%Y%m%d")}.db'
    return send_file(db_path, as_attachment=True, download_name=download_name)
