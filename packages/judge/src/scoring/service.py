"""
AgentForge Arena — Judge Service

Multi-dimension judging pipeline combining automated tests, static analysis,
and LLM evaluation. Produces composite scores for tournament matches.

Scoring Dimensions:
  - Functionality (30%): pytest hidden test suite
  - Code Quality (20%): ruff + mypy + LLM architecture review
  - Test Coverage (15%): coverage.py line + branch
  - UX/Design (15%): LLM screenshot evaluation
  - Architecture (10%): LLM ARCHITECTURE.md + code structure review
  - Innovation (10%): LLM novel approaches evaluation
"""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

from packages.shared.src.events.bus import EventBus
from packages.shared.src.types.models import JudgeScore, MatchResult

logger = logging.getLogger(__name__)

# Scoring weights
SCORING_WEIGHTS: dict[str, float] = {
    "functionality": 0.30,
    "code_quality": 0.20,
    "test_coverage": 0.15,
    "ux_design": 0.15,
    "architecture": 0.10,
    "innovation": 0.10,
}


class AutomatedJudge:
    """Runs automated checks: tests, linting, coverage."""

    async def judge_functionality(self, workspace_path: str, hidden_tests_path: str) -> JudgeScore:
        """Run hidden test suite against team's code."""
        proc = await asyncio.create_subprocess_exec(
            "pytest", hidden_tests_path,
            "--tb=short", "-q", "--no-header",
            f"--rootdir={workspace_path}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workspace_path,
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode()

        # Parse pytest output for pass/fail counts
        passed = output.count(" passed")
        failed = output.count(" failed")
        total = passed + failed
        score = (passed / max(total, 1)) * 100

        return JudgeScore(
            dimension="functionality",
            score=score,
            weight=SCORING_WEIGHTS["functionality"],
            judge_type="automated",
            details=f"Tests: {passed}/{total} passed. {output[-200:]}",
        )

    async def judge_code_quality(self, workspace_path: str) -> JudgeScore:
        """Run ruff + mypy for code quality scoring."""
        # Ruff
        ruff_proc = await asyncio.create_subprocess_exec(
            "ruff", "check", workspace_path, "--output-format=json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        ruff_out, _ = await ruff_proc.communicate()

        try:
            ruff_issues = json.loads(ruff_out.decode())
            ruff_count = len(ruff_issues) if isinstance(ruff_issues, list) else 0
        except json.JSONDecodeError:
            ruff_count = 0

        # Mypy
        mypy_proc = await asyncio.create_subprocess_exec(
            "mypy", workspace_path, "--no-error-summary",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        mypy_out, _ = await mypy_proc.communicate()
        mypy_errors = mypy_out.decode().count("error:")

        # Score: start at 100, deduct per issue
        score = max(0.0, 100.0 - (ruff_count * 2.0) - (mypy_errors * 5.0))

        return JudgeScore(
            dimension="code_quality",
            score=score,
            weight=SCORING_WEIGHTS["code_quality"],
            judge_type="automated",
            details=f"Ruff issues: {ruff_count}, Mypy errors: {mypy_errors}",
        )

    async def judge_test_coverage(self, workspace_path: str) -> JudgeScore:
        """Measure test coverage."""
        proc = await asyncio.create_subprocess_exec(
            "pytest",
            f"--cov={workspace_path}/src",
            "--cov-branch",
            "--cov-report=json:/tmp/coverage.json",
            f"{workspace_path}/tests",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workspace_path,
        )
        await proc.communicate()

        try:
            with open("/tmp/coverage.json") as f:
                cov_data = json.load(f)
            score = cov_data.get("totals", {}).get("percent_covered", 0.0)
        except (FileNotFoundError, json.JSONDecodeError):
            score = 0.0

        return JudgeScore(
            dimension="test_coverage",
            score=min(score, 100.0),
            weight=SCORING_WEIGHTS["test_coverage"],
            judge_type="automated",
            details=f"Coverage: {score:.1f}%",
        )


class LLMJudge:
    """Uses Claude Opus 4.6 for subjective evaluation dimensions."""

    def __init__(self, llm_client: object) -> None:
        self._llm = llm_client

    async def judge_ux_design(self, workspace_path: str) -> JudgeScore:
        """Evaluate UX/design quality via LLM review."""
        # TODO: Take screenshots via headless browser, send to LLM
        # For now, review the frontend code structure
        prompt = f"""You are a senior UX reviewer judging a hackathon project.
Review the frontend code at {workspace_path} and score the UX quality 0-100.

Criteria:
- Is there a clear user flow?
- Are there loading states, error states, empty states?
- Is the design responsive?
- Is there visual hierarchy and consistent styling?
- Are there accessibility considerations?

Respond with ONLY a JSON object: {{"score": <0-100>, "details": "<explanation>"}}"""

        # TODO: Actually call LLM via LiteLLM
        return JudgeScore(
            dimension="ux_design",
            score=50.0,  # Placeholder
            weight=SCORING_WEIGHTS["ux_design"],
            judge_type="llm",
            details="LLM UX review pending implementation",
        )

    async def judge_architecture(self, workspace_path: str) -> JudgeScore:
        """Evaluate architecture quality via LLM review."""
        prompt = f"""You are a senior architect reviewing a hackathon project.
Review ARCHITECTURE.md and the code structure at {workspace_path}.

Criteria:
- Clear separation of concerns
- Appropriate design patterns
- Scalability considerations
- Error handling strategy
- API design quality

Score 0-100. Respond with ONLY JSON: {{"score": <0-100>, "details": "<explanation>"}}"""

        return JudgeScore(
            dimension="architecture",
            score=50.0,  # Placeholder
            weight=SCORING_WEIGHTS["architecture"],
            judge_type="llm",
            details="LLM architecture review pending implementation",
        )

    async def judge_innovation(self, workspace_path: str) -> JudgeScore:
        """Evaluate innovation and creative problem-solving."""
        return JudgeScore(
            dimension="innovation",
            score=50.0,  # Placeholder
            weight=SCORING_WEIGHTS["innovation"],
            judge_type="llm",
            details="LLM innovation review pending implementation",
        )


class JudgeService:
    """Orchestrates the full judging pipeline."""

    def __init__(self, event_bus: EventBus, sandbox_manager: object) -> None:
        self._events = event_bus
        self._sandbox = sandbox_manager
        self._automated = AutomatedJudge()
        self._llm = LLMJudge(llm_client=None)  # TODO: Inject LiteLLM client

    async def judge_tournament(
        self,
        tournament_id: UUID,
        team_ids: list[UUID],
        challenge_id: str,
    ) -> list[MatchResult]:
        """Run the full judging pipeline for all matches in a tournament."""
        results: list[MatchResult] = []

        # For a duel: one match between team_ids[0] and team_ids[1]
        # For larger tournaments: generate matchups based on bracket
        matchups = self._generate_matchups(team_ids)

        for team_a_id, team_b_id in matchups:
            result = await self._judge_match(tournament_id, team_a_id, team_b_id, challenge_id)
            results.append(result)

            await self._events.publish(
                "tournament.match.judged",
                source="judge.service",
                tournament_id=tournament_id,
                payload={
                    "team_a_id": str(team_a_id),
                    "team_b_id": str(team_b_id),
                    "team_a_total": result.team_a_total,
                    "team_b_total": result.team_b_total,
                    "winner": str(result.winner_team_id) if result.winner_team_id else "draw",
                },
            )

        return results

    async def _judge_match(
        self,
        tournament_id: UUID,
        team_a_id: UUID,
        team_b_id: UUID,
        challenge_id: str,
    ) -> MatchResult:
        """Judge a single match between two teams."""
        from packages.shared.src.config import get_settings
        settings = get_settings()

        workspace_a = f"{settings.sandbox.workspace_base}/team-{team_a_id}/project"
        workspace_b = f"{settings.sandbox.workspace_base}/team-{team_b_id}/project"
        hidden_tests = f"challenges/library/{challenge_id}/hidden_tests"

        # Run all judges in parallel for both teams
        team_a_scores, team_b_scores = await asyncio.gather(
            self._score_team(workspace_a, hidden_tests),
            self._score_team(workspace_b, hidden_tests),
        )

        # Calculate totals
        total_a = sum(s.score * s.weight for s in team_a_scores)
        total_b = sum(s.score * s.weight for s in team_b_scores)

        # Determine winner
        winner = None
        is_draw = False
        if abs(total_a - total_b) < 1.0:  # Within 1 point = draw
            is_draw = True
        elif total_a > total_b:
            winner = team_a_id
        else:
            winner = team_b_id

        return MatchResult(
            tournament_id=tournament_id,
            round_number=1,
            team_a_id=team_a_id,
            team_b_id=team_b_id,
            team_a_scores=team_a_scores,
            team_b_scores=team_b_scores,
            team_a_total=total_a,
            team_b_total=total_b,
            winner_team_id=winner,
            is_draw=is_draw,
        )

    async def _score_team(self, workspace_path: str, hidden_tests_path: str) -> list[JudgeScore]:
        """Run all scoring dimensions for a single team."""
        automated_scores = await asyncio.gather(
            self._automated.judge_functionality(workspace_path, hidden_tests_path),
            self._automated.judge_code_quality(workspace_path),
            self._automated.judge_test_coverage(workspace_path),
        )

        llm_scores = await asyncio.gather(
            self._llm.judge_ux_design(workspace_path),
            self._llm.judge_architecture(workspace_path),
            self._llm.judge_innovation(workspace_path),
        )

        return list(automated_scores) + list(llm_scores)

    def _generate_matchups(self, team_ids: list[UUID]) -> list[tuple[UUID, UUID]]:
        """Generate match pairings from team list."""
        if len(team_ids) == 2:
            return [(team_ids[0], team_ids[1])]

        # Round-robin for larger tournaments
        matchups = []
        for i in range(len(team_ids)):
            for j in range(i + 1, len(team_ids)):
                matchups.append((team_ids[i], team_ids[j]))
        return matchups
