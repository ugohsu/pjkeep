# -*- coding: utf-8 -*-
import os
from functools import wraps
from flask import Blueprint, render_template, request, jsonify, redirect
from flask_login import current_user
from helpers import get_users_db, DATA_DIR

admin_bp = Blueprint('admin', __name__)


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            if request.path.startswith('/api/'):
                return jsonify({'error': '認証が必要です'}), 401
            return redirect('/login')
        if not current_user.is_admin:
            if request.path.startswith('/api/'):
                return jsonify({'error': '管理者権限が必要です'}), 403
            return redirect('/')
        return f(*args, **kwargs)
    return decorated


# ---------- pages ----------

@admin_bp.get('/admin/users')
@admin_required
def admin_users():
    return render_template('admin/users.html')


# ---------- API ----------

@admin_bp.get('/api/admin/users')
@admin_required
def api_admin_users():
    udb = get_users_db()
    rows = udb.execute('''
        SELECT u.id, u.username, u.role, u.created_at,
               COUNT(p.id) as project_count
        FROM users u
        LEFT JOIN projects p ON p.owner_id = u.id
        GROUP BY u.id
        ORDER BY u.created_at
    ''').fetchall()
    return jsonify([dict(r) for r in rows])


@admin_bp.delete('/api/admin/users/<int:user_id>')
@admin_required
def api_admin_delete_user(user_id):
    if user_id == current_user.id:
        return jsonify({'error': '自分自身は削除できません'}), 400
    udb = get_users_db()
    if not udb.execute('SELECT id FROM users WHERE id=?', (user_id,)).fetchone():
        return jsonify({'error': 'ユーザーが見つかりません'}), 404
    projects = udb.execute(
        'SELECT filename FROM projects WHERE owner_id=?', (user_id,)
    ).fetchall()
    for p in projects:
        path = os.path.join(DATA_DIR, p['filename'])
        if os.path.exists(path):
            os.remove(path)
    udb.execute('DELETE FROM projects WHERE owner_id=?', (user_id,))
    udb.execute('DELETE FROM users WHERE id=?', (user_id,))
    udb.commit()
    return jsonify({'ok': True})
