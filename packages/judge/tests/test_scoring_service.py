"""Unit tests for judge scoring (subprocess and LLM mocked)."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, mock_open, patch
from uuid import uuid4

import pytest

from packages.judge.src.scoring.service import (
    SCORING_WEIGHTS,
    AutomatedJudge,
    JudgeService,
    LLMJudge,
)
from packages.shared.src.types.models import JudgeScore, MatchResult


def _fake_proc(stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0) -> AsyncMock:
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.returncode = returncode
    return proc


@pytest.mark.asyncio
async def test_automated_judge_functionality_parses_pytest_output() -> None:
    judge = AutomatedJudge()
    # Implementation counts substrings " passed" / " failed" (one per summary token).
    stdout = b" passed\n passed\n failed\n"
    proc = _fake_proc(stdout=stdout)
    with patch(
        "packages.judge.src.scoring.service.asyncio.create_subprocess_exec",
        AsyncMock(return_value=proc),
    ):
        score = await judge.judge_functionality("/w", "/hidden")
    assert score.dimension == "functionality"
    assert score.score == pytest.approx(2 / 3 * 100)


@pytest.mark.asyncio
async def test_automated_judge_code_quality_json_decode_fallback() -> None:
    judge = AutomatedJudge()
    ruff_p = _fake_proc(stdout=b"not-json", returncode=0)
    mypy_p = _fake_proc(stdout=b"", returncode=0)
    with patch(
        "packages.judge.src.scoring.service.asyncio.create_subprocess_exec",
        AsyncMock(side_effect=[ruff_p, mypy_p]),
    ):
        score = await judge.judge_code_quality("/w")
    assert score.dimension == "code_quality"
    assert score.score == 100.0


@pytest.mark.asyncio
async def test_automated_judge_test_coverage_reads_json(tmp_path: Path) -> None:
    judge = AutomatedJudge()
    cov = {"totals": {"percent_covered": 82.5}}
    pytest_proc = _fake_proc()
    with patch(
        "packages.judge.src.scoring.service.asyncio.create_subprocess_exec",
        AsyncMock(return_value=pytest_proc),
    ), patch(
        "packages.judge.src.scoring.service.open",
        mock_open(read_data=json.dumps(cov)),
    ):
        score = await judge.judge_test_coverage("/w")
    assert score.score == 82.5


@pytest.mark.asyncio
async def test_llm_judge_no_client_defaults() -> None:
    j = LLMJudge(None)
    score, details = await j._call_llm("x", "ux_design")
    assert score == 50.0
    assert "not configured" in details


@pytest.mark.asyncio
async def test_llm_judge_parses_json_response() -> None:
    llm = AsyncMock()
    resp = MagicMock()
    resp.content = json.dumps({"score": 77.0, "details": "ok"})
    llm.completion = AsyncMock(return_value=resp)
    j = LLMJudge(llm)
    score, details = await j._call_llm("prompt", "architecture")
    assert score == 77.0
    assert details == "ok"


@pytest.mark.asyncio
async def test_llm_judge_invalid_json_falls_back() -> None:
    llm = AsyncMock()
    resp = MagicMock()
    resp.content = "not json"
    llm.completion = AsyncMock(return_value=resp)
    j = LLMJudge(llm)
    score, _details = await j._call_llm("p", "innovation")
    assert score == 50.0


def test_read_workspace_files_truncates(tmp_path: Path) -> None:
    j = LLMJudge(None)
    (tmp_path / "a.txt").write_text("x" * 5000)
    text = j._read_workspace_files(str(tmp_path), ["*.txt"], max_chars=100)
    assert "[truncated]" in text or len(text) <= 200


@pytest.mark.asyncio
async def test_llm_dimension_methods_call_llm(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Hi")
    j = LLMJudge(None)
    s = await j.judge_ux_design(str(tmp_path))
    assert s.dimension == "ux_design"
    assert s.score == 50.0


@contextmanager
def _restore_scoring_weights() -> object:
    snapshot = dict(SCORING_WEIGHTS)
    try:
        yield
    finally:
        SCORING_WEIGHTS.clear()
        SCORING_WEIGHTS.update(snapshot)


def test_apply_scoring_overrides_mutates_known_keys() -> None:
    with _restore_scoring_weights():
        svc = JudgeService(event_bus=MagicMock(), sandbox_manager=MagicMock())
        svc._apply_scoring_overrides({"functionality": 0.99, "unknown": 1.0})
        assert SCORING_WEIGHTS["functionality"] == 0.99


def test_generate_matchups_duel_and_round_robin() -> None:
    svc = JudgeService(event_bus=MagicMock(), sandbox_manager=MagicMock())
    a, b, c = uuid4(), uuid4(), uuid4()
    assert svc._generate_matchups([a, b]) == [(a, b)]
    pairs = svc._generate_matchups([a, b, c])
    assert len(pairs) == 3


@pytest.mark.asyncio
async def test_judge_tournament_publishes_per_match() -> None:
    bus = AsyncMock()
    bus.publish = AsyncMock(return_value="1-0")
    svc = JudgeService(event_bus=bus, sandbox_manager=MagicMock())
    ta, tb = uuid4(), uuid4()
    mr = MatchResult(
        tournament_id=uuid4(),
        round_number=1,
        team_a_id=ta,
        team_b_id=tb,
        team_a_scores=[],
        team_b_scores=[],
        team_a_total=10.0,
        team_b_total=5.0,
        winner_team_id=ta,
    )
    with patch.object(svc, "_judge_match", new_callable=AsyncMock, return_value=mr):
        out = await svc.judge_tournament(mr.tournament_id, [ta, tb], "url-shortener-saas")
    assert len(out) == 1
    bus.publish.assert_awaited()


@pytest.mark.asyncio
async def test_judge_match_winner_and_draw(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_settings = MagicMock(sandbox=MagicMock(workspace_base="/tmp/arena-judge-test"))
    monkeypatch.setattr(
        "packages.shared.src.config.get_settings",
        lambda: fake_settings,
    )

    ta, tb = uuid4(), uuid4()
    tid = uuid4()

    async def score_team_win(ws: str, _ht: str) -> list[JudgeScore]:
        val = 90.0 if str(ta) in ws else 10.0
        return [
            JudgeScore(
                dimension="functionality",
                score=val,
                weight=SCORING_WEIGHTS["functionality"],
                judge_type="auto",
            ),
        ]

    svc = JudgeService(event_bus=MagicMock(), sandbox_manager=MagicMock())
    with patch.object(svc, "_score_team", new=score_team_win):
        r_win = await svc._judge_match(tid, ta, tb, "url-shortener-saas")
    assert r_win.winner_team_id == ta

    async def score_team_tie(_ws: str, _ht: str) -> list[JudgeScore]:
        return [
            JudgeScore(
                dimension="functionality",
                score=50.0,
                weight=SCORING_WEIGHTS["functionality"],
                judge_type="auto",
            ),
        ]

    svc2 = JudgeService(event_bus=MagicMock(), sandbox_manager=MagicMock())
    with patch.object(svc2, "_score_team", new=score_team_tie):
        r_draw = await svc2._judge_match(tid, ta, tb, "url-shortener-saas")
    assert r_draw.is_draw is True
