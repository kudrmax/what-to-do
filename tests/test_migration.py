import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("migrate", Path(__file__).parent.parent / "scripts" / "migrate_first_schema.py")
migrate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate)


@pytest.mark.parametrize(
    "text,price",
    [
        ("1200 RSD, регистрация обязательна в директ", (1200, "RSD")),
        ("1000 RSD по регистрации, без неё 1500 RSD", (1000, "RSD")),
        ("500 RSD с репостом анонса в инстаграм, 800 RSD без репоста", (500, "RSD")),
        ("от 20€", (20, "EUR")),
        ("donation от 1500 RSD", (1500, "RSD")),
        ("1 500 динаров", (1500, "RSD")),
        ("Бесплатно", (0, None)),
        ("Вход свободный", (0, None)),
        ("Free donation", (None, None)),
        ("donation", (None, None)),
        (None, (None, None)),
    ],
)
def test_text_prices_of_the_first_version_become_numbers(text, price):
    assert migrate.TextPrice.parse(text) == price
