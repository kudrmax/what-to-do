import base64
import json

import httpx
import pytest
import respx

from where_to_go.phone_page.github import PAGES_OFF, RATE_LIMITED, GitHubPagesPublisher, PublishError

API = "https://api.github.com/repos/max/plans"
REPO = "max/plans"
TOKEN = "ghp_secret_token"


def body(route, index=-1):
    return json.loads(route.calls[index].request.content)


def root_tree(*paths):
    return {"sha": "t0", "truncated": False, "tree": [{"path": p, "mode": "100644", "type": "blob", "sha": f"s-{p}"} for p in paths]}


@pytest.fixture
async def publisher():
    async with httpx.AsyncClient() as client:
        yield GitHubPagesPublisher(client)


@respx.mock
@pytest.mark.parametrize(
    ("status", "payload", "message"),
    [
        (404, {"message": "Not Found"}, "Repository not found"),
        (200, {"permissions": {"pull": True, "push": False}}, "The token has no access to this repository"),
        (403, {"message": "Resource not accessible"}, "The token has no access to this repository"),
        (401, {"message": "Bad credentials"}, "The token expired or was revoked"),
    ],
)
async def test_check_maps_errors(publisher, status, payload, message):
    respx.get(API).respond(status, json=payload)
    with pytest.raises(PublishError) as error:
        await publisher.check(REPO, TOKEN)
    assert str(error.value) == message


@respx.mock
@pytest.mark.parametrize(
    ("status", "headers"),
    [
        (403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "2000000000"}),
        (403, {"retry-after": "60"}),
        (429, {"retry-after": "60"}),
    ],
)
async def test_rate_limit_is_not_mistaken_for_missing_access(publisher, status, headers):
    respx.get(API).respond(status, json={"message": "API rate limit exceeded"}, headers=headers)
    with pytest.raises(PublishError) as error:
        await publisher.check(REPO, TOKEN)
    assert str(error.value) == RATE_LIMITED


@respx.mock
async def test_rate_limit_during_a_publish_is_reported_as_such(publisher):
    respx.post(f"{API}/git/blobs").respond(403, json={"message": "You have exceeded a secondary rate limit"}, headers={"retry-after": "30"})
    with pytest.raises(PublishError) as error:
        await publisher.replace(REPO, TOKEN, {"index.html": b"x"}, {})
    assert str(error.value) == RATE_LIMITED


@respx.mock
async def test_check_sends_headers_and_accepts_push_access(publisher):
    route = respx.get(API).respond(200, json={"permissions": {"push": True}})
    await publisher.check(REPO, TOKEN)
    headers = route.calls[0].request.headers
    assert headers["Authorization"] == f"Bearer {TOKEN}"
    assert headers["Accept"] == "application/vnd.github+json"
    assert headers["X-GitHub-Api-Version"] == "2022-11-28"


@respx.mock
async def test_malformed_repository_is_refused_without_a_request(publisher):
    with pytest.raises(PublishError):
        await publisher.check("../../user", TOKEN)
    assert respx.calls.call_count == 0


@respx.mock
async def test_network_failure_becomes_publish_error_without_token(publisher):
    respx.get(API).mock(side_effect=httpx.ConnectError(f"down {TOKEN}"))
    with pytest.raises(PublishError) as error:
        await publisher.check(REPO, TOKEN)
    assert TOKEN not in str(error.value)


@respx.mock
async def test_unexpected_status_becomes_publish_error(publisher):
    respx.get(f"{API}/pages").respond(500, json={"message": "Server Error"})
    with pytest.raises(PublishError) as error:
        await publisher.ensure_pages(REPO, TOKEN)
    assert "500" in str(error.value)


@respx.mock
async def test_readme_only_repository_is_accepted(publisher):
    respx.get(f"{API}/git/trees/main").respond(200, json=root_tree("README.md", "LICENSE", ".gitignore"))
    await publisher.ensure_empty_or_ours(REPO, TOKEN)


@respx.mock
@pytest.mark.parametrize("status", [409, 404])
async def test_repository_without_commits_is_accepted(publisher, status):
    respx.get(f"{API}/git/trees/main").respond(status, json={"message": "Git Repository is empty."})
    await publisher.ensure_empty_or_ours(REPO, TOKEN)


@respx.mock
async def test_foreign_files_are_refused(publisher):
    respx.get(f"{API}/git/trees/main").respond(200, json=root_tree("README.md", "main.py"))
    with pytest.raises(PublishError) as error:
        await publisher.ensure_empty_or_ours(REPO, TOKEN)
    assert str(error.value) == "This repository already has other files. Create a new empty one."


@respx.mock
async def test_marker_makes_repository_ours(publisher):
    respx.get(f"{API}/git/trees/main").respond(200, json=root_tree(".what-to-do-phone-page", "index.html", "data.bin"))
    await publisher.ensure_empty_or_ours(REPO, TOKEN)


@respx.mock
async def test_pages_url_returned_when_on(publisher):
    respx.get(f"{API}/pages").respond(200, json={"html_url": "https://max.github.io/plans/"})
    create = respx.post(f"{API}/pages")
    assert await publisher.ensure_pages(REPO, TOKEN) == "https://max.github.io/plans/"
    assert not create.called


@respx.mock
async def test_pages_turned_on_when_off(publisher):
    respx.get(f"{API}/pages").respond(404, json={"message": "Not Found"})
    create = respx.post(f"{API}/pages").respond(201, json={"html_url": "https://max.github.io/plans/"})
    assert await publisher.ensure_pages(REPO, TOKEN) == "https://max.github.io/plans/"
    assert body(create) == {"build_type": "legacy", "source": {"branch": "main", "path": "/"}}


