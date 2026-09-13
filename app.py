import os
from flask import Flask, send_from_directory, render_template, session
from config import Config
from db import close_db, query_db
from routes.api_routes import api_bp
from routes.page_routes import page_bp
from routes.customer_bp import customer_bp
from routes.staff_bp import staff_bp
from models.auth import ensure_system_settings
from models.parcel import STATUS_LIST
from database.migrations import run_migrations

def create_app():
    app = Flask(__name__, template_folder='templates', static_folder='assets')
    app.config.from_object(Config)

    # Register database teardown
    app.teardown_appcontext(close_db)

    # Automatically run schema migrations on startup
    with app.app_context():
        try:
            run_migrations()
        except Exception as mig_err:
            app.logger.warning(f"Database migration note: {mig_err}")

    # Static file routes for legacy path preservation
    @app.route('/assets/<path:filename>')
    def serve_assets(filename):
        return send_from_directory(os.path.join(app.root_path, 'assets'), filename)

    @app.route('/landing_assets/<path:filename>')
    def serve_landing_assets(filename):
        return send_from_directory(os.path.join(app.root_path, 'landing_assets'), filename)

    @app.route('/landing_vendors/<path:filename>')
    def serve_landing_vendors(filename):
        return send_from_directory(os.path.join(app.root_path, 'landing_vendors'), filename)

    @app.route('/presentation')
    def serve_presentation():
        return send_from_directory(app.root_path, 'presentation.html')

    # Context processors
    @app.context_processor
    def inject_globals():
        unread_notifs = 0
        if session.get('login_id'):
            try:
                row = query_db(
                    "SELECT COUNT(*) as cnt FROM notifications WHERE user_id = ? AND is_read = 0",
                    (session['login_id'],),
                    one=True
                )
                unread_notifs = row['cnt'] if row else 0
            except Exception:
                pass

        return {
            'system': session.get('system', ensure_system_settings()),
            'status_list': STATUS_LIST,
            'unread_notifications_count': unread_notifs
        }

    # Register blueprints
    app.register_blueprint(api_bp)
    app.register_blueprint(page_bp)
    app.register_blueprint(customer_bp)
    app.register_blueprint(staff_bp)

    # 404 handler
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('404.html'), 404

    # 500 & Unhandled Exception handler
    @app.errorhandler(500)
    @app.errorhandler(Exception)
    def internal_server_error(e):
        app.logger.error(f"Internal server error: {e}", exc_info=True)
        from flask import request, jsonify
        if request.path.startswith('/api/') or 'ajax' in request.path or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                "status": "error",
                "message": "A system error occurred. Our technical team has logged the details."
            }), 500
        return render_template('500.html'), 500

    return app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
