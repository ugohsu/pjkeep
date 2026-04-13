# -*- coding: utf-8 -*-
import os
from flask import Flask, g, jsonify, redirect, request, url_for
from flask_login import LoginManager
from helpers import get_users_db, get_db, DATA_DIR, User


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
    from blueprints.closing import closing_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(init_bp)
    app.register_blueprint(accounts_bp)
    app.register_blueprint(journal_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(closing_bp)

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
