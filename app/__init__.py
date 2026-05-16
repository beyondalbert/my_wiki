"""Application factory."""
import os
from pathlib import Path

from flask import Flask, render_template

from .config import get_config
from .extensions import db, migrate, login_manager, csrf


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(
        __name__,
        instance_relative_config=True,
        static_folder="static",
        template_folder="templates",
    )
    cfg = get_config(config_name)
    app.config.from_object(cfg)

    _ensure_instance_dirs(app)
    _register_extensions(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    _register_context(app)
    _register_cli(app)

    return app


def _ensure_instance_dirs(app: Flask) -> None:
    for key in ("UPLOAD_DIR", "AI_WIKI_DIR"):
        path = app.config.get(key)
        if path:
            Path(path).mkdir(parents=True, exist_ok=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)


def _register_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Register user loader
    from .models.user import User

    @login_manager.user_loader
    def load_user(user_id: str):
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None


def _register_blueprints(app: Flask) -> None:
    from .blueprints.auth import bp as auth_bp
    from .blueprints.user import bp as user_bp
    from .blueprints.admin import bp as admin_bp
    from .blueprints.kb import bp as kb_bp
    from .blueprints.doc import bp as doc_bp
    from .blueprints.share import bp as share_bp
    from .blueprints.ai import bp as ai_bp
    from .blueprints.main import bp as main_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(user_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(kb_bp, url_prefix="/kb")
    app.register_blueprint(doc_bp, url_prefix="/doc")
    app.register_blueprint(share_bp, url_prefix="/share")
    app.register_blueprint(ai_bp, url_prefix="/ai")


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(403)
    def forbidden(_):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(_):
        return render_template("errors/500.html"), 500


def _register_context(app: Flask) -> None:
    @app.context_processor
    def inject_globals():
        return {
            "site_name": "麦威知识库",
        }


def _register_cli(app: Flask) -> None:
    from .cli import register_cli
    register_cli(app)
