"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from app import create_app
from app.extensions import db
from app.models import BusinessProfile


@pytest.fixture
def app(tmp_path):
    db_path = tmp_path / "test.db"
    application = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
            "RATELIMIT_ENABLED": False,
            "SECRET_KEY": "test-secret",
            "OPENAI_API_KEY": "test-openai",
            "DATAFORSEO_LOGIN": "test-login",
            "DATAFORSEO_PASSWORD": "test-password",
        }
    )
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def profile(app):
    row = BusinessProfile(
        name="Surfer SEO",
        domain="surferseo.com",
        industry="SEO Software",
        description="AI-powered SEO content optimization tool",
        competitors=["clearscope.io", "marketmuse.com", "frase.io"],
        status="created",
    )
    db.session.add(row)
    db.session.commit()
    return row
