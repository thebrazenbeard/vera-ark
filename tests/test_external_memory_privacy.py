"""No local private-memory egress without explicit, purpose-bound CLI consent."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from types import SimpleNamespace
from unittest.mock import patch
import urllib.error
import urllib.request

import pytest

from vera_ark.cli import _run_runtime, build_parser
from vera_ark.planner import OpenAIVisionPlanner, PlannerUnavailable, make_planner


PRIVATE_SYNTHETIC = "PRIVATE_CONTEXT_SENTINEL_XYZ"


def _offline_captured_request(planner: OpenAIVisionPlanner) -> dict:
    requests = []

    def intercept(request, timeout):
        requests.append(request)
        raise urllib.error.URLError("offline test blocks all real network requests")

    with patch("vera_ark.planner._require_openai_spend_authority"):
        with patch("vera_ark.planner.urllib.request.build_opener") as build:
            build.return_value.open.side_effect = intercept
            with pytest.raises(PlannerUnavailable):
                planner.plan(
                    perception=None,
                    frame=SimpleNamespace(png_bytes=b""),
                    memory_context=[PRIVATE_SYNTHETIC],
                )
    assert len(requests) == 1
    assert requests[0].full_url == "https://api.openai.com/v1/responses"
    assert build.call_args.args[0].__class__.__name__ == "_DenyAuthenticatedRedirects"
    return json.loads(requests[0].data)


def test_default_external_planner_never_serializes_local_private_memory():
    body = _offline_captured_request(
        OpenAIVisionPlanner(api_key="SYNTHETIC_TEST_KEY")
    )
    assert PRIVATE_SYNTHETIC not in json.dumps(body)
    assert "local context withheld" in body["input"][0]["content"][0]["text"]


def test_explicit_opt_in_serializes_only_synthetic_memory_context():
    body = _offline_captured_request(
        OpenAIVisionPlanner(api_key="SYNTHETIC_TEST_KEY", allow_external_memory=True)
    )
    assert PRIVATE_SYNTHETIC in body["input"][0]["content"][0]["text"]


@pytest.mark.parametrize("bad_consent", ["true", 1, None])
def test_nonboolean_library_consent_is_rejected(bad_consent):
    with pytest.raises(ValueError):
        OpenAIVisionPlanner(api_key="SYNTHETIC_TEST_KEY", allow_external_memory=bad_consent)


def test_cli_requires_explicit_three_part_egress_binding(tmp_path):
    parser = build_parser()
    args = parser.parse_args([
        "demo", "--planner", "openai", "--memory-file", "private.jsonl",
        "--allow-memory-to-openai"
    ])
    assert args.allow_memory_to_openai is True
    for planner, memory in (("heuristic", tmp_path / "private.jsonl"), ("openai", None)):
        with pytest.raises(ValueError):
            _run_runtime(
                capture=object(),
                planner_name=planner,
                monitor=0,
                steps=1,
                interval=0,
                log_dir=tmp_path / "uncreated_logs",
                stop_file=tmp_path / "STOP",
                memory_file=memory,
                allow_memory_to_openai=True,
            )
    assert not (tmp_path / "uncreated_logs").exists()


def test_local_fallback_remains_available_without_memory_egress_consent():
    planner = make_planner("heuristic")
    assert planner.name == "heuristic-v1"
    with pytest.raises(ValueError):
        make_planner("heuristic", allow_external_memory=True)


def test_invalid_consent_type_rejected_before_creating_local_ledgers(tmp_path):
    ledgers = tmp_path / "no_side_effects"
    with pytest.raises(ValueError, match="explicit boolean"):
        _run_runtime(
            capture=object(), planner_name="openai", monitor=0,
            steps=1, interval=0, log_dir=ledgers,
            stop_file=tmp_path / "STOP", memory_file=tmp_path / "memory.jsonl",
            allow_memory_to_openai="true",
        )
    assert not ledgers.exists()


def test_openai_is_default_denied_under_zero_budget_even_with_key_and_memory_opt_in():
    with patch("vera_ark.planner.urllib.request.build_opener") as no_network:
        with pytest.raises(PlannerUnavailable, match=r"\$0 budget"):
            OpenAIVisionPlanner(
                api_key="SYNTHETIC_TEST_KEY", allow_external_memory=True
            ).plan(
                perception=None,
                frame=SimpleNamespace(png_bytes=b"synthetic"),
                memory_context=[PRIVATE_SYNTHETIC],
            )
        no_network.assert_not_called()


@pytest.mark.parametrize("redirect_code", [301, 302, 303, 307, 308])
def test_authenticated_planner_post_never_follows_redirect_to_foreign_origin(redirect_code):
    """Two loopback servers, synthetic token, actual planner request transport."""
    foreign_requests = []
    origin_requests = []

    class ForeignSink(BaseHTTPRequestHandler):
        def do_GET(self):
            foreign_requests.append(("GET", self.headers.get("Authorization")))
            self.send_response(200)
            self.end_headers()

        def do_POST(self):
            foreign_requests.append(("POST", self.headers.get("Authorization")))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    sink = ThreadingHTTPServer(("127.0.0.1", 0), ForeignSink)
    sink_thread = threading.Thread(target=sink.serve_forever, daemon=True)
    sink_thread.start()
    target = f"http://127.0.0.1:{sink.server_port}/foreign"

    class RedirectOrigin(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            origin_requests.append(self.headers.get("Authorization"))
            self.send_response(redirect_code)
            self.send_header("Location", target)
            self.end_headers()

        def log_message(self, *args):
            pass

    origin = ThreadingHTTPServer(("127.0.0.1", 0), RedirectOrigin)
    origin_thread = threading.Thread(target=origin.serve_forever, daemon=True)
    origin_thread.start()
    local_origin = f"http://127.0.0.1:{origin.server_port}/synthetic-provider"
    original_build_opener = urllib.request.build_opener

    def local_redirect_test_opener(*handlers):
        real_opener = original_build_opener(*handlers)

        class RerouteOnlyTheInitialRequest:
            def open(self, request, timeout):
                assert request.full_url == "https://api.openai.com/v1/responses"
                rerouted = urllib.request.Request(
                    local_origin,
                    data=request.data,
                    headers=dict(request.header_items()),
                    method=request.get_method(),
                )
                # A real redirect from origin is then handled exclusively by
                # the planner's own opener, with no further interception.
                return real_opener.open(rerouted, timeout=timeout)

        return RerouteOnlyTheInitialRequest()

    try:
        with patch("vera_ark.planner._require_openai_spend_authority"):
            with patch("vera_ark.planner.urllib.request.build_opener", side_effect=local_redirect_test_opener):
                with pytest.raises(PlannerUnavailable):
                    OpenAIVisionPlanner(api_key="SYNTHETIC_TEST_KEY").plan(
                        perception=None, frame=SimpleNamespace(png_bytes=b"")
                    )
        assert origin_requests == ["Bearer SYNTHETIC_TEST_KEY"]
        assert foreign_requests == []
    finally:
        origin.shutdown()
        origin.server_close()
        origin_thread.join(timeout=3)
        sink.shutdown()
        sink.server_close()
        sink_thread.join(timeout=3)


def test_oversized_provider_response_fails_closed_without_parsing():
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def geturl(self):
            return "https://api.openai.com/v1/responses"

        def read(self, count):
            assert count == 2_000_001
            return b"X" * count

    with patch("vera_ark.planner._require_openai_spend_authority"):
        with patch("vera_ark.planner.urllib.request.build_opener") as build:
            build.return_value.open.return_value = FakeResponse()
            with pytest.raises(PlannerUnavailable, match="size limit"):
                OpenAIVisionPlanner(api_key="SYNTHETIC_TEST_KEY").plan(
                    perception=None, frame=SimpleNamespace(png_bytes=b"")
                )
