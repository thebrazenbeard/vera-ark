from __future__ import annotations

from email.message import Message
import json
import urllib.error
import urllib.request

import pytest

from vera_ark.storage import SupabaseEventAdapter
from vera_ark import cli


URL = "https://example.supabase.co"
KEY = "synthetic-nonsecret-test-key"
EVENT = {"schema_version": "VERA_ARK_OPERATIONAL_EVENT_V1", "event_id": "offline"}


@pytest.mark.parametrize(
    "url",
    [
        "http://example.supabase.co",
        "https://user:pass@example.supabase.co",
        "https://example.supabase.co?redirect=https://elsewhere.test",
        "https://example.supabase.co/#fragment",
        "file:///tmp/supabase",
        "https://",
        "https://example.supabase.co\n",
    ],
)
def test_invalid_mirror_sink_urls_fail_closed(url: str) -> None:
    with pytest.raises(ValueError):
        SupabaseEventAdapter(url, KEY)


@pytest.mark.parametrize("table", ["events?apikey=leak", "events/other", "", "a b"])
def test_invalid_table_name_fails_closed(table: str) -> None:
    with pytest.raises(ValueError):
        SupabaseEventAdapter(URL, KEY, table=table)


@pytest.mark.parametrize("key", ["key\r\nHost: bad", "synthetic-☃", "key with spaces", ""])
def test_non_header_safe_mirror_key_is_rejected(key: str) -> None:
    with pytest.raises(ValueError):
        SupabaseEventAdapter(URL, key)


def test_visible_ascii_mirror_key_is_accepted_but_not_qualified() -> None:
    adapter = SupabaseEventAdapter(URL, "sb_publishable_synthetic-123._=")
    assert adapter.sink_qualified is False


def test_mirror_does_not_call_provider_without_positive_sink_qualification(monkeypatch) -> None:
    def no_network(*_args, **_kwargs):
        raise AssertionError("An unqualified sink must never be contacted")

    monkeypatch.setattr(urllib.request, "build_opener", no_network)
    adapter = SupabaseEventAdapter(URL, KEY)
    assert adapter.emit(EVENT) is False


def test_invalid_environment_mirror_config_does_not_break_local_runtime(monkeypatch) -> None:
    monkeypatch.setenv("VERA_ARK_SUPABASE_URL", "http://untrusted.example")
    monkeypatch.setenv("VERA_ARK_SUPABASE_ANON_KEY", KEY)
    monkeypatch.setenv("VERA_ARK_SUPABASE_PROJECT_REF", "example")
    assert SupabaseEventAdapter.from_environment() is None


def test_generic_shared_supabase_environment_cannot_bind_ark(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", URL)
    monkeypatch.setenv("SUPABASE_ANON_KEY", KEY)
    assert SupabaseEventAdapter.from_environment() is None


@pytest.mark.parametrize(
    "url,ref,available",
    [
        (URL, "example", True),
        (URL + "/", "example", True),
        (URL, "anotherproject", False),
        ("http://example.supabase.co", "example", False),
        ("https://user:pass@example.supabase.co", "example", False),
        (URL, "EXAMPLE", False),
    ],
)
def test_environment_endpoint_must_match_pinned_ark_project(monkeypatch, url, ref, available) -> None:
    monkeypatch.setenv("VERA_ARK_SUPABASE_URL", url)
    monkeypatch.setenv("VERA_ARK_SUPABASE_ANON_KEY", KEY)
    monkeypatch.setenv("VERA_ARK_SUPABASE_PROJECT_REF", ref)
    adapter = SupabaseEventAdapter.from_environment()
    assert (adapter is not None) is available
    if adapter is not None:
        assert adapter.sink_qualified is False


def test_qualified_mirror_rejects_redirects_even_to_same_origin(monkeypatch) -> None:
    original_build = urllib.request.build_opener
    observed = []

    def inspect_handlers(*handlers):
        redirect = next(h for h in handlers if isinstance(h, urllib.request.HTTPRedirectHandler))
        req = urllib.request.Request(
            f"{URL}/rest/v1/vera_ark_operational_events",
            data=b"{}",
            headers={"apikey": KEY, "Authorization": f"Bearer {KEY}"},
            method="POST",
        )
        assert redirect.redirect_request(req, None, 302, "Found", {}, URL + "/elsewhere") is None
        assert redirect.redirect_request(req, None, 307, "Redirect", {}, "https://attacker.test") is None
        observed.append(True)
        return original_build(*handlers)

    monkeypatch.setattr(urllib.request, "build_opener", inspect_handlers)
    # Exercise the handler configuration without touching an actual network.
    class NoCall:
        def open(self, _req, timeout):
            del timeout
            raise urllib.error.URLError("synthetic offline rejection")

    def no_provider_call(*handlers):
        inspect_handlers(*handlers)
        return NoCall()

    monkeypatch.setattr(urllib.request, "build_opener", no_provider_call)
    assert SupabaseEventAdapter(URL, KEY, sink_qualified=True).emit(EVENT) is False
    assert observed == [True]


@pytest.mark.parametrize(
    "status,body,accepted",
    [(201, b"", True), (204, b"", True), (200, b"", True), (202, b"", False), (201, b"unexpected", False)],
)
def test_qualified_mirror_bounded_http_ack_not_delivery_proof(monkeypatch, status, body, accepted) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def __init__(self):
            self.status = status

        def read(self, limit):
            assert limit == 1
            return body[:limit]

    class FakeOpener:
        def open(self, request, *, timeout):
            assert timeout == 5.0
            assert request.full_url == URL + "/rest/v1/vera_ark_operational_events"
            assert request.get_method() == "POST"
            return Response()

    monkeypatch.setattr(urllib.request, "build_opener", lambda *_handlers: FakeOpener())
    assert SupabaseEventAdapter(URL, KEY, sink_qualified=True).emit(EVENT) is accepted


def test_denied_rls_sink_never_claims_acceptance(monkeypatch) -> None:
    class DenyOpener:
        def open(self, request, *, timeout):
            del timeout
            raise urllib.error.HTTPError(request.full_url, 403, "RLS denied", Message(), None)

    monkeypatch.setattr(urllib.request, "build_opener", lambda *_handlers: DenyOpener())
    assert SupabaseEventAdapter(URL, KEY, sink_qualified=True).emit(EVENT) is False


def test_doctor_distinguishes_configured_credentials_from_sink_qualification(monkeypatch, capsys) -> None:
    monkeypatch.setenv("VERA_ARK_SUPABASE_URL", URL)
    monkeypatch.setenv("VERA_ARK_SUPABASE_ANON_KEY", KEY)
    monkeypatch.setenv("VERA_ARK_SUPABASE_PROJECT_REF", "example")
    assert cli.main(["doctor"]) == 0
    doctor = json.loads(capsys.readouterr().out)
    assert doctor["supabase_adapter_configured"] is True
    assert doctor["supabase_adapter_qualified"] is False
