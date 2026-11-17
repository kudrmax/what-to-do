import base64
import re
from typing import Any

import httpx

API = "https://api.github.com"
BRANCH = "main"
MARKER = ".what-to-do-phone-page"
GITHUB_STARTER_FILES = frozenset({"README.md", "LICENSE", ".gitignore"})
REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+")
COMMIT_MESSAGE = "Publish the phone page"


class PublishError(Exception):
    pass


class _EmptyRepository(Exception):
    pass


class _GitHubSession:
    def __init__(self, http: httpx.AsyncClient, repository: str, token: str) -> None:
        if not REPOSITORY_PATTERN.fullmatch(repository) or ".." in repository:
            raise PublishError("The repository must look like owner/name")
        self._http = http
        self._base = f"{API}/repos/{repository}"
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._http.request(method, self._base + path, headers=self._headers, **kwargs)
        except httpx.HTTPError:
            raise PublishError("Could not reach GitHub. Check the internet connection.") from None
        if response.status_code == 401:
            raise PublishError("The token expired or was revoked")
        return response

    async def expect(self, method: str, path: str, *ok: int, **kwargs: Any) -> dict[str, Any]:
        response = await self.send(method, path, **kwargs)
        if response.status_code not in ok:
            raise _unexpected(response)
        return response.json()


def _unexpected(response: httpx.Response) -> PublishError:
    if response.status_code == 403:
        return PublishError("The token has no access to this repository")
    try:
        detail = response.json().get("message")
    except ValueError:
        detail = None
    suffix = f": {detail}" if isinstance(detail, str) and detail else ""
    return PublishError(f"GitHub refused the request ({response.status_code}){suffix}")


class GitHubPagesPublisher:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def check(self, repository: str, token: str) -> None:
        session = self._session(repository, token)
        response = await session.send("GET", "")
        if response.status_code == 404:
            raise PublishError("Repository not found")
        if response.status_code != 200:
            raise _unexpected(response)
        if not response.json().get("permissions", {}).get("push"):
            raise PublishError("The token has no access to this repository")

    async def ensure_empty_or_ours(self, repository: str, token: str) -> None:
        entries = await self._tree(self._session(repository, token), recursive=False)
        paths = {entry["path"] for entry in entries}
        if MARKER in paths or paths <= GITHUB_STARTER_FILES:
            return
        raise PublishError("This repository already has other files. Create a new empty one.")

    async def ensure_pages(self, repository: str, token: str) -> str:
        session = self._session(repository, token)
        response = await session.send("GET", "/pages")
        if response.status_code == 200:
            return self._site_url(repository, response.json())
        if response.status_code != 404:
            raise _unexpected(response)
        site = await session.expect(
            "POST",
            "/pages",
            201,
            json={"build_type": "legacy", "source": {"branch": BRANCH, "path": "/"}},
        )
        return self._site_url(repository, site)

    async def current_blobs(self, repository: str, token: str) -> dict[str, str]:
        entries = await self._tree(self._session(repository, token), recursive=True)
        return {entry["path"]: entry["sha"] for entry in entries if entry["type"] == "blob"}

    async def replace(self, repository: str, token: str, files: dict[str, bytes], reuse: dict[str, str]) -> None:
        session = self._session(repository, token)
        shas = dict(reuse)
        for path, content in files.items():
            shas[path] = await self._blob_in_any_repository(session, content)
        tree = await session.expect(
            "POST",
            "/git/trees",
            201,
            json={"tree": [{"path": p, "mode": "100644", "type": "blob", "sha": s} for p, s in shas.items()]},
        )
        commit = await session.expect(
            "POST",
            "/git/commits",
            201,
            json={"message": COMMIT_MESSAGE, "tree": tree["sha"], "parents": []},
        )
        await self._move_branch(session, commit["sha"])

    def _session(self, repository: str, token: str) -> _GitHubSession:
        return _GitHubSession(self._http, repository, token)

    @staticmethod
    async def _tree(session: _GitHubSession, recursive: bool) -> list[dict[str, Any]]:
        params = {"recursive": "1"} if recursive else None
        response = await session.send("GET", f"/git/trees/{BRANCH}", params=params)
        if response.status_code in (404, 409):
            return []
        if response.status_code != 200:
            raise _unexpected(response)
        return response.json()["tree"]

    async def _blob_in_any_repository(self, session: _GitHubSession, content: bytes) -> str:
        try:
            return await self._blob(session, content)
        except _EmptyRepository:
            await self._bootstrap(session)
        try:
            return await self._blob(session, content)
        except _EmptyRepository:
            raise PublishError("GitHub did not accept the first file in the empty repository") from None

    @staticmethod
    async def _blob(session: _GitHubSession, content: bytes) -> str:
        response = await session.send(
            "POST",
            "/git/blobs",
            json={"content": base64.b64encode(content).decode("ascii"), "encoding": "base64"},
        )
        if response.status_code == 409:
            raise _EmptyRepository
        if response.status_code != 201:
            raise _unexpected(response)
        return response.json()["sha"]

    @staticmethod
    async def _bootstrap(session: _GitHubSession) -> None:
        marker = base64.b64encode(b"Published by What To Do\n").decode("ascii")
        await session.expect(
            "PUT",
            f"/contents/{MARKER}",
            200,
            201,
            json={"message": COMMIT_MESSAGE, "content": marker},
        )

    @staticmethod
    async def _move_branch(session: _GitHubSession, sha: str) -> None:
        response = await session.send("PATCH", f"/git/refs/heads/{BRANCH}", json={"sha": sha, "force": True})
        if response.status_code == 200:
            return
        if response.status_code != 422:
            raise _unexpected(response)
        await session.expect("POST", "/git/refs", 201, json={"ref": f"refs/heads/{BRANCH}", "sha": sha})

    @staticmethod
    def _site_url(repository: str, site: dict[str, Any]) -> str:
        url = site.get("html_url")
        if isinstance(url, str) and url:
            return url
        owner, name = repository.split("/")
        return f"https://{owner.lower()}.github.io/{name}/"
