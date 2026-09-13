"""Shared test fixtures. A ``FakeOpener`` stands in for ``urllib``'s opener so
the client can be exercised end-to-end with zero network and zero waiting."""

from __future__ import annotations

import io
import json
import os
import urllib.error
from email.message import Message

import pytest

from rd_cli import config


class FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(code: int, payload: dict | None = None, headers: dict | None = None):
    body = json.dumps(payload).encode() if payload is not None else b""
    hdrs = Message()
    for key, value in (headers or {}).items():
        hdrs[key] = value
    return urllib.error.HTTPError(
        "https://api.raindrop.io/rest/v1/x",
        code,
        "error",
        hdrs,
        io.BytesIO(body),
    )


class FakeOpener:
    """Records requests and returns queued responses in order.

    Queue entries are either dicts (JSON-encoded into a 200 body) or exceptions
    (raised to simulate transport / HTTP errors).
    """

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, req, timeout=None):
        self.requests.append(req)
        if not self.responses:
            raise AssertionError("FakeOpener ran out of queued responses")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeResponse(json.dumps(item).encode())

    @property
    def last(self):
        return self.requests[-1]


@pytest.fixture(autouse=True)
def _isolate_token_state(monkeypatch):
    """Fresh token-resolution state per test.

    ``load_env_files`` injects into ``os.environ`` directly, which
    ``monkeypatch`` cannot see or undo, and the injected-keys registry is
    module state. Without this fixture one test's ``.env`` could leak its
    injections (or a developer's real ``~/.config/rd-cli`` fallback) into the
    next test.
    """
    token_vars = (*config.ENV_VARS, *config.PINBOARD_ENV_VARS)
    before = {var: os.environ.get(var) for var in token_vars}
    monkeypatch.setattr(config, "_injected", {})
    yield
    for var in token_vars:
        if os.environ.get(var) != before[var]:
            if before[var] is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = before[var]


@pytest.fixture
def opener_factory():
    return FakeOpener


@pytest.fixture
def no_sleep():
    calls = []
    return calls.append, calls
