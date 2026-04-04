#!/usr/bin/env python3
"""Validate frozen challenge suites: spec + markdown + hidden_tests layout.

Exit 0 only if every library challenge passes. Intended for CI and pre-release gates.

Checks:
  - CHALLENGE.md + challenge.spec.json present and mutually consistent (Pydantic + title/id)
  - hidden_tests/ directory exists with at least one test_*.py
  - hidden_tests Python files are syntactically valid (compile)
  - Judge criteria ids are the known dimensions; weights sum to ~1.0
  - Quality command names are unique
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from packages.shared.src.challenge_library import (  # noqa: E402
    iter_library_challenge_ids,
    load_validated_library_challenge,
)

# Challenges that must ship a golden workspace under challenges/fixtures/<id>/golden/
CHALLENGES_REQUIRING_GOLDEN_FIXTURE: frozenset[str] = frozenset({"url-shortener-saas"})


KNOWN_JUDGE_DIMENSIONS = frozenset(
    {
        "functionality",
        "code_quality",
        "test_coverage",
        "ux_design",
        "architecture",
        "innovation",
    }
)


def _repo_root(start: Path) -> Path:
    cur = start.resolve()
    for p in [cur, *cur.parents]:
        if (p / "pyproject.toml").is_file() and (p / "challenges" / "library").is_dir():
            return p
    return _REPO_ROOT


def _validate_hidden_tests(challenge_dir: Path) -> list[str]:
    errors: list[str] = []
    ht = challenge_dir / "hidden_tests"
    if not ht.is_dir():
        errors.append("missing hidden_tests/ directory")
        return errors
    tests = sorted(ht.glob("test_*.py"))
    if not tests:
        errors.append("hidden_tests/ has no test_*.py files")
    for pyf in sorted(ht.glob("*.py")):
        try:
            compile(pyf.read_text(encoding="utf-8"), str(pyf), "exec")
        except SyntaxError as e:
            errors.append(f"syntax error in {pyf.relative_to(challenge_dir)}: {e}")
    return errors


def _validate_judge_spec(spec: object, challenge_id: str) -> list[str]:
    errors: list[str] = []
    judge = getattr(spec, "judge", None)
    if judge is None:
        return ["missing judge block"]
    cids = [c.id for c in judge.criteria]
    unknown = set(cids) - KNOWN_JUDGE_DIMENSIONS
    if unknown:
        errors.append(
            f"judge.criteria ids not in known dimensions: {sorted(unknown)} "
            f"(allowed: {sorted(KNOWN_JUDGE_DIMENSIONS)})"
        )
    missing = KNOWN_JUDGE_DIMENSIONS - set(cids)
    if missing:
        errors.append(
            f"judge.criteria missing dimensions (judge service expects these): {sorted(missing)}"
        )
    total_w = sum(c.weight for c in judge.criteria)
    if abs(total_w - 1.0) > 0.02:
        errors.append(
            f"judge.criteria weights sum to {total_w:.4f}, expected ~1.0 for challenge {challenge_id}"
        )
    return errors


def _validate_quality(spec: object) -> list[str]:
    errors: list[str] = []
    names = [q.name for q in spec.quality.commands]
    if len(names) != len(set(names)):
        errors.append(f"duplicate quality.commands name: {names}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (default: discover from cwd)",
    )
    parser.add_argument(
        "--json-summary",
        action="store_true",
        help="Print one JSON object with per-challenge results to stdout",
    )
    args = parser.parse_args()
    root = args.repo_root or _repo_root(Path.cwd())

    ids = iter_library_challenge_ids(root)
    if not ids:
        print("No challenges under challenges/library/", file=sys.stderr)
        return 1

    summary: dict[str, dict[str, object]] = {}
    failed = 0
    for cid in ids:
        row: dict[str, object] = {"ok": True, "errors": []}
        errs: list[str] = []
        try:
            _md, spec = load_validated_library_challenge(root, cid)
        except Exception as e:
            errs.append(f"load_validated_library_challenge: {e}")
            row["ok"] = False
            row["errors"] = errs
            summary[cid] = row
            failed += 1
            continue

        ch_dir = root / "challenges" / "library" / cid
        errs.extend(_validate_hidden_tests(ch_dir))
        errs.extend(_validate_judge_spec(spec, cid))
        errs.extend(_validate_quality(spec))
        if cid in CHALLENGES_REQUIRING_GOLDEN_FIXTURE:
            gdir = root / "challenges" / "fixtures" / cid / "golden"
            if not (gdir / "main.py").is_file():
                errs.append(
                    f"missing golden reference (expected challenges/fixtures/{cid}/golden/main.py)"
                )

        if errs:
            row["ok"] = False
            row["errors"] = errs
            failed += 1
        summary[cid] = row

    if args.json_summary:
        print(json.dumps({"repo_root": str(root), "challenges": summary}, indent=2))

    for cid, row in summary.items():
        if not row["ok"]:
            print(f"[FAIL] {cid}", file=sys.stderr)
            for e in row["errors"]:
                print(f"  - {e}", file=sys.stderr)
        elif not args.json_summary:
            print(f"[OK]   {cid}")

    if failed:
        print(f"\n{failed}/{len(ids)} challenge(s) failed validation.", file=sys.stderr)
        return 1
    if not args.json_summary:
        print(f"All {len(ids)} challenge(s) passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
