# packages/sandbox — CLAUDE.md

## What This Package Is
Docker Sandbox MicroVM management. Creates isolated environments for each team,
manages network policies, resource limits, and filesystem access.

## Key Modules
- `src/docker/manager.py` — SandboxManager: create, destroy, resource monitoring
- `src/security/agentshield.py` — 102-rule security scanner (pre-execution)
- `src/security/parry.py` — Prompt injection detection
- `src/network/policy.py` — Network allow/deny list management
- `src/resource/limits.py` — RAM, CPU, disk limit enforcement

## Security Model (5 Layers)
1. MicroVM Hardware Boundary (kernel isolation)
2. Network Isolation (allow/deny lists)
3. Resource Limits (4GB RAM, 2 vCPU, 10GB disk)
4. AgentShield Pre-Execution Scan (102 rules)
5. parry Injection Scanner (real-time)

## Dependencies
- `packages/shared` — Types, events, config
