import logging

from fastapi.testclient import TestClient

from where_to_go.api import create_app
from where_to_go.container import Container


def test_an_interface_timing_lands_in_the_log(tmp_path, caplog):
    app = create_app(lambda: Container.build(tmp_path))
    timing = {"action": "mark", "screen": "/?view=review", "phases": {"saved": 6.4, "reloaded": 41.2, "shown": 230.7}, "blocked": 180.2}
    with TestClient(app) as client, caplog.at_level(logging.INFO, logger="where_to_go.timings"):
        response = client.post("/timings", json=timing)
    assert response.status_code == 204
    assert "mark on /?view=review: saved=6ms reloaded=41ms shown=231ms blocked=180ms" in caplog.text


def test_a_timing_with_too_many_phases_is_refused(tmp_path):
    app = create_app(lambda: Container.build(tmp_path))
    timing = {"action": "mark", "screen": "/", "phases": {f"p{i}": 1.0 for i in range(21)}, "blocked": 0}
    with TestClient(app) as client:
        assert client.post("/timings", json=timing).status_code == 422


def test_a_freeze_has_no_phases_only_the_blocked_time():
    from where_to_go.api.timings import InterfaceTiming

    assert InterfaceTiming(action="freeze", screen="/", phases={}, blocked=558.4).line() == "freeze on /: blocked=558ms"
