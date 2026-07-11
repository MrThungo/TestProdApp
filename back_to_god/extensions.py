from __future__ import annotations

from flask import Flask


try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import DeclarativeBase, scoped_session, sessionmaker

    class Base(DeclarativeBase):
        pass

    db_session = scoped_session(
        sessionmaker(autoflush=False, expire_on_commit=False)
    )
    SQLALCHEMY_AVAILABLE = True
except ModuleNotFoundError:
    Base = None
    db_session = None
    create_engine = None
    SQLALCHEMY_AVAILABLE = False


engine = None


def init_sqlalchemy(app: Flask) -> None:
    app.extensions["sqlalchemy_available"] = SQLALCHEMY_AVAILABLE
    if not SQLALCHEMY_AVAILABLE:
        return

    global engine
    engine = create_engine(app.config["SQLALCHEMY_DATABASE_URI"], future=True)
    db_session.configure(bind=engine)
    app.extensions["sqlalchemy_engine"] = engine
    app.extensions["sqlalchemy_session"] = db_session

    @app.teardown_appcontext
    def remove_sqlalchemy_session(error: Exception | None = None) -> None:
        db_session.remove()


def create_model_tables() -> None:
    if not SQLALCHEMY_AVAILABLE or engine is None:
        return

    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
