import pytest

from movie_bot.config import Settings


def test_parse_admin_ids():
    assert Settings.parse_admin_ids("1, 2,3") == frozenset({1, 2, 3})


def test_parse_admin_ids_rejects_bad_value():
    with pytest.raises(RuntimeError):
        Settings.parse_admin_ids("1,nope")


def test_normalizes_postgres_url():
    assert (
        Settings.normalize_database_url("postgres://user:pass@host/db")
        == "postgresql+psycopg://user:pass@host/db"
    )
