# packages/replay — CLAUDE.md

## What This Package Is
Tournament replay system. Exports Langfuse traces into replayable timelines
with code diffs, agent actions, and tutor commentary.

## Key Modules
- `src/traces/exporter.py` — Langfuse trace extraction
- `src/timeline/builder.py` — Chronological event timeline
- `src/timeline/differ.py` — Code diff generation at each step
- `src/export/formatter.py` — Export to JSON/HTML formats
- `src/commentary/generator.py` — Post-hoc tutor commentary

## Replay Data Structure
```json
{
  "tournament_id": "...",
  "timeline": [
    {
      "timestamp": "...",
      "team_id": "...",
      "agent_role": "architect",
      "action": "file_write",
      "file": "src/main.py",
      "diff": "...",
      "commentary": "The architect just created the entry point..."
    }
  ]
}
```

## Dependencies
- `packages/shared` — Types, events, config
