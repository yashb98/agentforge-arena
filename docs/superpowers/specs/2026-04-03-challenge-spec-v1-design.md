# Challenge spec v1 — design

**Status:** Draft → implementation-ready  
**Date:** 2026-04-03  
**Scope:** Item **C** in roadmap order **C → A → F → B → E → D**  
**Consumers:** Orchestrator, judge, builder agents (all read the same validated contract)

## 1. Problem

The platform today mixes a flat `Challenge` Pydantic model, database JSONB fields, and a **tolerant** `CHALLENGE.md` parser. That is insufficient for large builds: phases, rubrics, acceptance checks, and agent constraints need a **single strict source of truth** that every subsystem agrees on.

## 2. Approaches considered

| Approach | Idea | Pros | Cons |
|----------|------|------|------|
| **A. Flat v2 model** | Extend `Challenge` with many new fields | Simple mentally | Becomes unmergeable; unclear ownership per consumer |
| **B. Consumer-namespaced document** | One JSON root; sections: `orchestration`, `judge`, `agents`, `quality`, … | Clear boundaries; teams can own a section; extensible | Slightly more nesting; docs must explain each block |
| **C. Split files** | `judge.json`, `agents.json`, … per challenge | Maximum isolation | Many files; cross-reference errors; worse PR ergonomics |

**Decision:** **B — single `challenge.spec.json`** with **namespaced top-level keys** and **Pydantic v2** models in `packages/shared` (extra fields forbidden in v1).

## 3. File layout (canonical authoring)

```
challenges/library/<challenge_id>/
  CHALLENGE.md          # Human narrative (brief, context); not a schema substitute
  challenge.spec.json   # Machine-readable canonical spec (validated)
```

- **Folder name** MUST equal `challenge_id` (URL-safe slug, match existing convention).
- **Sync rule (CI):** `challenge_id` and `title` in the spec MUST match folder name and the first `#` title in `CHALLENGE.md` (after optional `Challenge:` prefix), or the build fails.

## 4. Document shape (v1)

Top-level keys (all required unless noted). Field lists are **minimal v1**; implementations may add subfields in later minor versions.

```json
{
  "spec_version": "1.0",
  "challenge_id": "url-shortener-saas",
  "title": "URL Shortener SaaS",
  "metadata": {
    "category": "saas_app",
    "difficulty": "medium",
    "tags": ["http", "storage"],
    "time_limit_minutes": 90
  },
  "requirements": [
    "Users can create short links that redirect to long URLs."
  ],
  "orchestration": {
    "tournament_formats_allowed": ["DUEL", "BRACKET", "MARATHON"],
    "phase_hints": {
      "research": { "objectives": ["Survey patterns for URL safety and storage."] },
      "architecture": { "deliverables": ["ADR or design doc path under docs/"] }
    },
    "milestones": []
  },
  "delivery": {
    "root_readme_required": true,
    "artifact_globs": ["README.md", "docs/**/*.md"]
  },
  "quality": {
    "commands": [
      { "name": "lint", "cmd": ["make", "lint"], "required": true },
      { "name": "test", "cmd": ["make", "test"], "required": true }
    ]
  },
  "judge": {
    "rubric_version": "1",
    "criteria": [
      {
        "id": "correctness",
        "weight": 0.35,
        "description": "Meets functional requirements; tests pass."
      }
    ],
    "pass_gates": [
      { "criterion_id": "correctness", "min_score": 0.5 }
    ]
  },
  "agents": {
    "global_constraints": [
      "Do not exfiltrate secrets; use LiteLLM proxy only."
    ],
    "roles": {
      "architect": { "focus": ["boundaries", "interfaces", "module map"] },
      "builder": { "focus": ["implementation", "tests"] }
    }
  },
  "hidden_test_hints": []
}
```

### 4.1 Semantics

