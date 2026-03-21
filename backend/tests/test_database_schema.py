from sqlalchemy import create_engine, inspect, text

from backend import database


def test_resolve_database_url_prefers_configured_database_url():
    url = database.resolve_database_url(
        env={"DATABASE_URL": "postgres://render-user:secret@render-host/db"},
        running_tests=False,
    )
    assert url == "postgres://render-user:secret@render-host/db"


def test_resolve_database_url_requires_database_url_by_default():
    try:
        database.resolve_database_url(env={}, running_tests=False)
        assert False, "Expected DATABASE_URL to be required by default"
    except RuntimeError as exc:
        assert "DATABASE_URL is required by default" in str(exc)


def test_resolve_database_url_allows_explicit_local_sqlite_opt_in():
    url = database.resolve_database_url(env={"ALLOW_LOCAL_SQLITE": "true"}, running_tests=False)
    assert url == database.DEFAULT_SQLITE_URL


def test_resolve_database_url_allows_sqlite_under_pytest():
    url = database.resolve_database_url(env={}, running_tests=True)
    assert url == database.DEFAULT_SQLITE_URL


def test_ensure_schema_handles_legacy_sqlite_timestamp_columns(monkeypatch, tmp_path):
    db_path = tmp_path / "legacy_learning_data.db"
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE players (
                    id INTEGER PRIMARY KEY,
                    username VARCHAR,
                    xp INTEGER,
                    level INTEGER,
                    location VARCHAR,
                    grade_level INTEGER,
                    learning_style VARCHAR,
                    sex VARCHAR,
                    birthday VARCHAR,
                    interests TEXT,
                    role VARCHAR,
                    password_hash VARCHAR,
                    email VARCHAR
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE topic_progress (
                    id INTEGER PRIMARY KEY,
                    player_id INTEGER,
                    topic_name VARCHAR,
                    status VARCHAR,
                    mastery_score INTEGER,
                    mistakes JSON,
                    last_state_snapshot JSON,
                    completed_nodes JSON,
                    current_node VARCHAR
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE interactions (
                    id INTEGER PRIMARY KEY,
                    timestamp TIMESTAMP,
                    username VARCHAR,
                    subject VARCHAR,
                    user_query TEXT,
                    agent_response TEXT,
                    source_node VARCHAR
                )
                """
            )
        )

    monkeypatch.setattr(database, "engine", engine)
    database.ensure_schema()

    inspector = inspect(engine)
    player_columns = {column["name"] for column in inspector.get_columns("players")}
    topic_columns = {column["name"] for column in inspector.get_columns("topic_progress")}

    assert "created_at" in player_columns
    assert "updated_at" in player_columns
    assert "password_changed_at" in player_columns
    assert "created_at" in topic_columns
    assert "updated_at" in topic_columns
    assert "learning_mode" in topic_columns
