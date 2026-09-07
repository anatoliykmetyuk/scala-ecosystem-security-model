"""Bounded-concurrency HTTP with immutable per-run, compressed evidence."""

from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import subprocess
import threading
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from .data import JSON, obj, rows, string

T = TypeVar("T")
U = TypeVar("U")


def parallel(fn: Callable[[T], U], items: Iterable[T], workers: int = 24) -> list[U]:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(fn, items))


def query(url: str, **params: object) -> str:
    parts = urlsplit(url)
    values = dict(parse_qsl(parts.query))
    values.update({k: str(v) for k, v in params.items()})
    return urlunsplit(parts._replace(query=urlencode(values)))


class Fetcher:
    def __init__(self, directory: Path, transport: httpx.BaseTransport | None = None) -> None:
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.client = httpx.Client(
            timeout=25,
            follow_redirects=True,
            transport=transport,
            headers={"User-Agent": "ScalaSecurityModel/0.2"},
        )
        token = (
            subprocess.run(["gh", "auth", "token"], capture_output=True, text=True).stdout.strip()
            if shutil.which("gh")
            else ""
        )
        self.github_token = token
        self.locks = [threading.Lock() for _ in range(256)]
        self.failures: list[tuple[str, str]] = []
        self.used: set[str] = set()

    def path(self, url: str) -> Path:
        return self.directory / (hashlib.sha256(url.encode()).hexdigest() + ".json.gz")

    def record(self, url: str) -> dict[str, JSON]:
        path = self.path(url)
        with self.locks[int(path.name[:4], 16) % len(self.locks)]:
            self.used.add(url)
            if path.exists():
                try:
                    with gzip.open(path, "rt") as f:
                        return obj(json.load(f))
                except (OSError, ValueError, EOFError):
                    path.rename(path.with_suffix(".corrupt"))
                    self.failures.append((url, "Corrupt cached response preserved and refetched"))
            result: dict[str, JSON] = {
                "url": url,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            }
            for attempt in range(3):
                try:
                    response = self.client.get(
                        url,
                        headers={"Authorization": "Bearer " + self.github_token}
                        if urlsplit(url).hostname == "api.github.com" and self.github_token
                        else {},
                    )
                    result.update(
                        status=response.status_code,
                        body=response.text,
                        link=response.headers.get("link", ""),
                    )
                    if response.status_code not in (429, 500, 502, 503, 504):
                        break
                    time.sleep(min(10, 2**attempt))
                except httpx.HTTPError as error:
                    result.update(status=0, body="", error=str(error))
            temporary = path.with_suffix(".tmp")
            with gzip.open(temporary, "wt") as f:
                json.dump(result, f, separators=(",", ":"))
            temporary.replace(path)
            return result

    def text(self, url: str) -> str:
        record = self.record(url)
        if record.get("status") != 200:
            self.failures.append((url, f"HTTP {record.get('status')}: {record.get('error', '')}"))
            return ""
        return string(record.get("body"))

    def json(self, url: str) -> JSON:
        text = self.text(url)
        if not text:
            return None
        try:
            return json.loads(text)
        except ValueError:
            self.failures.append((url, "Invalid JSON"))
            return None

    def pages(
        self, url: str, project: Callable[[dict[str, JSON]], dict[str, JSON]] | None = None
    ) -> list[dict[str, JSON]]:
        result: list[dict[str, JSON]] = []
        signatures: set[str] = set()
        page = 1
        while True:
            value = self.json(query(url, page=page, per_page=100))
            if not isinstance(value, list):
                if value is not None:
                    self.failures.append((url, "Expected a paginated array"))
                break
            batch = rows(value)
            if not batch:
                break
            signature = hashlib.sha256(json.dumps(batch, sort_keys=True).encode()).hexdigest()
            if signature in signatures:
                self.failures.append((url, "Repeated page; pagination incomplete"))
                break
            signatures.add(signature)
            result.extend(project(item) for item in batch) if project else result.extend(batch)
            # Do not infer completion from short pages: service limits can differ.
            page += 1
        return result
