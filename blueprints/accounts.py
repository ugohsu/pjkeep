# -*- coding: utf-8 -*-
import sqlite3
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from helpers import get_db, db_required

accounts_bp = Blueprint('accounts', __name__)


@accounts_bp.get('/accounts')
@login_required
@db_required
def accounts():
    return render_template('accounts.html')


@accounts_bp.get('/api/accounts')
@login_required
@db_required
def api_accounts_list():
    db = get_db()
    rows = db.execute(
        'SELECT id, name, code, element, sort_order FROM accounts ORDER BY element, sort_order, name'
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@accounts_bp.post('/api/accounts')
@login_required
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


@accounts_bp.put('/api/accounts/<int:account_id>')
@login_required
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


@accounts_bp.delete('/api/accounts/<int:account_id>')
@login_required
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


@accounts_bp.post('/api/accounts/batch')
@login_required
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
