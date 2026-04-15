# -*- coding: utf-8 -*-
import os
from functools import wraps
from flask import Blueprint, render_template, request, jsonify, redirect, url_for
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
               COUNT(pm.project_id) as project_count
        FROM users u
        LEFT JOIN project_members pm ON pm.user_id = u.id
        GROUP BY u.id
        ORDER BY u.created_at
    ''').fetchall()
    return jsonify([dict(r) for r in rows])


# ---------- project pages ----------

@admin_bp.get('/admin/projects')
@admin_required
def admin_projects():
    return render_template('admin/projects.html')


# ---------- project API ----------

@admin_bp.get('/api/admin/projects')
@admin_required
def api_admin_projects():
    udb = get_users_db()
    rows = udb.execute('''
        SELECT p.id, p.filename, p.description, p.owner_id,
               u.username as owner_name,
               COUNT(pm.user_id) as member_count
        FROM projects p
        LEFT JOIN users u ON u.id = p.owner_id
        LEFT JOIN project_members pm ON pm.project_id = p.id
        GROUP BY p.id
        ORDER BY p.filename
    ''').fetchall()
    return jsonify([dict(r) for r in rows])


@admin_bp.delete('/api/admin/projects/<int:project_id>')
@admin_required
def api_admin_delete_project(project_id):
    udb = get_users_db()
    proj = udb.execute('SELECT filename FROM projects WHERE id=?', (project_id,)).fetchone()
    if not proj:
        return jsonify({'error': 'プロジェクトが見つかりません'}), 404
    path = os.path.join(DATA_DIR, proj['filename'])
    if os.path.exists(path):
        os.remove(path)
    udb.execute('DELETE FROM projects WHERE id=?', (project_id,))
    udb.commit()
    return jsonify({'ok': True})


@admin_bp.get('/api/admin/projects/<int:project_id>/members')
@admin_required
def api_admin_project_members(project_id):
    udb = get_users_db()
    if not udb.execute('SELECT id FROM projects WHERE id=?', (project_id,)).fetchone():
        return jsonify({'error': 'プロジェクトが見つかりません'}), 404
    rows = udb.execute('''
        SELECT u.id, u.username, pm.permission
        FROM project_members pm
        JOIN users u ON u.id = pm.user_id
        WHERE pm.project_id=?
        ORDER BY u.username
    ''', (project_id,)).fetchall()
    return jsonify([dict(r) for r in rows])


@admin_bp.put('/api/admin/projects/<int:project_id>/members/<int:user_id>')
@admin_required
def api_admin_project_member_put(project_id, user_id):
    data = request.json or {}
    permission = data.get('permission', '')
    if permission not in ('read', 'write'):
        return jsonify({'error': 'permission は "read" または "write" です'}), 400
    udb = get_users_db()
    if not udb.execute('SELECT id FROM projects WHERE id=?', (project_id,)).fetchone():
        return jsonify({'error': 'プロジェクトが見つかりません'}), 404
    if not udb.execute('SELECT id FROM users WHERE id=?', (user_id,)).fetchone():
        return jsonify({'error': 'ユーザーが見つかりません'}), 404
    udb.execute('''
        INSERT INTO project_members (project_id, user_id, permission)
        VALUES (?,?,?)
        ON CONFLICT(project_id, user_id) DO UPDATE SET permission=excluded.permission
    ''', (project_id, user_id, permission))
    udb.commit()
    return jsonify({'ok': True})


@admin_bp.delete('/api/admin/projects/<int:project_id>/members/<int:user_id>')
@admin_required
def api_admin_project_member_delete(project_id, user_id):
    udb = get_users_db()
    udb.execute(
        'DELETE FROM project_members WHERE project_id=? AND user_id=?',
        (project_id, user_id)
    )
    udb.commit()
    return jsonify({'ok': True})


# ---------- user API ----------

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
