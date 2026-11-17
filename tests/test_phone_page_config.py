import pytest
from fastapi.testclient import TestClient

from tests.helpers import extraction_by_text, judge_same_titles, photos_saying
from where_to_go.api import create_app
from where_to_go.container import Container
from where_to_go.db import Database
from where_to_go.phone_page.config import PhonePageConfig, PhonePageConfigRepository


@pytest.fixture
def client(tmp_path):
    app = create_app(
        lambda: Container.build(
            tmp_path, extraction_llm=extraction_by_text({}), matching_llm=judge_same_titles(), photo_llm=photos_saying()
        )
    )
    with TestClient(app) as test_client:
        yield test_client


def test_config_round_trip(tmp_path):
    repo = PhonePageConfigRepository(Database(tmp_path / "db.sqlite3"))
    assert repo.load() == PhonePageConfig()
    repo.update(repository="max/plans", token="t0k", password="pw")
    assert repo.load().repository == "max/plans" and repo.load().token == "t0k"


def test_secrets_do_not_reach_app_settings(client):
    container = client.app.state.container
    container.phone_config.update(token="t0k", password="pw")
    body = client.get("/settings").text
    assert "t0k" not in body and "pw" not in body
