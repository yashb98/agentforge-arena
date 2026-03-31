---
name: github-researcher
description: |
  Search GitHub for repositories, code patterns, and best practices in real-time.
  Use whenever an agent needs to find existing implementations, evaluate libraries,
  or discover new techniques. Triggers on: "search GitHub", "find repos",
  "look for implementations", "how do others solve", "best practices for",
  "find a library for", or when the Researcher agent is active during RESEARCH phase.
  Always prefer this over cached training knowledge for implementation patterns.
---

# GitHub Researcher Skill

## Purpose
Find the best, most current code patterns and libraries from GitHub.
This skill ensures agents use REAL, CURRENT approaches — not stale training data.

## Core Principle
**NEVER rely on training knowledge for implementation details.**
Always search GitHub for the latest patterns, especially for:
- Framework-specific patterns (FastAPI, Next.js, etc.)
- Library APIs that may have changed
- Best practices that evolve rapidly
- New tools and packages

## Search Strategies

### 1. Find Similar Projects
```
Query: "{challenge_type} {tech_stack} production"
Sort: stars (most popular) AND recently updated (last 6 months)
Evaluate: README quality, test coverage, last commit date, issue count
```

### 2. Find Implementation Patterns
```
Query: "{specific_feature} {language} example"
Filter: Language, Last pushed > 6 months ago
Evaluate: Code quality, documentation, license compatibility
```

### 3. Find Libraries/Packages
```
Query: "{functionality} {language} library"
Then verify on PyPI/NPM: version > 1.0, weekly downloads, maintenance status
```

### 4. Find Configuration Examples
```
Query: "filename:pyproject.toml {package_name}"
Query: "filename:docker-compose.yml {service_name}"
Query: "filename:CLAUDE.md agentforge OR agent"
```

## Evaluation Rubric

| Signal | Good | Warning | Bad |
|--------|------|---------|-----|
| Last commit | < 30 days | 30-180 days | > 180 days |
| Stars | > 100 | 10-100 | < 10 |
| Open issues | < 50 | 50-200 | > 200 |
| License | MIT, Apache 2.0 | LGPL | GPL, None |
| Tests | Has CI + tests | Has tests, no CI | No tests |
| Docs | README + docs/ | README only | No README |

## GitHub API Usage
```bash
# Search repositories
curl -s "https://api.github.com/search/repositories?q={query}&sort=stars&order=desc&per_page=5"

# Get repo details
curl -s "https://api.github.com/repos/{owner}/{repo}"

# Read README
curl -s "https://raw.githubusercontent.com/{owner}/{repo}/main/README.md"

# Search code patterns
curl -s "https://api.github.com/search/code?q={pattern}+language:{lang}"
```

## Output Format
For each relevant repo found, extract:
```markdown
### [repo-name](url) — ⭐ {stars} | Updated: {date}
- **What it does**: One-line description
- **Relevant to**: Which part of our challenge
- **Key patterns to adopt**: Specific files/patterns worth replicating
- **Dependencies it uses**: Libraries we should consider
- **Gotchas**: Known issues, limitations, or outdated parts
```

## Rate Limiting
- GitHub API: 60 requests/hour unauthenticated, 5000/hour with token
- Always use `GITHUB_TOKEN` env var if available
- Cache results in Redis with 1-hour TTL to avoid redundant searches
