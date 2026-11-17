import pytest
from fastapi.testclient import TestClient

from tests.helpers import BELGRADE
from where_to_go.api import create_app
from where_to_go.container import Container


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(lambda: Container.build(tmp_path))) as test_client:
        yield test_client


def test_requests_without_an_origin_pass(client):
    assert client.post("/cities", json=BELGRADE).status_code == 201


def test_the_app_own_page_passes(client):
    assert client.post("/cities", json=BELGRADE, headers={"Origin": "http://testserver"}).status_code == 201


def test_another_site_cannot_change_anything(client):
    response = client.post("/cities", json=BELGRADE, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert client.get("/cities").json() == []


def test_another_site_cannot_read_either(client):
    assert client.get("/settings", headers={"Origin": "https://evil.example"}).status_code == 403


def test_another_port_on_the_same_computer_is_another_site(client):
    assert client.get("/settings", headers={"Origin": "http://testserver:5180"}).status_code == 403


def test_a_page_without_an_address_is_refused(client):
    assert client.get("/settings", headers={"Origin": "null"}).status_code == 403


def test_no_cors_headers_are_given_to_other_sites(client):
    preflight = client.options("/phone-page", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "DELETE"})
    assert "access-control-allow-origin" not in preflight.headers
