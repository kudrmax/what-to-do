import pytest
from fastapi.testclient import TestClient

from tests.helpers import extraction_by_text, judge_same_titles
from where_to_go.api import create_app
from where_to_go.container import Container
from where_to_go.serving import AppWithInterface


@pytest.fixture
def interface(tmp_path):
    folder = tmp_path / "dist"
    (folder / "assets").mkdir(parents=True)
    (folder / "index.html").write_text("<html>interface</html>")
    (folder / "assets" / "app.js").write_text("console.log(1)")
    (folder / "favicon.svg").write_text("<svg/>")
    return folder


@pytest.fixture
def client(tmp_path, interface):
    api = create_app(lambda: Container.build(tmp_path / "data", extraction_llm=extraction_by_text({}), matching_llm=judge_same_titles()))
    with TestClient(AppWithInterface.build(api, interface)) as test_client:
        yield test_client


def test_api_lives_under_api(client):
    assert client.get("/api/settings").json()["recent_posts"] == 20
    assert client.get("/api/docs").status_code == 200


def test_interface_routes_get_the_index_and_files_are_served(client):
    assert client.get("/").text == "<html>interface</html>"
    assert client.get("/calendar").text == "<html>interface</html>"
    assert client.get("/event/12?day=2026-11-09").text == "<html>interface</html>"
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/favicon.svg").text == "<svg/>"


def test_files_outside_the_interface_are_not_served(client, tmp_path):
    (tmp_path / "secret.txt").write_text("secret")
    assert "secret" not in client.get("/..%2Fsecret.txt").text


def test_missing_build_is_reported(tmp_path):
    with pytest.raises(FileNotFoundError, match="build the interface"):
        AppWithInterface.build(create_app(lambda: None), tmp_path)


def test_a_column_added_to_a_model_is_added_to_an_old_database(tmp_path):
    import sqlite3

    from where_to_go.db import Database

    path = tmp_path / "old.sqlite3"
    Database(path).close()
    with sqlite3.connect(path) as old:
        old.execute("ALTER TABLE posts DROP COLUMN read_with")
    Database(path).close()
    with sqlite3.connect(path) as upgraded:
        assert "read_with" in {row[1] for row in upgraded.execute("PRAGMA table_info(posts)")}
