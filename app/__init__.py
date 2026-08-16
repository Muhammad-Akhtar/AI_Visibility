"""Application factory."""

from __future__ import annotations

import logging

from flask import Flask, jsonify

from app.config import Config
from app.errors import register_error_handlers
from app.extensions import db, limiter, migrate
from app.logging_setup import configure_logging


def create_app(config: dict | None = None) -> Flask:
    configure_logging()
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(Config)
    if config:
        app.config.update(config)

    if app.config.get("TESTING"):
        app.config["RATELIMIT_ENABLED"] = False

    db.init_app(app)
    migrate.init_app(app, db, directory="migrations")
    limiter.init_app(app)

    # Ensure models are registered with SQLAlchemy / Alembic.
    from app import models as _models  # noqa: F401

    register_error_handlers(app)

    from app.api.profiles import profiles_bp
    from app.api.queries import queries_bp
    from app.web import web_bp

    app.register_blueprint(profiles_bp, url_prefix="/api/v1/profiles")
    app.register_blueprint(queries_bp, url_prefix="/api/v1/queries")
    app.register_blueprint(web_bp)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/api/v1/health")
    def api_health():
        return jsonify({"status": "ok"})

    app.logger.setLevel(logging.INFO)
    return app
