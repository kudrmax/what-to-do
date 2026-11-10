class ReadingRules:
    """Posts and photos read under other rules are read again at the next refresh. The rules change only here, by hand,
    when what Claude read before is wrong: a prompt edited in settings applies to new posts and costs no Claude calls.
    Change POSTS together with PHOTOS, since a post is read with the text of its photos.
    The first values are the fingerprints the readings already carried, so switching to them re-read nothing."""

    POSTS = "a70fb071ee6f7092"
    PHOTOS = "8a0769ce1a02a386"
