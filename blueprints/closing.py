# -*- coding: utf-8 -*-
import sqlite3
from flask import Blueprint, request, jsonify
from flask_login import login_required
from helpers import get_db, db_required, get_closing_amounts

closing_bp = Blueprint('closing', __name__)


@closing_bp.get('/api/closings')
@login_required
@db_required
def api_closings_list():
    db = get_db()
    return jsonify(get_closing_amounts(db))


@closing_bp.get('/api/closings/preview')
@login_required
@db_required
def api_closings_preview():
    """指定した振替日の振替金額をプレビュー（未保存）。"""
    closing_date = request.args.get('closing_date', '').strip()
    if not closing_date:
        return jsonify({'error': '振替日を指定してください'}), 400

    db = get_db()
    if db.execute('SELECT id FROM closings WHERE closing_date=?', (closing_date,)).fetchone():
        return jsonify({'error': 'この日付の振替は既に登録されています'}), 400

    gross_row = db.execute('''
        SELECT COALESCE(SUM(
            CASE WHEN a.element='revenues' AND j.debit_credit='credit' THEN  j.amount
                 WHEN a.element='revenues' AND j.debit_credit='debit'  THEN -j.amount
                 WHEN a.element='expenses' AND j.debit_credit='debit'  THEN -j.amount
                 WHEN a.element='expenses' AND j.debit_credit='credit' THEN  j.amount
                 ELSE 0 END
        ), 0) as gross
        FROM journal j JOIN accounts a ON j.account_id = a.id
        WHERE a.element IN ('revenues','expenses') AND j.entry_date < ?
    ''', (closing_date,)).fetchone()

    gross = gross_row['gross'] or 0
    prior = sum(c['amount'] for c in get_closing_amounts(db) if c['closing_date'] < closing_date)
    return jsonify({'amount': gross - prior})


@closing_bp.post('/api/closings')
@login_required
@db_required
def api_closings_create():
    data = request.json or {}
    closing_date = data.get('closing_date', '').strip()
    account_id = data.get('account_id')
    note = (data.get('note') or '').strip() or None

    if not closing_date:
        return jsonify({'error': '振替日は必須です'}), 400
    if not account_id:
        return jsonify({'error': '振替先科目は必須です'}), 400

    db = get_db()
    acc = db.execute('SELECT element FROM accounts WHERE id=?', (account_id,)).fetchone()
    if not acc:
        return jsonify({'error': '科目が見つかりません'}), 400
    if acc['element'] != 'equity':
        return jsonify({'error': '振替先は純資産科目のみ指定できます'}), 400

    try:
        cur = db.execute(
            'INSERT INTO closings (closing_date, account_id, note) VALUES (?,?,?)',
            (closing_date, account_id, note)
        )
        db.commit()
        return jsonify({'id': cur.lastrowid, 'ok': True})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'この日付の振替は既に登録されています'}), 400


@closing_bp.delete('/api/closings/<int:closing_id>')
@login_required
@db_required
def api_closings_delete(closing_id):
    db = get_db()
    db.execute('DELETE FROM closings WHERE id=?', (closing_id,))
    db.commit()
    return jsonify({'ok': True})
