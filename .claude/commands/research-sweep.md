# /research-sweep

Run a real-time intelligence sweep to update the project's knowledge of the AI agent ecosystem.

## Usage
```
/research-sweep [scope]
```

## Arguments
- `scope`: `full` (default) | `competitors` | `tools` | `papers` | `docker`

## What This Command Does

Searches the web for the LATEST information across these domains:

### 1. Competitor Landscape (`competitors`)
```
Search: "AI agent competition tournament platform {CURRENT_MONTH} {CURRENT_YEAR}"
Search: "multi-agent coding competition {CURRENT_YEAR}"
Search: "LLM arena benchmark {CURRENT_MONTH} {CURRENT_YEAR}"
```
Updates: `docs/research/competitors.md`

### 2. Tools & Infrastructure (`tools`)
```
Search: "Docker Sandboxes AI agents update {CURRENT_MONTH}"
Search: "MCP server new plugins {CURRENT_MONTH} {CURRENT_YEAR}"
Search: "Claude Code new features {CURRENT_MONTH}"
Search: "LiteLLM changelog {CURRENT_YEAR}"
Search: "Langfuse new features {CURRENT_YEAR}"
```
Updates: `docs/research/tools.md`

### 3. Research Papers (`papers`)
```
Search: "arxiv multi-agent collaboration competition {CURRENT_MONTH}"
Search: "arxiv LLM coding agent benchmark {CURRENT_YEAR}"
Search: "arxiv agent evaluation framework {CURRENT_YEAR}"
```
Updates: `docs/research/papers.md`

### 4. Docker & Sandbox Ecosystem (`docker`)
```
Search: "Docker Desktop sandbox update {CURRENT_MONTH}"
Search: "E2B sandbox new features {CURRENT_YEAR}"
Search: "Firecracker MicroVM update {CURRENT_YEAR}"
```
Updates: `docs/research/docker.md`

## Execution Steps
```python
from packages.research.src.aggregator.sweep import ResearchSweep

sweep = ResearchSweep(scope="$SCOPE")
report = await sweep.run()

# Save findings
report.save_to("docs/research/")

# Update memory
with open(".claude/memory/latest-sweep.md", "w") as f:
    f.write(report.summary())

print(f"Sweep complete: {report.sources_found} sources, {report.insights_count} insights")
```

## Schedule
Run this weekly to keep the architecture document current.
Update the "Competitive Landscape" section of the architecture doc with findings.
