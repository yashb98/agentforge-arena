"""Challenge-aligned research: arXiv + GitHub → markdown briefs and peer review."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

from packages.research.src.aggregator.sweep import (
    ArxivSearcher,
    GitHubSearcher,
    PaperResult,
    RepoResult,
)

logger = logging.getLogger(__name__)

# arXiv asks for modest request rates; stay conservative between queries.
_ARXIV_DELAY_S = 3.0


@dataclass(frozen=True)
class ChallengeResearchContext:
    """Inputs derived from CHALLENGE.md + challenge.spec.json."""

    title: str
    challenge_id: str
    requirements: list[str]
    category: str | None = None


def _tokenize_query(text: str, max_words: int = 8) -> str:
    words = re.findall(r"[a-zA-Z0-9][a-zA-Z0-9+.-]*", text.lower())
    stop = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "for",
        "with",
        "from",
        "into",
        "per",
        "to",
        "of",
        "in",
        "on",
        "at",
        "by",
        "endpoint",
        "optional",
    }
    out = [w for w in words if w not in stop and len(w) > 1][:max_words]
    return " ".join(out) if out else text[:80].strip()


def _github_queries(ctx: ChallengeResearchContext) -> list[str]:
    core = _tokenize_query(ctx.title, 6)
    queries = [core]
    if ctx.category:
        cat = ctx.category.replace("_", " ")
        queries.append(f"{core} {cat}")
    if ctx.requirements:
        queries.append(f"{_tokenize_query(ctx.requirements[0], 5)} implementation open source")
    return list(dict.fromkeys(queries))[:4]


def _arxiv_queries(ctx: ChallengeResearchContext) -> list[str]:
    core = _tokenize_query(ctx.title, 5)
    queries = [core]
    if ctx.requirements:
        queries.append(_tokenize_query(ctx.requirements[0][:240], 7))
    return list(dict.fromkeys(queries))[:3]


def _dedupe_repos(repos: list[RepoResult]) -> list[RepoResult]:
    seen: set[str] = set()
    out: list[RepoResult] = []
    for r in repos:
        if r.full_name in seen:
            continue
        seen.add(r.full_name)
        out.append(r)
    return out


def _dedupe_papers(papers: list[PaperResult]) -> list[PaperResult]:
    seen: set[str] = set()
    out: list[PaperResult] = []
    for p in papers:
        key = p.url or p.title
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _render_research_md(
    ctx: ChallengeResearchContext,
    repos: list[RepoResult],
    papers: list[PaperResult],
    *,
    doc_heading: str | None = None,
    intro: str | None = None,
) -> str:
    heading = doc_heading or f"Research — {ctx.title}"
    intro_text = intro or (
        "Automated sweep of public GitHub repositories and arXiv papers aligned "
        "with the challenge title and first requirements. Refine with team-specific "
        "queries during the research phase."
    )
    lines = [
        f"# {heading}",
        "",
        f"**Challenge ID:** `{ctx.challenge_id}`",
        "",
        intro_text,
        "",
        "## GitHub repositories",
        "",
    ]
    if not repos:
        lines.append("_No repositories returned (check network, API limits, or queries)._")
        lines.append("")
    else:
        for r in repos:
            lines.append(f"### [{r.full_name}]({r.url}) — {r.stars} stars")
            lines.append(f"- **Description:** {r.description or '—'}")
            lines.append(f"- **Language:** {r.language or '—'} | **Pushed:** {r.last_pushed or '—'}")
            if r.topics:
                lines.append(f"- **Topics:** {', '.join(r.topics[:8])}")
            lines.append("")

    lines.extend(["## arXiv papers", ""])
    if not papers:
        lines.append("_No papers returned (check queries or arXiv availability)._")
        lines.append("")
    else:
        for p in papers:
            lines.append(f"### [{p.title}]({p.url})")
            lines.append(f"- **Authors:** {', '.join(p.authors[:5])}")
            lines.append(f"- **Published:** {p.published} | **Categories:** {', '.join(p.categories[:4])}")
            ab = (p.abstract or "").strip().replace("\n", " ")
            lines.append(f"- **Abstract (excerpt):** {ab[:400]}{'…' if len(ab) > 400 else ''}")
            lines.append("")

    return "\n".join(lines)


def _render_use_cases_md(ctx: ChallengeResearchContext) -> str:
    lines = [
        f"# Use cases — {ctx.title}",
        "",
        "Structured from official challenge requirements. Extend with actors, "
        "preconditions, and acceptance tests during architecture.",
        "",
    ]
    for i, req in enumerate(ctx.requirements, 1):
        short = req.strip()
        head = short[:90] + ("…" if len(short) > 90 else "")
        lines.append(f"## UC-{i}: {head}")
        lines.append("")
        lines.append("### Primary goal")
        lines.append(f"Satisfy: {short}")
        lines.append("")
        lines.append("### Actors")
        lines.append("- TBD (e.g. API client, worker, admin)")
        lines.append("")
        lines.append("### Main flow (draft)")
        lines.append("1. Trigger context is established.")
        lines.append(f"2. System behavior matches: _{short[:200]}{'…' if len(short) > 200 else ''}_")
        lines.append("3. Outcome is observable via API, DB, or UI as appropriate.")
        lines.append("")
        lines.append("### Acceptance / test ideas")
        lines.append("- Add automated tests mapping to this requirement.")
        lines.append("")
    return "\n".join(lines)


def _peer_review_template(
    ctx: ChallengeResearchContext,
    repos: list[RepoResult],
    papers: list[PaperResult],
) -> str:
    lines = [
        f"# Peer review (automated draft) — {ctx.title}",
        "",
        "This section was generated without an LLM. Enable `RESEARCH_PEER_REVIEW_WITH_LLM=true` "
        "for a richer synthesis when LiteLLM is available.",
        "",
        "## Coverage",
        "",
        f"- **Repositories reviewed (sample):** {len(repos)}",
        f"- **Papers reviewed (sample):** {len(papers)}",
        "",
        "## Strengths (of public landscape)",
        "",
    ]
    if repos:
        hi = [r for r in repos if r.stars >= 100]
        if hi:
            lines.append(
                f"- Several projects show community traction (e.g. ≥100 stars): "
                f"{', '.join(r.full_name for r in hi[:5])}."
            )
        else:
            lines.append("- Niche repos; verify maturity and maintenance before adopting patterns.")
    else:
        lines.append("- No repo hits; widen GitHub queries or add a `GITHUB_TOKEN` for higher limits.")
    lines.append("")
    if papers:
        lines.append("- Recent literature may inform architecture choices; read abstracts in RESEARCH.md.")
    else:
        lines.append("- No arXiv hits; try domain-specific keywords (e.g. system name, algorithm).")
    lines.extend(
        [
            "",
            "## Risks and gaps vs challenge",
            "",
            "- Public repos rarely match **all** requirements; expect integration work.",
            "- Security, multi-tenancy, and operational concerns are often underdocumented.",
            "",
            "## Recommended focus",
            "",
            "1. Pick **one** reference stack close to the challenge category.",
            "2. Map each requirement to a concrete module and test.",
            "3. Re-run targeted GitHub/code search per subsystem during BUILD.",
            "",
        ]
    )
    return "\n".join(lines)


async def _render_peer_review_llm(
    ctx: ChallengeResearchContext,
    repos: list[RepoResult],
    papers: list[PaperResult],
    llm: object,
) -> str | None:
    repo_lines = "\n".join(
        f"- {r.full_name} ({r.stars}★): {r.description[:200]}"
        for r in repos[:12]
    )
    paper_lines = "\n".join(
        f"- {p.title[:120]} — {p.abstract[:180]}…"
        for p in papers[:10]
    )
    user = (
        f"Challenge title: {ctx.title}\n"
        f"Challenge id: {ctx.challenge_id}\n"
        f"Category: {ctx.category or 'n/a'}\n\n"
        f"Requirements (verbatim count {len(ctx.requirements)}):\n"
        + "\n".join(f"- {r[:300]}" for r in ctx.requirements[:15])
        + "\n\n## Sample repositories\n"
        + repo_lines
        + "\n\n## Sample papers (excerpts)\n"
        + paper_lines
        + "\n\nWrite a **peer review** in Markdown with these H2 sections exactly: "
        "## Strengths of public work, ## Gaps vs this challenge, ## Risks, "
        "## Recommended implementation focus, ## Suggested validation & tests. "
        "Be specific to the challenge; 400-800 words."
    )
    try:
        resp = await llm.completion(  # type: ignore[union-attr]
            messages=[
                {
                    "role": "system",
                    "content": "You are a senior engineer peer-reviewing external sources for a hackathon build.",
                },
                {"role": "user", "content": user},
            ],
            trace_name="research.peer_review",
            trace_metadata={"challenge_id": ctx.challenge_id},
            temperature=0.25,
            max_tokens=4096,
        )
        body = getattr(resp, "content", "") or ""
        return f"# Peer review — {ctx.title}\n\n{body.strip()}"
    except Exception:
        logger.exception("LLM peer review failed")
        return None


def _render_queries_md(
    ctx: ChallengeResearchContext,
    gh_qs: list[str],
    ax_qs: list[str],
    *,
    doc_title: str | None = None,
    blurb: str | None = None,
) -> str:
    title = doc_title or f"Research queries — {ctx.title}"
    blurb_text = blurb or "Queries used for the automated sweep (edit and re-search as needed)."
    lines = [
        f"# {title}",
        "",
        blurb_text,
        "",
        "## GitHub",
        "",
    ]
    for q in gh_qs:
        lines.append(f"- `{q}`")
    lines.extend(["", "## arXiv", ""])
    for q in ax_qs:
        lines.append(f"- `{q}`")
    lines.append("")
    return "\n".join(lines)


async def run_challenge_research_brief(
    ctx: ChallengeResearchContext,
    *,
    github_token: str | None,
    arxiv_max_per_query: int,
    github_per_query: int,
    llm_client: object | None,
    peer_review_with_llm: bool,
) -> dict[str, str]:
    """Return relative paths → markdown bodies for writing into the team project root."""
    gh = GitHubSearcher(token=github_token)
    ax = ArxivSearcher()
    gh_qs = _github_queries(ctx)
    ax_qs = _arxiv_queries(ctx)

    repos: list[RepoResult] = []
    for gq in gh_qs:
        repos.extend(await gh.search_repos(gq, per_page=github_per_query))
        await asyncio.sleep(0.4)

    repos = _dedupe_repos(repos)[:18]

    papers: list[PaperResult] = []
    for aq in ax_qs:
        papers.extend(await ax.search(aq, max_results=arxiv_max_per_query))
        await asyncio.sleep(_ARXIV_DELAY_S)

    papers = _dedupe_papers(papers)[:15]

    research_md = _render_research_md(ctx, repos, papers)
    use_cases_md = _render_use_cases_md(ctx)
    queries_md = _render_queries_md(ctx, gh_qs, ax_qs)

    peer_md: str
    if peer_review_with_llm and llm_client is not None:
        llm_peer = await _render_peer_review_llm(ctx, repos, papers, llm_client)
        peer_md = llm_peer or _peer_review_template(ctx, repos, papers)
    else:
        peer_md = _peer_review_template(ctx, repos, papers)

    return {
        "RESEARCH.md": research_md,
        "USE_CASES.md": use_cases_md,
        "PEER_REVIEW.md": peer_md,
        "RESEARCH_QUERIES.md": queries_md,
    }


def _github_queries_architecture(ctx: ChallengeResearchContext) -> list[str]:
    core = _tokenize_query(ctx.title, 5)
    qs = [f"{core} system design production", f"{core} reference architecture patterns"]
    if ctx.category:
        cat = ctx.category.replace("_", " ")
        qs.append(f"{core} {cat} scalable backend")
    return list(dict.fromkeys(qs))[:3]


def _arxiv_queries_architecture(ctx: ChallengeResearchContext) -> list[str]:
    core = _tokenize_query(ctx.title, 4)
    return list(
        dict.fromkeys(
            [
                f"{core} distributed systems architecture",
                f"{core} software engineering design",
            ]
        )
    )[:2]


async def run_architecture_followup_research(
    ctx: ChallengeResearchContext,
    *,
    github_token: str | None,
    arxiv_max_per_query: int,
    github_per_query: int,
) -> dict[str, str]:
    """Second-pass GitHub/arXiv sweep for ARCHITECTURE phase (narrower, design-oriented queries)."""
    gh = GitHubSearcher(token=github_token)
    ax = ArxivSearcher()
    gh_qs = _github_queries_architecture(ctx)
    ax_qs = _arxiv_queries_architecture(ctx)

    repos: list[RepoResult] = []
    for gq in gh_qs:
        repos.extend(await gh.search_repos(gq, per_page=github_per_query))
        await asyncio.sleep(0.4)

    repos = _dedupe_repos(repos)[:12]

    papers: list[PaperResult] = []
    for aq in ax_qs:
        papers.extend(await ax.search(aq, max_results=arxiv_max_per_query))
        await asyncio.sleep(_ARXIV_DELAY_S)

    papers = _dedupe_papers(papers)[:10]

    research_md = _render_research_md(
        ctx,
        repos,
        papers,
        doc_heading=f"Architecture follow-up research — {ctx.title}",
        intro=(
            "Second-pass sweep focused on system design, reference architectures, and scalable "
            "patterns. Use together with RESEARCH.md during the ARCHITECTURE phase."
        ),
    )
    queries_md = _render_queries_md(
        ctx,
        gh_qs,
        ax_qs,
        doc_title=f"Architecture-phase queries — {ctx.title}",
        blurb="Queries used for the architecture follow-up sweep.",
    )
    return {
        "RESEARCH_ARCHITECTURE.md": research_md,
        "RESEARCH_QUERIES_ARCHITECTURE.md": queries_md,
    }


def _requirements_trace_template(ctx: ChallengeResearchContext) -> str:
    lines = [
        f"# Requirements trace (seed) — {ctx.title}",
        "",
        "Map each official requirement to a subsystem and test idea. Expand during ARCHITECTURE.",
        "",
        "| # | Requirement (excerpt) | Subsystem / API (TBD) | Test / acceptance idea |",
        "|---|------------------------|------------------------|-------------------------|",
    ]
    for i, req in enumerate(ctx.requirements, 1):
        excerpt = req.strip().replace("|", "\\|").replace("\n", " ")
        if len(excerpt) > 120:
            excerpt = excerpt[:117] + "..."
        lines.append(f"| {i} | {excerpt} | TBD | TBD |")
    lines.append("")
    return "\n".join(lines)


def _architecture_seed_template(
    ctx: ChallengeResearchContext,
    research_bundle: dict[str, str],
    extra_architecture_research: str,
) -> str:
    peer_ex = (research_bundle.get("PEER_REVIEW.md") or "").strip()
    peer_snip = peer_ex[:1200] + ("…" if len(peer_ex) > 1200 else "")
    extra_snip = extra_architecture_research.strip()[:800] + (
        "…" if len(extra_architecture_research.strip()) > 800 else ""
    )
    lines = [
        f"# Architecture seed — {ctx.title}",
        "",
        "Generated from the challenge spec and automated research summaries. "
        "Refine into **ARCHITECTURE.md** with diagrams and concrete decisions.",
        "",
        "## Objective",
        f"Deliver a build that satisfies `{ctx.challenge_id}` requirements in category "
        f"`{ctx.category or 'n/a'}`.",
        "",
        "## Context summary",
        "- See **USE_CASES.md** for requirement-structured flows.",
        "- See **RESEARCH.md** and **RESEARCH_ARCHITECTURE.md** (if present) for external patterns.",
        "",
        "## Proposed subsystems (draft — team to confirm)",
        "- **API surface** — HTTP/WebSocket or RPC aligned to challenge.",
        "- **Core domain** — business logic isolated from transport.",
        "- **Persistence** — choose store(s) matching consistency and query needs.",
        "- **Async / jobs** — if the challenge implies background work or streams.",
        "",
        "## Data & APIs",
        "- Define primary entities and ownership boundaries.",
        "- List public endpoints or events and idempotency expectations.",
        "",
        "## Cross-cutting concerns",
        "- AuthN/Z, observability, configuration, error model, rate limits (if applicable).",
        "",
        "## Risks & unknowns",
        "",
    ]
    if peer_snip:
        lines.append("Excerpt from **PEER_REVIEW.md**:")
        lines.append("")
        lines.append(f"> {peer_snip.replace(chr(10), ' ')}")
        lines.append("")
    else:
        lines.append("- No peer-review text in bundle; read **PEER_REVIEW.md** in the repo.")
        lines.append("")
    if extra_snip:
        lines.append("Excerpt from **RESEARCH_ARCHITECTURE.md**:")
        lines.append("")
        lines.append(f"> {extra_snip.replace(chr(10), ' ')}")
        lines.append("")
    lines.extend(
        [
            "## Build-phase milestones",
            "1. Skeleton services/modules and config.",
            "2. Vertical slice for the highest-priority requirement.",
            "3. Tests and docs for each merged increment.",
            "",
        ]
    )
    return "\n".join(lines)


async def _architecture_seed_llm(
    ctx: ChallengeResearchContext,
    research_bundle: dict[str, str],
    extra_architecture_research: str,
    llm: object,
) -> str | None:
    blocks: list[str] = []
    for key in ("RESEARCH.md", "USE_CASES.md", "PEER_REVIEW.md"):
        body = (research_bundle.get(key) or "")[:6000]
        blocks.append(f"## Source: {key}\n{body}")
    if extra_architecture_research.strip():
        blocks.append(f"## Source: RESEARCH_ARCHITECTURE.md\n{extra_architecture_research[:4000]}")
    user = (
        f"Challenge title: {ctx.title}\n"
        f"Challenge id: {ctx.challenge_id}\n"
        f"Category: {ctx.category or 'n/a'}\n\n"
        + "\n\n".join(blocks)
        + "\n\nProduce **architecture seed** content in Markdown. "
        "Use these H2 sections exactly: ## Objective, ## Context summary, ## Proposed subsystems, "
        "## Data & APIs, ## Cross-cutting concerns, ## Risks & unknowns, ## Build-phase milestones. "
        "Be concrete where the sources allow; use TBD where the team must decide. 500–1200 words. "
        "Do not repeat entire source documents."
    )
    try:
        resp = await llm.completion(  # type: ignore[union-attr]
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a principal engineer drafting an architecture seed for a "
                        "time-boxed competitive build. Ground recommendations in the provided excerpts."
                    ),
                },
                {"role": "user", "content": user},
            ],
            trace_name="research.architecture_seed",
            trace_metadata={"challenge_id": ctx.challenge_id},
            temperature=0.2,
            max_tokens=4096,
        )
        body = getattr(resp, "content", "") or ""
        body = body.strip()
        if not body:
            return None
        if body.startswith("#"):
            return body
        return f"# Architecture seed — {ctx.title}\n\n{body}"
    except Exception:
        logger.exception("LLM architecture seed failed")
        return None


async def generate_architecture_phase_seed_docs(
    ctx: ChallengeResearchContext,
    research_bundle: dict[str, str],
    *,
    llm_client: object | None,
    seed_with_llm: bool,
    extra_architecture_research: str = "",
) -> dict[str, str]:
    """ARCHITECTURE_SEED.md + REQUIREMENTS_TRACE.md from cached research + optional follow-up body."""
    trace = _requirements_trace_template(ctx)
    if seed_with_llm and llm_client is not None:
        llm_body = await _architecture_seed_llm(
            ctx, research_bundle, extra_architecture_research, llm_client
        )
        seed_md = llm_body or _architecture_seed_template(
            ctx, research_bundle, extra_architecture_research
        )
    else:
        seed_md = _architecture_seed_template(ctx, research_bundle, extra_architecture_research)
    return {
        "ARCHITECTURE_SEED.md": seed_md,
        "REQUIREMENTS_TRACE.md": trace,
    }