- **`spec_version`:** Semantic version string for the **spec document** format (not the challenge content). Breaking JSON shape changes bump major.
- **`metadata`:** Aligns with existing `Challenge` / API fields; `time_limit_minutes` applies to timed formats; marathon may ignore wall-clock where orchestrator already does.
- **`requirements`:** Functional requirements (string list); judge and builders both consume; replaces free-form-only MD lists for **machine** use (MD may duplicate for humans).
- **`orchestration`:** Hints and constraints for the core loop (formats, phase objectives, optional `milestones` entries for marathon alignment). Orchestrator remains authoritative on **actual** phase transitions; this block is **input**, not execution state.
- **`delivery`:** What must exist in the repo for submission (globs, README). Supports future module manifest paths (`MODULES.json` under **F**).
- **`quality`:** **Forward link to pipeline A:** declarative commands the runner executes in sandbox (names + argv). **v1:** `commands` may be an empty array; absence of commands means no automated quality runner until pipeline A consumes this block.
- **`judge`:** Rubric: weighted criteria plus **structured** `pass_gates`: `{ "criterion_id", "min_score" }[]`.
- **`agents`:** Non-secret instructions and role focus; tool allowlists can be added as `tools_allow: string[]` per role in v1 if already in codebase patterns.
- **`hidden_test_hints`:** Same role as today; surfaced only where appropriate.

## 5. Validation and CI

- **Library loader:** Given `challenge_id`, read `challenge.spec.json`, parse with shared Pydantic models (`extra = "forbid"`).
- **CI:** Script or pytest that glob-finds every `challenges/library/*/challenge.spec.json`, validates, and checks MD/sync rules.
- **API:** Challenge endpoints may return a **merged** view: narrative from MD + structured fields from spec (cached or read-through).

## 6. Database and API

- **Option v1 (recommended):** Store **`spec_snapshot` JSONB** on `challenges` (or tournament row) at **publish/import** time so runs are reproducible even if git library changes.
- Keep existing columns where still useful for queries (slug, title, category); migrate toward populating them from the spec on ingest.
- **API:** Extend `ChallengeResponse` with optional `spec_version` and nested blocks as needed, or embed full `spec` object behind a flag to avoid breaking clients.

## 7. Orchestrator integration

- Replace or supplement `_load_challenge` path: load **both** `CHALLENGE.md` and `challenge.spec.json`; attach parsed spec to in-memory tournament / event payload.
- Phase timers and marathon **milestones:** `orchestration.milestones` is an ordered list `{ "id", "phase", "label", "completion_criteria_ref" }` (exact fields in Pydantic model). Orchestrator uses these when format is MARATHON; empty list means “use default phase order with manual advance only” (current behavior).

## 8. Judge integration

- Judge reads `judge.criteria` weights and `pass_gates`; scoring outputs reference `criterion_id`.
- Hidden tests metadata can remain in DB `hidden_tests` or move under spec `judge.hidden_suite` in v1.1; v1 may keep DB column for backward compatibility.

## 9. Builder agents

- Inject a **trimmed JSON** or markdown summary derived from `requirements`, `delivery`, `quality`, `agents` into the team mailbox or bootstrap context (implementation detail in agents package).
- **No secrets** in spec; validated at parse time (reject keys that look like env var payloads if introduced later).

## 10. Errors

- **Missing spec file:** Challenge directory invalid for tournament start; clear 400 with `challenge_id`.
- **Validation error:** Return field paths (Pydantic); CI prints same.
- **MD/spec mismatch:** CI failure; runtime may warn or hard-fail per config.

## 11. Testing

- Golden fixtures: minimal valid spec + one broken spec per error class.
- Round-trip: load from `challenges/library` sample, assert API/orchestrator sees expected structure.
- Regression: existing challenges gain `challenge.spec.json` in a follow-up migration PR.

## 12. Migration

1. Add Pydantic models + loader utilities in `packages/shared`.
2. Add `challenge.spec.json` to each existing library challenge (scripted from current MD + defaults).
3. Wire API and orchestrator to prefer spec when present; fallback to MD-only with **deprecated** warning until all challenges migrated.
4. Add CI gate: no new challenge without spec.

## 13. Self-review

- **Placeholders:** None; empty `quality.commands` is explicitly valid v1 (no automated gates until A).
- **Consistency:** Pass gates specified as structured objects, not ambiguous strings.
- **Scope:** Single spec file for challenge content; does not implement A/F/B/E/D — only defines hooks (`quality`, `delivery`) those features consume.

## 14. Out of scope (this spec)

- Implementation code, judge mini-language beyond weighted criteria + structured pass gates.
- Hosted-only DB-only authoring (D) — may be a later import path into the same JSON shape.

---

**Next step:** Use **writing-plans** skill to produce an implementation plan (models, loader, CI, API, orchestrator, fixtures, migration of library entries).
