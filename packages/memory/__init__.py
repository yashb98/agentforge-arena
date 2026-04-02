"""
AgentForge Arena — Agent Memory System

Three-layer memory architecture:
  L1 Working Memory  — per-agent Redis state (fast, ephemeral)
  L2 Module Memory   — structured PostgreSQL records (persistent)
  L3 Semantic Memory — code search via Qdrant (vector)
"""
