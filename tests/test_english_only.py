"""The app speaks English: its interface, messages and documentation have no Russian letters.

Russian stays only where it is the user's data or what reads that data: the Russian default tags, the prompts,
the card language installs had before it became the city's, and the search that forgives a wrong keyboard layout.
Tests and their fixtures are data too.
"""

import json
import re
import subprocess
from pathlib import Path

import pytest

from where_to_go.settings import AppSettings

ROOT = Path(__file__).resolve().parent.parent
CYRILLIC = re.compile(r"[Ѐ-ӿ]")

WHOLE_FILE = object()

ALLOWED: dict[str, object] = {
    "src/where_to_go/prompts.py": WHOLE_FILE,
    "src/where_to_go/search.py": WHOLE_FILE,
    "scripts/migrate_first_schema.py": WHOLE_FILE,
    "src/where_to_go/cities.py": (
        '"Концерт"',
        '"Вечеринка"',
        '"Лекция"',
        '"Стендап"',
        '"Театр"',
        '"Кино"',
        '"Выставка"',
        '"Игры и квизы"',
        '"Мастер-класс"',
        '"Встреча"',
        '"Спорт"',
        '"Прогулка"',
        '"Маркет"',
        '"Детям"',
        '"Другое"',
        '"русский"',
        '"русский язык"',
        '"по-русски"',
    ),
    "src/where_to_go/migrations.py": ('LEGACY_CARD_LANGUAGE = "русский"',),
    "scripts/common.py": ('"Белград"',),
    ".claude/skills/release/SKILL.md": ('"выпускай релиз"', '"сделай релиз"'),
}

# The API schema is generated from the backend and copies the defaults of the settings: the prompts and the
# language of descriptions.
_RUSSIAN_DEFAULTS = [str(field.default) for field in AppSettings.model_fields.values() if isinstance(field.default, str)]
_COPIED_DEFAULTS = tuple(
    {json.dumps(text, ensure_ascii=False)[1:-1] for text in _RUSSIAN_DEFAULTS}
    | {line.strip() for text in _RUSSIAN_DEFAULTS for line in text.splitlines() if line.strip()}
)
ALLOWED["frontend/openapi.json"] = _COPIED_DEFAULTS
ALLOWED["frontend/src/api/schema.d.ts"] = _COPIED_DEFAULTS

SKIPPED_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".icns", ".lock")
SKIPPED_NAMES = ("package-lock.json",)


def _is_test_data(path: str) -> bool:
    return (
        path.startswith("tests/")
        or path.startswith("frontend/src/test/")
        or bool(re.search(r"\.test\.tsx?$", path))
        or path.startswith("macos/Tests/")
    )


def _checked_files() -> list[str]:
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    return [
        path
        for path in tracked
        if not path.endswith(SKIPPED_SUFFIXES)
        and Path(path).name not in SKIPPED_NAMES
        and not _is_test_data(path)
        and ALLOWED.get(path) is not WHOLE_FILE
        and (ROOT / path).is_file()
    ]


def _russian_lines(path: str) -> list[str]:
    allowed = sorted(ALLOWED.get(path, ()), key=len, reverse=True)
    found = []
    for number, line in enumerate((ROOT / path).read_text(encoding="utf-8").splitlines(), start=1):
        for fragment in allowed:
            line = line.replace(fragment, "")
        if CYRILLIC.search(line):
            found.append(f"{path}:{number}: {line.strip()}")
    return found


def test_no_russian_letters_outside_user_data():
    found = [line for path in _checked_files() for line in _russian_lines(path)]
    assert not found, "Russian text in the app (translate it to English):\n" + "\n".join(found)


@pytest.mark.parametrize("path", sorted(set(ALLOWED) - {"frontend/openapi.json", "frontend/src/api/schema.d.ts"}))
def test_every_exception_still_has_russian_data(path):
    text = (ROOT / path).read_text(encoding="utf-8")
    allowed = ALLOWED[path]
    if allowed is WHOLE_FILE:
        assert CYRILLIC.search(text), f"{path} has no Russian left: drop it from ALLOWED"
    else:
        missing = [fragment for fragment in allowed if fragment not in text]
        assert not missing, f"{path} no longer has {missing}: drop them from ALLOWED"


def test_the_check_catches_russian(tmp_path, monkeypatch):
    sample = tmp_path / "sample.tsx"
    sample.write_text('<button>Обновить</button>\n<p>Refresh</p>\n', encoding="utf-8")
    monkeypatch.setattr(f"{__name__}.ROOT", tmp_path)
    assert _russian_lines("sample.tsx") == ["sample.tsx:1: <button>Обновить</button>"]
