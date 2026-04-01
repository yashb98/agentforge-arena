# Challenge Library

Each challenge is a directory under `library/` with this structure:

```
library/<challenge-slug>/
├── CHALLENGE.md           # Brief shown to competing teams
├── hidden_tests/          # pytest suite run by the judge (never shown to teams)
│   ├── conftest.py        # Shared fixtures (httpx client, helpers)
│   ├── test_*.py          # Test modules
│   └── ...
└── scoring_config.json    # Optional weight overrides for this challenge
```

## Writing a New Challenge

1. Create `library/<slug>/CHALLENGE.md` with frontmatter:
   - `# Challenge: <Title>`
   - `## Difficulty: <Easy|Medium|Hard> | Category: <category> | Time: <minutes> minutes`
   - Sections: Brief, Requirements (Must/Should/Nice), Tech Constraints, Hidden Test Hints, Scoring Weights

2. Write hidden tests using `httpx` to call the team's app on `localhost:8000`.
   Tests must be self-contained — no imports from the team's code.

3. Add `scoring_config.json` if you need non-default scoring weights.

## Available Challenges

| Slug | Difficulty | Category | Time |
|------|-----------|----------|------|
| `url-shortener-saas` | Medium | SaaS App | 90 min |
| `realtime-chat-app` | Hard | Real Time | 120 min |
| `task-queue-engine` | Hard | API Service | 120 min |
