import httpx
import respx

from where_to_go.images import ImageStore


@respx.mock
async def test_image_is_downloaded_once_and_bad_responses_are_skipped(tmp_path):
    good = respx.get("https://cdn.test/a.jpg").respond(200, content=b"jpg", headers={"content-type": "image/jpeg"})
    respx.get("https://cdn.test/gone.jpg").respond(404)
    respx.get("https://cdn.test/page").respond(200, text="<html>", headers={"content-type": "text/html"})
    respx.get("https://cdn.test/down.jpg").mock(side_effect=httpx.ConnectError("down"))
    async with httpx.AsyncClient() as client:
        store = ImageStore(tmp_path, client)
        name = await store.save("https://cdn.test/a.jpg?token=1")
        assert await store.save("https://cdn.test/a.jpg?token=2") == name
        assert good.call_count == 1
        assert [await store.save(f"https://cdn.test/{u}") for u in ("gone.jpg", "page", "down.jpg")] == [None] * 3
    assert store.path(name).read_bytes() == b"jpg"
    assert store.path("missing.jpg") is None
