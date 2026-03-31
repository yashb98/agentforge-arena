---
name: plugin-discovery
description: |
  Search for, evaluate, and configure MCP plugins and npm/PyPI packages for agent
  projects. Use when agents need to find the best tools for their task, install
  external integrations, or set up MCP servers. Triggers on: "find plugin",
  "search for tool", "MCP server", "integrate with", "find package for",
  "what's the best library for", or when agents are evaluating external dependencies.
---

# Plugin Discovery Skill

## Purpose
Help agents find, evaluate, and integrate the best external tools and plugins.
Agents should behave like senior developers evaluating dependencies — not just
grabbing the first result.

## Discovery Sources

### MCP Plugin Registry
Search for MCP servers that provide tool integrations:
- Database connectors (PostgreSQL, MongoDB, Supabase)
- API clients (GitHub, Slack, Notion, etc.)
- Development tools (testing, linting, deployment)
- AI/ML tools (embedding, vector search, inference)

### PyPI (Python Packages)
```bash
# Search packages
curl -s "https://pypi.org/pypi/{package}/json" | jq '.info.version, .info.requires_python'
# Check download stats and maintenance status
```

### NPM (Node.js Packages)
```bash
# Search packages
curl -s "https://registry.npmjs.org/{package}" | jq '.["dist-tags"].latest, .time.modified'
```

## Evaluation Criteria (Score 1-10)

| Criterion | Weight | How to Check |
|-----------|--------|-------------|
| Maintenance | 30% | Last publish date, open issues response time |
| Popularity | 20% | Downloads/week, GitHub stars |
| Type Safety | 20% | Has TypeScript types / Python type hints |
| Security | 15% | No known vulnerabilities, trusted publisher |
| Documentation | 15% | README quality, API docs, examples |

**Minimum Score to Recommend: 6/10**

## Plugin Configuration Template
When a plugin is selected, generate config:
```json
{
  "name": "plugin-name",
  "version": "^1.2.3",
  "source": "npm|pypi|mcp",
  "reason": "Why this plugin was chosen over alternatives",
  "alternatives_considered": ["alt1", "alt2"],
  "config": {
    "key": "value"
  },
  "risk_level": "low|medium|high",
  "notes": "Any gotchas or special setup needed"
}
```

## Decision Framework
1. Is there a built-in solution? → Use it (no external dependency)
2. Is there one clearly dominant package? → Use it (e.g., `pydantic` for validation)
3. Are there multiple options? → Compare on evaluation criteria
4. Is it security-sensitive? → Extra scrutiny, prefer well-known packages
5. Will it be hard to replace? → Wrap in an adapter/interface
