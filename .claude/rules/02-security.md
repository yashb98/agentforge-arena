# Rule 02: Security — Non-Negotiable

## Applies To
All code, all agents, all sandboxes. ZERO exceptions.

## Sandbox Security Model (5 Layers)

### Layer 1: MicroVM Hardware Boundary
- Each tournament team runs in a dedicated Docker Sandbox MicroVM
- Kernel-level isolation — teams CANNOT see each other's processes or files
- `docker sandbox create` with explicit resource limits

### Layer 2: Network Isolation
```
ALLOW: pypi.org, registry.npmjs.org, github.com, api.anthropic.com, api.openai.com
DENY: * (everything else)
```
- Agents CANNOT make arbitrary network requests
- No access to internal services from sandbox (DB, Redis, API)
- LiteLLM proxy is the ONLY way agents call LLMs

### Layer 3: Resource Limits (Per Team)
- RAM: 4GB max (8GB for Grand Prix)
- CPU: 2 vCPU (4 for Grand Prix)
- Disk: 10GB
- Process: Max 100 concurrent processes
- Idle timeout: 90 seconds per agent action

### Layer 4: AgentShield Pre-Execution Scan
Before ANY `bash` or `write` tool use inside a sandbox:
- Scan for secrets (14 patterns: AWS keys, API tokens, SSH keys, etc.)
- Scan for privilege escalation attempts (`sudo`, `chmod 777`, etc.)
- Scan for container escape attempts (`docker run`, `nsenter`, etc.)
- Scan for data exfiltration (`curl` to non-whitelisted domains)
- Block if ANY rule triggers. Log the violation.

### Layer 5: parry Injection Scanner
- Scans ALL tool inputs and outputs for prompt injection
- Detects indirect prompt injection from web content
- Detects data exfiltration attempts in LLM outputs
- Runs as real-time hook, not batch scan

## API Security
- JWT authentication with RS256 signing
- Rate limiting: 100 req/min for free tier, 1000 for pro, 5000 for enterprise
- Input validation via Pydantic strict models on ALL endpoints
- SQL injection prevention: SQLAlchemy ORM only, no raw SQL strings
- CORS: Explicit origin allowlist, no wildcards in production
- CSP headers on all responses

## Secrets Management
- ALL secrets in environment variables, loaded via Pydantic Settings
- NEVER log secrets — use `SecretStr` type from Pydantic
- NEVER pass secrets into sandbox environments
- API keys for LLM providers go through LiteLLM proxy ONLY
- Rotate keys quarterly (tracked in `.claude/memory/decisions-log.md`)

## Agent-Specific Security
- Agents CANNOT modify files outside their assigned workspace
- Agents CANNOT communicate with other teams (except cross-review phase, read-only)
- Agent system prompts are immutable during a tournament
- Agent tool permissions are whitelisted per role (see `.claude/agents/`)
- ALL agent actions are traced and attributable

## Incident Response
- Security violations are logged to `security_events` table with full context
- Critical violations (container escape attempts, data exfil) trigger immediate sandbox termination
- Alerts via webhook to admin channel
- Post-incident: trace replay + root cause analysis via Langfuse
