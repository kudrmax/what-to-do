from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

WORD = re.compile(r"\w+")
LATIN_KEYS = "`qwertyuiop[]asdfghjkl;'zxcvbnm,.~QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>"
CYRILLIC_KEYS = "ёйцукенгшщзхъфывапролджэячсмитьбюЁЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ"
OTHER_LAYOUT = str.maketrans(LATIN_KEYS + CYRILLIC_KEYS, CYRILLIC_KEYS + LATIN_KEYS)
TYPO_MIN_LENGTH = 4


def words(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKC", text).casefold().replace("ё", "е")
    return WORD.findall(folded)


def one_typo_apart(a: str, b: str) -> bool:
    """One letter missed, added, replaced, or two neighbours swapped."""
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
        if len(diff) != 2:
            return len(diff) <= 1
        i, j = diff
        return j == i + 1 and a[i] == b[j] and a[j] == b[i]
    short, long = sorted((a, b), key=len)
    i = next((k for k, (x, y) in enumerate(zip(short, long)) if x != y), len(short))
    return short[i:] == long[i + 1 :]


def found_in(term: str, word: str) -> bool:
    if term in word:
        return True
    if len(term) < TYPO_MIN_LENGTH:
        return False
    return any(one_typo_apart(term, word[: len(term) + shift]) for shift in (-1, 0, 1))


class SearchQuery:
    """What the user typed in search: every word of it has to be found in the text.

    A word is found as any part of a text word («импро иг» finds «Импровизационные игры»), ignoring case and
    е/ё, forgiving one typo in a word of four letters or more.
    """

    def __init__(self, text: str) -> None:
        self._text = text
        self._terms = words(text)

    def __bool__(self) -> bool:
        return bool(self._terms)

    def in_other_layout(self) -> SearchQuery:
        """The same keys pressed in the other keyboard layout: «bvghj» is «импро»."""
        return SearchQuery(self._text.translate(OTHER_LAYOUT))

    def matches(self, texts: Iterable[str | None]) -> bool:
        haystack = [word for text in texts if text for word in words(text)]
        return all(any(found_in(term, word) for word in haystack) for term in self._terms)
