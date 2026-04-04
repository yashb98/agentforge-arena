---
name: arena-project-hints
description: |
  Arena tournament project conventions. Use when bootstrapping or reviewing
  the team codebase—testing gates, Docker-only agent execution, and quality
  commands from challenge.spec.json.
---

# Arena project hints

## Quality gates

- Read `challenge.spec.json` → `quality.commands` and run those checks before hand-off.
- If `scripts/check_module_boundaries.py` exists and the team uses `MODULES.json`, keep imports within declared module boundaries.

## Safety

- Do not run untrusted agent code outside the team sandbox.
- Prefer the LiteLLM proxy for model calls; avoid embedding API keys in the repo.

## Tests

- Match or exceed the coverage expectations called out in the challenge brief and judge rubric.
