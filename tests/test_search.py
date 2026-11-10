import pytest

from where_to_go.search import SearchQuery

TITLE = ["Импровизационные игры для взрослых", "Тёплый вечер в «Дорćоле»"]


@pytest.mark.parametrize(
    "typed",
    [
        "импро иг",
        "ИМПРОВИЗАЦИЯ",
        "игры импров",
        "визац",
        "теплый",
        "ТЁПЛ",
        "импровезац",
        "ипмро",
        "взрослых вечер",
        "дорćол",
    ],
)
def test_finds_parts_of_words_in_any_case_and_with_a_typo(typed):
    assert SearchQuery(typed).matches(TITLE)


@pytest.mark.parametrize("typed", ["импро танцы", "джаз", "игрок", "ри"])
def test_every_word_has_to_be_found(typed):
    assert not SearchQuery(typed).matches(TITLE)


def test_looks_through_every_given_text_and_skips_missing_ones():
    assert SearchQuery("квиз белград").matches(["Квиз", None, "ул. Белградская, 5"])


def test_empty_query_is_falsy_and_finds_everything():
    assert not SearchQuery("  , ")
    assert SearchQuery("").matches([])


def test_other_layout_turns_latin_keys_into_cyrillic_and_back():
    assert SearchQuery("bvghj").in_other_layout().matches(TITLE)
    assert SearchQuery("nt[yj").in_other_layout().matches(["Техно-вечеринка"])
    assert SearchQuery("офяя").in_other_layout().matches(["Jazz jam"])
