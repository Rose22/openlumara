# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
"""
core/api.py - error objects and error/retry classification (pure parts).

intent: API errors are RETURNED as APIError objects (never raised at callers),
messages must be actionable for end users, and the retry loop must only
re-attempt transient failures - SSL problems and auth errors never.
"""

import asyncio

import aiohttp
import pytest

import core


@pytest.fixture
def client():
    # APIClient.__new__ without __init__: these tests only touch pure
    # classification methods, no network/session state is needed.
    return core.api.APIClient.__new__(core.api.APIClient)


# ---- APIError / APIHTTPError --------------------------------------------------

def test_apierror_str_variants(monkeypatch):
    monkeypatch.setattr(core, "debug", False)

    assert str(core.api.APIError("plain message")) == "plain message"
    assert str(core.api.APIError(None, ValueError("cause"))) == "cause"
    assert str(core.api.APIError("context", ValueError("cause"))) == "context: cause"
    assert str(core.api.APIError()) == ""


def test_apihttp_error_carries_status_and_truncated_body():
    err = core.api.APIHTTPError(404, "no such model")
    assert err.status == 404
    assert err.body == "no such model"
    assert str(err) == "HTTP 404: no such model"

    long_err = core.api.APIHTTPError(500, "x" * 2000)
    assert len(str(long_err)) < 600  # body truncated to 500 chars


# ---- _error_for_status ---------------------------------------------------------

def test_error_for_status_bad_request(client):
    assert client._error_for_status(400, "something odd").message == "Bad request"


def test_error_for_status_bad_request_model_missing(client):
    # intent: a 400 that mentions a missing model is the classic "wrong model
    # name" mistake and must tell the user that, not just "bad request"
    e = client._error_for_status(400, "The model `llama-3` was not found")
    assert "does not exist" in e.message
    e = client._error_for_status(400, "model missing from router")
    assert "does not exist" in e.message


def test_error_for_status_auth(client):
    for status in (401, 403):
        e = client._error_for_status(status, "")
        assert "Authentication failed" in e.message


def test_error_for_status_not_found_is_model_message(client):
    assert "does not exist" in client._error_for_status(404, "").message


def test_error_for_status_rate_limit(client):
    assert client._error_for_status(429, "").message == "Rate limit exceeded"


def test_error_for_status_falls_through_to_generic(client):
    assert client._error_for_status(503, "down").message == "API Status Error"


def test_error_for_status_keeps_underlying_http_error(client):
    e = client._error_for_status(500, "boom")
    assert isinstance(e.exc, core.api.APIHTTPError)
    assert e.exc.status == 500


# ---- _is_retryable_error ---------------------------------------------------------

def test_retryable_http_statuses(client):
    for status in core.api.APIClient.RETRYABLE_STATUS_CODES:
        assert client._is_retryable_error(core.api.APIHTTPError(status)) is True
    assert client._is_retryable_error(core.api.APIHTTPError(401)) is False


def test_retryable_connection_errors_and_timeouts(client):
    assert client._is_retryable_error(aiohttp.ClientConnectionError()) is True
    assert client._is_retryable_error(asyncio.TimeoutError()) is True


def test_ssl_errors_are_never_retried(client):
    # aiohttp 3.14 constructs these from a real OSError
    err = aiohttp.ClientSSLError(None, OSError(22, "certificate verify failed"))
    assert client._is_retryable_error(err) is False


def test_unknown_exceptions_are_not_retried(client):
    assert client._is_retryable_error(RuntimeError("?")) is False