@respx.mock
@pytest.mark.parametrize("status", [403, 404])
async def test_pages_the_token_cannot_turn_on_ask_the_user_to(publisher, status):
    respx.get(f"{API}/pages").respond(404, json={"message": "Not Found"})
    respx.post(f"{API}/pages").respond(status, json={"message": "Resource not accessible by personal access token"})
    with pytest.raises(PublishError) as error:
        await publisher.ensure_pages(REPO, TOKEN)
    assert str(error.value) == PAGES_OFF


@respx.mock
async def test_rate_limit_on_turning_pages_on_is_not_taken_for_pages_off(publisher):
    respx.get(f"{API}/pages").respond(404, json={"message": "Not Found"})
    respx.post(f"{API}/pages").respond(403, json={"message": "API rate limit exceeded"}, headers={"x-ratelimit-remaining": "0"})
    with pytest.raises(PublishError) as error:
        await publisher.ensure_pages(REPO, TOKEN)
    assert str(error.value) == RATE_LIMITED


@respx.mock
async def test_current_blobs_lists_nested_files(publisher):
    respx.get(f"{API}/git/trees/main", params={"recursive": "1"}).respond(
        200,
        json={
            "sha": "t0",
            "truncated": False,
            "tree": [
                {"path": "data.bin", "mode": "100644", "type": "blob", "sha": "b1"},
                {"path": "posters", "mode": "040000", "type": "tree", "sha": "t1"},
                {"path": "posters/a.bin", "mode": "100644", "type": "blob", "sha": "b2"},
            ],
        },
    )
    assert await publisher.current_blobs(REPO, TOKEN) == {"data.bin": "b1", "posters/a.bin": "b2"}


@respx.mock
async def test_current_blobs_of_empty_repository(publisher):
    respx.get(f"{API}/git/trees/main").respond(409, json={"message": "Git Repository is empty."})
    assert await publisher.current_blobs(REPO, TOKEN) == {}


@respx.mock
async def test_replace_makes_parentless_commit_and_forces_ref(publisher):
    blobs = respx.post(f"{API}/git/blobs").mock(
        side_effect=[httpx.Response(201, json={"sha": "new-index"}), httpx.Response(201, json={"sha": "new-data"})]
    )
    tree = respx.post(f"{API}/git/trees").respond(201, json={"sha": "tree1"})
    commit = respx.post(f"{API}/git/commits").respond(201, json={"sha": "commit1"})
    ref = respx.patch(f"{API}/git/refs/heads/main").respond(200, json={"object": {"sha": "commit1"}})

    await publisher.replace(
        REPO,
        TOKEN,
        files={"index.html": b"<html>", "data.bin": b"WTD1\x00\xff"},
        reuse={"posters/a.bin": "old-poster"},
    )

    assert blobs.call_count == 2
    assert body(blobs, 1) == {"content": base64.b64encode(b"WTD1\x00\xff").decode(), "encoding": "base64"}
    entries = {e["path"]: e for e in body(tree)["tree"]}
    assert "base_tree" not in body(tree)
    assert entries == {
        "index.html": {"path": "index.html", "mode": "100644", "type": "blob", "sha": "new-index"},
        "data.bin": {"path": "data.bin", "mode": "100644", "type": "blob", "sha": "new-data"},
        "posters/a.bin": {"path": "posters/a.bin", "mode": "100644", "type": "blob", "sha": "old-poster"},
    }
    assert body(commit)["parents"] == []
    assert body(commit)["tree"] == "tree1"
    assert body(ref) == {"sha": "commit1", "force": True}


@respx.mock
async def test_replace_creates_main_when_missing(publisher):
    respx.post(f"{API}/git/blobs").respond(201, json={"sha": "b1"})
    respx.post(f"{API}/git/trees").respond(201, json={"sha": "tree1"})
    respx.post(f"{API}/git/commits").respond(201, json={"sha": "commit1"})
    respx.patch(f"{API}/git/refs/heads/main").respond(422, json={"message": "Reference does not exist"})
    create = respx.post(f"{API}/git/refs").respond(201, json={"ref": "refs/heads/main"})

    await publisher.replace(REPO, TOKEN, files={"index.html": b"x"}, reuse={})

    assert body(create) == {"ref": "refs/heads/main", "sha": "commit1"}


@respx.mock
async def test_empty_repository_is_bootstrapped(publisher):
    blobs = respx.post(f"{API}/git/blobs").mock(
        side_effect=[
            httpx.Response(409, json={"message": "Git Repository is empty."}),
            httpx.Response(201, json={"sha": "b1"}),
            httpx.Response(201, json={"sha": "b2"}),
        ]
    )
    bootstrap = respx.put(f"{API}/contents/.what-to-do-phone-page").respond(201, json={"content": {"sha": "m"}})
    respx.post(f"{API}/git/trees").respond(201, json={"sha": "tree1"})
    respx.post(f"{API}/git/commits").respond(201, json={"sha": "commit1"})
    ref = respx.patch(f"{API}/git/refs/heads/main").respond(200, json={})

    await publisher.replace(REPO, TOKEN, files={"index.html": b"a", "data.bin": b"b"}, reuse={})

    assert bootstrap.call_count == 1
    assert "content" in body(bootstrap) and "message" in body(bootstrap)
    assert blobs.call_count == 3
    assert ref.called


@respx.mock
async def test_bootstrap_happens_only_once(publisher):
    respx.post(f"{API}/git/blobs").respond(409, json={"message": "Git Repository is empty."})
    bootstrap = respx.put(f"{API}/contents/.what-to-do-phone-page").respond(201, json={})
    with pytest.raises(PublishError):
        await publisher.replace(REPO, TOKEN, files={"index.html": b"a"}, reuse={})
    assert bootstrap.call_count == 1
