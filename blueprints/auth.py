# -*- coding: utf-8 -*-
import os
from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from helpers import get_users_db, DATA_DIR, User

auth_bp = Blueprint('auth', __name__)

# ---------- pages ----------

@auth_bp.get('/setup')
def setup():
    if get_users_db().execute('SELECT COUNT(*) FROM users').fetchone()[0] > 0:
        return redirect(url_for('auth.login'))
    return render_template('auth/setup.html')


@auth_bp.get('/login')
def login():
    if current_user.is_authenticated:
        return redirect('/')
    return render_template('auth/login.html')


@auth_bp.get('/register')
def register():
    if current_user.is_authenticated:
        return redirect('/')
    return render_template('auth/register.html')


@auth_bp.get('/profile')
@login_required
def profile():
    return render_template('auth/profile.html')


# ---------- API ----------

@auth_bp.post('/api/auth/setup')
def api_setup():
    udb = get_users_db()
    if udb.execute('SELECT COUNT(*) FROM users').fetchone()[0] > 0:
        return jsonify({'error': 'すでにセットアップ済みです'}), 400
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    if not username or not password:
        return jsonify({'error': 'ユーザー名とパスワードは必須です'}), 400
    if len(password) < 6:
        return jsonify({'error': 'パスワードは6文字以上にしてください'}), 400
    cur = udb.execute(
        'INSERT INTO users (username, password_hash, role) VALUES (?,?,?)',
        (username, generate_password_hash(password), 'admin')
    )
    udb.commit()
    login_user(User(cur.lastrowid, username, 'admin'))
    return jsonify({'ok': True})


@auth_bp.post('/api/auth/login')
def api_login():
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    udb = get_users_db()
    row = udb.execute(
        'SELECT id, username, password_hash, role FROM users WHERE username=?', (username,)
    ).fetchone()
    if not row or not check_password_hash(row['password_hash'], password):
        return jsonify({'error': 'ユーザー名またはパスワードが正しくありません'}), 401
    user = User(row['id'], row['username'], row['role'])
    login_user(user)
    resp = jsonify({'ok': True})
    # active_db クッキーが他ユーザーのものであればログイン時にクリアする
    active_db = request.cookies.get('active_db')
    if active_db and not user.is_admin:
        proj = udb.execute(
            'SELECT owner_id FROM projects WHERE filename=?', (active_db,)
        ).fetchone()
        if proj is None or proj['owner_id'] != user.id:
            resp.delete_cookie('active_db')
    return resp


@auth_bp.post('/api/auth/logout')
@login_required
def api_logout():
    logout_user()
    return jsonify({'ok': True})


@auth_bp.post('/api/auth/register')
def api_register():
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    if not username or not password:
        return jsonify({'error': 'ユーザー名とパスワードは必須です'}), 400
    if len(password) < 6:
        return jsonify({'error': 'パスワードは6文字以上にしてください'}), 400
    udb = get_users_db()
    try:
        cur = udb.execute(
            'INSERT INTO users (username, password_hash, role) VALUES (?,?,?)',
            (username, generate_password_hash(password), 'user')
        )
        udb.commit()
    except Exception:
        return jsonify({'error': 'そのユーザー名はすでに使用されています'}), 400
    login_user(User(cur.lastrowid, username, 'user'))
    return jsonify({'ok': True})


@auth_bp.post('/api/profile/password')
@login_required
def api_profile_password():
    data = request.json or {}
    current_pw = data.get('current_password', '')
    new_pw = data.get('new_password', '').strip()
    if not current_pw or not new_pw:
        return jsonify({'error': '現在のパスワードと新しいパスワードを入力してください'}), 400
    if len(new_pw) < 6:
        return jsonify({'error': 'パスワードは6文字以上にしてください'}), 400
    udb = get_users_db()
    row = udb.execute('SELECT password_hash FROM users WHERE id=?', (current_user.id,)).fetchone()
    if not check_password_hash(row['password_hash'], current_pw):
        return jsonify({'error': '現在のパスワードが正しくありません'}), 400
    udb.execute('UPDATE users SET password_hash=? WHERE id=?',
                (generate_password_hash(new_pw), current_user.id))
    udb.commit()
    return jsonify({'ok': True})


@auth_bp.delete('/api/profile')
@login_required
def api_profile_delete():
    udb = get_users_db()
    projects = udb.execute(
        'SELECT filename FROM projects WHERE owner_id=?', (current_user.id,)
    ).fetchall()
    for p in projects:
        path = os.path.join(DATA_DIR, p['filename'])
        if os.path.exists(path):
            os.remove(path)
    udb.execute('DELETE FROM projects WHERE owner_id=?', (current_user.id,))
    udb.execute('DELETE FROM users WHERE id=?', (current_user.id,))
    udb.commit()
    logout_user()
    return jsonify({'ok': True})
