"""No local private-memory egress without explicit, purpose-bound CLI consent."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import urllib.error

import pytest

from vera_ark.cli import _run_runtime, build_parser
from vera_ark.planner import OpenAIVisionPlanner, PlannerUnavailable, make_planner


PRIVATE_SYNTHETIC = "PRIVATE_CONTEXT_SENTINEL_XYZ"


def _offline_captured_request(planner: OpenAIVisionPlanner) -> dict:
    requests = []

    def intercept(request, timeout):
        requests.append(request)
        raise urllib.error.URLError("offline test blocks all real network requests")

    with patch("vera_ark.planner.urllib.request.urlopen", side_effect=intercept):
        with pytest.raises(PlannerUnavailable):
            planner.plan(
                perception=None,
                frame=SimpleNamespace(png_bytes=b""),
                memory_context=[PRIVATE_SYNTHETIC],
            )
    assert len(requests) == 1
    assert requests[0].full_url == "https://api.openai.com/v1/responses"
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
