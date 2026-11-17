import colorsys
import io

import av
import httpx
import pytest
import respx
from PIL import Image

from where_to_go.frames import MAX_FRAMES, VideoFrames

RED, BLUE = (255, 0, 0), (0, 0, 255)


def make_video(colors: list[tuple[int, int, int]], seconds_each: int) -> bytes:
    """A video that shows each color for seconds_each seconds."""
    buffer = io.BytesIO()
    with av.open(buffer, "w", format="mp4") as container:
        stream = container.add_stream("mpeg4", rate=2)
        stream.width, stream.height, stream.pix_fmt = 64, 64, "yuv420p"
        for color in colors:
            for _ in range(2 * seconds_each):
                frame = av.VideoFrame.from_image(Image.new("RGB", (64, 64), color))
                container.mux(stream.encode(frame))
        container.mux(stream.encode())
    return buffer.getvalue()


def pixel(path) -> tuple[int, int, int]:
    return Image.open(path).convert("RGB").getpixel((32, 32))


def is_close(actual, expected) -> bool:
    return all(abs(a - b) < 40 for a, b in zip(actual, expected))


@pytest.fixture
async def frames(tmp_path):
    async with httpx.AsyncClient() as client:
        yield VideoFrames(tmp_path, client)


@respx.mock
async def test_frames_that_look_alike_are_kept_once(frames, tmp_path):
    respx.get("https://cdn.test/a.mp4").respond(200, content=make_video([RED, BLUE], 5))

    names = await frames.save("https://cdn.test/a.mp4?token=1")

    assert len(names) == 2 and all(n.endswith(".jpg") for n in names)
    assert is_close(pixel(tmp_path / names[0]), RED) and is_close(pixel(tmp_path / names[1]), BLUE)


@respx.mock
async def test_a_long_changing_video_gives_at_most_six_frames_spread_over_it(frames, tmp_path):
    colors = [tuple(int(c * 255) for c in colorsys.hsv_to_rgb(i / 30, 1, 1)) for i in range(30)]
    respx.get("https://cdn.test/a.mp4").respond(200, content=make_video(colors, 1))

    names = await frames.save("https://cdn.test/a.mp4")

    assert len(names) == MAX_FRAMES
    assert is_close(pixel(tmp_path / names[0]), colors[0])
    assert not is_close(pixel(tmp_path / names[-1]), colors[0])


@respx.mock
async def test_names_do_not_depend_on_the_query_and_a_known_video_is_not_downloaded_again(frames):
    route = respx.get(url__startswith="https://cdn.test/a.mp4").respond(200, content=make_video([RED, BLUE], 5))

    first = await frames.save("https://cdn.test/a.mp4?a=1")
    second = await frames.save("https://cdn.test/a.mp4?a=2")

    assert first == second and route.call_count == 1


@respx.mock
async def test_a_body_that_is_not_a_video_gives_no_frames(frames):
    respx.get("https://cdn.test/a.mp4").respond(200, content=b"not a video at all")

    assert await frames.save("https://cdn.test/a.mp4") == []


@respx.mock
async def test_a_missing_video_gives_no_frames(frames):
    respx.get("https://cdn.test/a.mp4").respond(404)

    assert await frames.save("https://cdn.test/a.mp4") == []


@respx.mock
async def test_a_network_error_gives_no_frames(frames):
    respx.get("https://cdn.test/a.mp4").mock(side_effect=httpx.ConnectError("down"))

    assert await frames.save("https://cdn.test/a.mp4") == []


@respx.mock
async def test_a_video_over_the_size_limit_is_not_read(frames, monkeypatch):
    monkeypatch.setattr("where_to_go.frames.MAX_VIDEO_BYTES", 100)
    respx.get("https://cdn.test/a.mp4").respond(200, content=make_video([RED, BLUE], 5))

    assert await frames.save("https://cdn.test/a.mp4") == []
