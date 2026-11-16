"""Postgres row-level security and column privileges, exercised for real.

Needs the database from docker-compose: `make db-up`, then
PA_RAG_DATABASE_URL=postgresql://rag_gateway:rag_gateway_dev@localhost:5433/hr
"""

from __future__ import annotations

import psycopg
import pytest

from pa_rag.auth.directory import Directory
from pa_rag.config import DEFAULT_DATA_DIR
from pa_rag.tools.hr_db import HRDatabase

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def hr(database_url: str) -> HRDatabase:
    try:
        psycopg.connect(database_url, connect_timeout=3).close()
    except psycopg.OperationalError:
        pytest.skip("Postgres not reachable (run `make db-up`)")
    return HRDatabase(database_url)


@pytest.fixture(scope="module")
def directory() -> Directory:
    return Directory.from_file(DEFAULT_DATA_DIR / "directory.json")


def _ids(rows: list[dict[str, object]]) -> set[object]:
    return {r["employee_id"] for r in rows}


def test_employees_see_only_themselves(hr: HRDatabase, directory: Directory) -> None:
    assert _ids(hr.list_people(directory.resolve("ivy")).rows) == {"ivy"}


def test_managers_see_their_direct_reports(hr: HRDatabase, directory: Directory) -> None:
    assert _ids(hr.list_people(directory.resolve("dan")).rows) == {"dan", "erin", "ivy"}


def test_hr_comp_sees_everyone(hr: HRDatabase, directory: Directory) -> None:
    assert _ids(hr.list_people(directory.resolve("hana")).rows) == {
        "cora",
        "dan",
        "erin",
        "hana",
        "ivy",
    }


@pytest.mark.parametrize(("user_id", "target"), [("ivy", "Cora"), ("ivy", "Ivy"), ("dan", "Erin")])
def test_salary_column_is_denied_by_the_database(
    hr: HRDatabase, directory: Directory, user_id: str, target: str
) -> None:
    result = hr.get_salary(directory.resolve(user_id), target)
    assert not result.ok
    assert result.error == "access denied by database policy"


def test_hr_comp_can_read_salaries(hr: HRDatabase, directory: Directory) -> None:
    result = hr.get_salary(directory.resolve("hana"), "Cora")
    assert result.ok
    assert result.rows == [{"employee_id": "cora", "full_name": "Cora", "base_salary": 410000}]


def test_rls_fails_closed_without_a_user_id(database_url: str, hr: HRDatabase) -> None:
    with psycopg.connect(database_url) as conn, conn.transaction(), conn.cursor() as cur:
        cur.execute("SET LOCAL ROLE rag_employee")
        cur.execute("SELECT employee_id FROM compensation")
        assert cur.fetchall() == []


def test_the_gateway_login_itself_has_no_data_access(database_url: str, hr: HRDatabase) -> None:
    with (
        psycopg.connect(database_url) as conn,
        conn.cursor() as cur,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        cur.execute("SELECT employee_id FROM compensation")


def test_why_the_model_never_gets_raw_sql(database_url: str, hr: HRDatabase) -> None:
    """SET ROLE is not a boundary against arbitrary SQL on the same connection.

    This is the reason the HR tool exposes fixed, parameterized queries only. With
    free-form text-to-SQL, give each user (or tier) its own LOGIN role instead.
    """
    with psycopg.connect(database_url) as conn, conn.transaction(), conn.cursor() as cur:
        cur.execute("SET LOCAL ROLE rag_employee")
        cur.execute("RESET ROLE")  # what an injected statement could do...
        cur.execute("SET LOCAL ROLE rag_hr_comp")  # ...followed by this
        cur.execute("SELECT base_salary FROM compensation WHERE employee_id = 'cora'")
        assert cur.fetchone() == (410000,)
