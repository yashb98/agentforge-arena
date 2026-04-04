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
from pathlib import Path
from uuid import UUID

from packages.shared.src.events.bus import EventBus
from packages.shared.src.llm.task_timeout import LLMTaskKind
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

    # Model used for judging — Opus for highest accuracy
    JUDGE_MODEL = "claude-opus-4-6"

    def __init__(self, llm_client: object | None) -> None:
        self._llm = llm_client

    async def _call_llm(self, prompt: str, dimension: str) -> tuple[float, str]:
        """Make an LLM call and parse the JSON score response.

        Returns (score, details). Falls back to 50.0 on any failure.
        """
        if self._llm is None:
            return 50.0, f"LLM client not configured — {dimension} defaulted to 50"

        try:
            response = await self._llm.completion(  # type: ignore[union-attr]
                messages=[
                    {"role": "system", "content": "You are a fair, expert hackathon judge. Always respond with ONLY a JSON object."},
                    {"role": "user", "content": prompt},
                ],
                model=self.JUDGE_MODEL,
                temperature=0.0,
                max_tokens=1024,
                trace_name=f"judge.{dimension}",
                task_kind=LLMTaskKind.JUDGE_SCORING,
            )

            data = json.loads(response.content)
            score = float(data.get("score", 50.0))
            details = str(data.get("details", ""))
            return max(0.0, min(100.0, score)), details

        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("LLM judge parse error for %s: %s", dimension, exc)
            return 50.0, f"LLM response parse failed — {dimension} defaulted to 50"
        except Exception:
            logger.exception("LLM judge call failed for %s", dimension)
            return 50.0, f"LLM call failed — {dimension} defaulted to 50"

    def _read_workspace_files(self, workspace_path: str, globs: list[str], max_chars: int = 15000) -> str:
        """Read files matching globs from workspace, truncated to max_chars."""
        root = Path(workspace_path)
        parts: list[str] = []
        total = 0
        for pattern in globs:
            for filepath in sorted(root.glob(pattern)):
                if filepath.is_file():
                    try:
                        content = filepath.read_text(errors="replace")
                        header = f"\n--- {filepath.relative_to(root)} ---\n"
                        if total + len(header) + len(content) > max_chars:
                            remaining = max_chars - total - len(header)
                            if remaining > 200:
                                parts.append(header + content[:remaining] + "\n[truncated]")
                            break
                        parts.append(header + content)
                        total += len(header) + len(content)
                    except Exception:
                        continue
            if total >= max_chars:
                break
        return "".join(parts) or "(no files found)"

    async def judge_ux_design(self, workspace_path: str) -> JudgeScore:
        """Evaluate UX/design quality via LLM review of frontend code."""
        code = self._read_workspace_files(workspace_path, [
            "**/*.tsx", "**/*.jsx", "**/*.css", "**/*.html",
            "**/tailwind.config.*", "**/globals.css",
        ])
        prompt = f"""You are judging a hackathon project's UX/design quality.

Review the frontend code below and score 0-100.

Criteria:
- Clear user flow and navigation
- Loading states, error states, empty states
- Responsive design
- Visual hierarchy and consistent styling
- Accessibility considerations (aria labels, semantic HTML)

Frontend code:
{code}

Respond with ONLY a JSON object: {{"score": <0-100>, "details": "<2-3 sentence explanation>"}}"""

        score, details = await self._call_llm(prompt, "ux_design")
        return JudgeScore(
            dimension="ux_design",
            score=score,
            weight=SCORING_WEIGHTS["ux_design"],
            judge_type="llm",
            details=details,
        )

    async def judge_architecture(self, workspace_path: str) -> JudgeScore:
        """Evaluate architecture quality via LLM review."""
        code = self._read_workspace_files(workspace_path, [
            "ARCHITECTURE.md", "README.md",
            "**/__init__.py", "**/models.py", "**/routes.py", "**/main.py",
            "pyproject.toml", "package.json",
        ])
        prompt = f"""You are judging a hackathon project's architecture quality.

Review the architecture docs and code structure below. Score 0-100.

Criteria:
- Clear separation of concerns
- Appropriate design patterns for the problem
- Scalability considerations
- Error handling strategy
- API design quality (if applicable)

Project files:
{code}

Respond with ONLY a JSON object: {{"score": <0-100>, "details": "<2-3 sentence explanation>"}}"""

        score, details = await self._call_llm(prompt, "architecture")
        return JudgeScore(
            dimension="architecture",
            score=score,
            weight=SCORING_WEIGHTS["architecture"],
            judge_type="llm",
            details=details,
        )

    async def judge_innovation(self, workspace_path: str) -> JudgeScore:
        """Evaluate innovation and creative problem-solving."""
        code = self._read_workspace_files(workspace_path, [
            "README.md", "ARCHITECTURE.md",
            "**/*.py", "**/*.ts", "**/*.tsx",
        ])
        prompt = f"""You are judging a hackathon project's innovation and creativity.

Review the project below and score 0-100.

Criteria:
- Novel approach to the problem
- Creative use of technology
- Going beyond basic requirements
- Elegant solutions to complex problems
- Unique features or capabilities

Project files:
{code}

Respond with ONLY a JSON object: {{"score": <0-100>, "details": "<2-3 sentence explanation>"}}"""

        score, details = await self._call_llm(prompt, "innovation")
        return JudgeScore(
            dimension="innovation",
            score=score,
            weight=SCORING_WEIGHTS["innovation"],
            judge_type="llm",
            details=details,
        )


class JudgeService:
    """Orchestrates the full judging pipeline."""

    def __init__(
        self,
        event_bus: EventBus,
        sandbox_manager: object,
        llm_client: object | None = None,
    ) -> None:
        self._events = event_bus
        self._sandbox = sandbox_manager
        self._automated = AutomatedJudge()
        self._llm = LLMJudge(llm_client=llm_client)

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

        # Resolve hidden tests path from challenge library
        repo_root = Path(__file__).resolve().parents[4]
        hidden_tests_dir = repo_root / "challenges" / "library" / challenge_id / "hidden_tests"

        if hidden_tests_dir.is_dir():
            hidden_tests = str(hidden_tests_dir)
        else:
            logger.warning("Hidden tests not found for challenge %s, using team tests", challenge_id)
            hidden_tests = f"{workspace_a}/tests"

        # Load scoring config overrides if available
        scoring_config_file = repo_root / "challenges" / "library" / challenge_id / "scoring_config.json"
        if scoring_config_file.is_file():
            try:
                config_data = json.loads(scoring_config_file.read_text())
                weight_overrides = config_data.get("scoring_weights", {})
                if weight_overrides:
                    self._apply_scoring_overrides(weight_overrides)
            except (json.JSONDecodeError, OSError):
                logger.warning("Failed to load scoring config for %s", challenge_id)

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

    def _apply_scoring_overrides(self, overrides: dict[str, float]) -> None:
        """Temporarily apply per-challenge scoring weight overrides."""
        for dim, weight in overrides.items():
            if dim in SCORING_WEIGHTS:
                SCORING_WEIGHTS[dim] = weight
                logger.debug("Scoring override: %s = %.2f", dim, weight)

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
