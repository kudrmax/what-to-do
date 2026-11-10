"""Default prompts. The user can change them in settings; these are what «вернуть как было» brings back."""

EXTRACTION_PLACEHOLDERS = ("city", "language", "tags", "fallback")

EXTRACTION = """You turn Telegram channel posts into event cards for a person who lives in {city} and looks for things to do in person.

For every post return the events and places it announces. Most posts announce nothing: return empty lists for them.

What to keep
- Offline events that take place in {city}. Drop online events, events in other cities, ads, giveaways, news and reports about events that already happened.
- A digest post that lists many events becomes one item per event.
- A place with no date goes to "places", never to "events".
- A follow-up about an event announced earlier is an item too: a post that adds details (update_kind "details"), moves it ("reschedule") or cancels it ("cancellation"), e.g. «Зачем идти на церемонию к Юле?» or «Сегодня лекции не будет». Name the event as the earlier announcement would. Resolve «сегодня», «завтра» and weekdays against the publication date; when the post gives no date at all, start_date is null. Only details and cancellations may go without a date.

Photos
- Each post lists its photos by index: "shows" says what the photo is, "text" is the text on it, transcribed word for word. Read them as part of the post: posters and event cards often carry the date, time, price, venue and the whole description.
- For every event give "photo": the index of its post's photo that shows that event.

The description language is {language}. Allowed tags: {tags}. If none fits, use exactly "{fallback}".
Each field's meaning is in the schema."""

PHOTOS = """You transcribe the photos of Telegram posts that announce events: posters, event cards, schedules, digests.

Every photo comes after its caption with its number. Return one item per photo. Each field's meaning is in the schema."""

MATCHING = """You merge duplicate event announcements collected from several Telegram channels.

You get existing event cards and new announcements. For every new announcement decide whether it describes the same real-world event as one of the existing cards, as one of the earlier new announcements, or neither.

Same event: the same happening at the same place on the same date, even when titles differ or are in different languages. Also the same: a post that reschedules, cancels or adds details to an event announced earlier (update_kind says so), and a single date of a recurring event that has a recurring card.
Not the same: different events at the same venue on the same day; the same show or tour on different dates; different sessions of a festival when each is its own event.

An announcement without a start_date is a follow-up its channel posted about one of its own events; the existing cards offered for it are that channel's. Pick the card it is about by title, description and venue; if none clearly fits, leave both fields null.

Never set both same_as_card and same_as_announcement."""
