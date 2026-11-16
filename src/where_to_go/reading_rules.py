import hashlib


class ReadingRules:
    """Posts and photos read under other rules are read again at the next refresh. The rules change only here, by hand,
    when what Claude read before is wrong: a prompt edited in settings applies to new posts and costs no Claude calls.
    Change POSTS together with PHOTOS, since a post is read with the text of its photos.
    The first values are the fingerprints the readings already carried, so switching to them re-read nothing."""

    POSTS = "digests-read-whole-1"
    PHOTOS = "8a0769ce1a02a386"

    @classmethod
    def posts(cls, priority_wish: str, card_language: str) -> str:
        """A new priority wish or card language reads the recent posts again: the cards already there get flagged by
        the wish and rewritten in the language too."""
        wish = f":{_digest(priority_wish)}" if priority_wish else ""
        return f"{cls.POSTS}{wish}{cls.language_part(card_language)}"

    @staticmethod
    def language_part(card_language: str) -> str:
        return f":lang-{_digest(card_language.strip().casefold())}"


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:8]
