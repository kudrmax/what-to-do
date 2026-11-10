from datetime import UTC, datetime

from tests.helpers import mention
from where_to_go.db import Database
from where_to_go.models import PhotoText
from where_to_go.originals import EventLines, OriginalPosts
from where_to_go.repositories import PhotoTextRepository

DIGEST = """Афиша недели

📎07.11 Суббота
17:00 Мастер-класс по керамике (https://t.me/a/1)
19:00 Неоклассика и минимализм: Alex Solely и струнный оркестр (https://t.me/a/2)
19:00 «Трудности перевода» — плейбек-перформанс (https://t.me/a/3)"""


def test_the_quoted_line_is_found_though_claude_dropped_its_link():
    assert EventLines.of(DIGEST, ["19:00 Неоклассика и минимализм: Alex Solely и струнный оркестр"]) == [4]


def test_a_quote_may_be_part_of_a_line_or_span_more_than_it():
    assert EventLines.of(DIGEST, ["Alex Solely и струнный оркестр"]) == [4]
    assert EventLines.of("Лекция\nО грибах", ["Лекция о грибах в субботу"]) == []


def test_short_quotes_match_whole_lines_only():
    assert EventLines.of(DIGEST, ["19:00"]) == []
    assert EventLines.of("Чай\nКофе", ["чай"]) == [0]


def test_no_quotes_means_the_whole_post_is_about_the_event():
    assert EventLines.of(DIGEST, []) == []


def posts(*mentions):
    return OriginalPosts(PhotoTextRepository(Database(":memory:"))).in_order(list(mentions))


def test_the_organizer_comes_first_then_the_most_detailed_then_the_newest():
    afisha = mention(1, description="Коротко", published=datetime(2026, 11, 5, tzinfo=UTC))
    detailed = mention(2, description="Подробное описание концерта", published=datetime(2026, 11, 1, tzinfo=UTC))
    organizer = mention(3, description="Коротко", organizer=True, published=datetime(2026, 11, 1, tzinfo=UTC))
    newer = mention(4, description="Коротко", published=datetime(2026, 11, 9, tzinfo=UTC))
    assert [m.id for m in posts(afisha, detailed, organizer, newer)] == [3, 2, 4, 1]


def test_each_post_comes_with_its_photos_what_claude_read_on_them_and_this_events_lines():
    texts = PhotoTextRepository(Database(":memory:"))
    texts.save([PhotoText(image="a.jpg", text="ВС, 22.11 | 18:00", shows="poster", read_with="r")])
    one = mention(1)
    one.post.image_paths = ["a.jpg", "b.jpg"]
    one.post.text = DIGEST
    one.image_index = 1
    one.data.post_lines = ["17:00 Мастер-класс по керамике"]

    [shown] = OriginalPosts(texts).present([one])

    assert [(p.url, p.text) for p in shown.photos] == [("/images/a.jpg", "ВС, 22.11 | 18:00"), ("/images/b.jpg", None)]
    assert shown.event_photo == 1 and shown.event_lines == [3]
