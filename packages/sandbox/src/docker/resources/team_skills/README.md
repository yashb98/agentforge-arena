# Bundled team skill packs (`.claude/skills/`)

Every new tournament sandbox gets **subdirectories here** copied into
`project/.claude/skills/<pack-name>/` when the workspace is initialized.

## Currently bundled (vendored)

| Pack | Source |
|------|--------|
| `arena-project-hints` | AgentForge Arena (this repo) |
| `hermes-test-driven-development` | [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) `skills/software-development/test-driven-development` |
| `hermes-systematic-debugging` | same tree, `systematic-debugging` |
| `hermes-writing-plans` | `writing-plans` |
| `hermes-requesting-code-review` | `requesting-code-review` |
| `hermes-github-pr-workflow` | `skills/github/github-pr-workflow` |
| `hermes-github-codebase-inspection` | `skills/github/codebase-inspection` |

Each `hermes-*` directory includes `ORIGIN.md` with upstream path and MIT notice.

## Vendoring skills from Hermes / agentskills.io

1. **License:** [Hermes Agent](https://github.com/NousResearch/hermes-agent) is MIT. Keep each pack’s `LICENSE` or note the upstream path in a one-line `ORIGIN.md` inside the pack directory.

2. **Copy a pack:** From a Hermes checkout, copy one folder under their `skills/` tree into this directory:

   ```bash
   cp -R /path/to/hermes-agent/skills/some-pack \
     packages/sandbox/src/docker/resources/team_skills/some-pack
   ```

3. **Normalize for Claude Code:** Each pack should contain at least `SKILL.md` with YAML frontmatter:

   ```yaml
   ---
   name: pack-name
   description: |
     One or more lines the agent uses to decide when to load this skill.
   ---
   ```

   If upstream uses different frontmatter keys, align with the format used in this repo’s `.claude/skills/*/SKILL.md`.

4. **Omit noise:** Do not copy entire Hermes repos here—only the skill **folder** you want in every team sandbox.

5. **Size:** Large reference files under a pack are fine; keep total bundled size reasonable so sandbox init stays fast.

## Naming

- Directory name = pack id (e.g. `http-client-patterns`).
- `name` in frontmatter should match or be a short alias.
