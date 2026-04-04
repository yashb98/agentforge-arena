"""
AgentForge Arena — Real-Time Research Engine

Searches GitHub, arXiv, and the web for the latest techniques, libraries,
and best practices. This gives agents a competitive edge by finding CURRENT
information rather than relying on stale training data.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime

import httpx

from packages.shared.src.reliability.circuit_breaker import (
    CircuitBreaker,
    circuit_breaker_http_guard,
)

logger = logging.getLogger(__name__)

DEFAULT_HTTP_TIMEOUT = 30.0


@dataclass
class RepoResult:
    """A GitHub repository search result."""

    name: str
    full_name: str
    url: str
    description: str
    stars: int
    last_pushed: str
    language: str | None
    topics: list[str] = field(default_factory=list)
    open_issues: int = 0
    license_name: str | None = None
    readme_url: str | None = None


@dataclass
class PaperResult:
    """An arXiv paper search result."""

    title: str
    authors: list[str]
    abstract: str
    url: str
    published: str
    categories: list[str] = field(default_factory=list)
    has_code: bool = False
    code_url: str | None = None


@dataclass
class ResearchReport:
    """Aggregated research findings."""

    query: str
    repos: list[RepoResult] = field(default_factory=list)
    papers: list[PaperResult] = field(default_factory=list)
    packages_found: list[dict] = field(default_factory=list)
    insights: list[str] = field(default_factory=list)
    web_instant_snippets: list[str] = field(default_factory=list)
    scholar_hits: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def sources_found(self) -> int:
        return (
            len(self.repos)
            + len(self.papers)
            + len(self.packages_found)
            + len(self.web_instant_snippets)
            + len(self.scholar_hits)
        )

    @property
    def insights_count(self) -> int:
        return len(self.insights)

    def to_markdown(self) -> str:
        """Generate a RESEARCH.md document from findings."""
        lines = [
            f"# Research Report: {self.query}",
            f"Generated: {self.generated_at} | Sources: {self.sources_found}",
            "",
        ]

        if self.repos:
            lines.append("## Relevant GitHub Repositories")
            lines.append("")
            for repo in self.repos[:5]:
                lines.append(f"### [{repo.full_name}]({repo.url}) — ⭐ {repo.stars}")
                lines.append(f"- **Description**: {repo.description}")
                lines.append(f"- **Language**: {repo.language or 'Unknown'}")
                lines.append(f"- **Last pushed**: {repo.last_pushed}")
                lines.append(f"- **Topics**: {', '.join(repo.topics[:5])}")
                lines.append("")

        if self.papers:
            lines.append("## Relevant Research Papers")
            lines.append("")
            for paper in self.papers[:5]:
                lines.append(f"### [{paper.title}]({paper.url})")
                lines.append(f"- **Authors**: {', '.join(paper.authors[:3])}")
                lines.append(f"- **Published**: {paper.published}")
                lines.append(f"- **Code available**: {'Yes' if paper.has_code else 'No'}")
                lines.append(f"- **Abstract**: {paper.abstract[:200]}...")
                lines.append("")

        if self.web_instant_snippets:
            lines.append("## Web (DuckDuckGo instant answers)")
            lines.append("")
            for snip in self.web_instant_snippets[:5]:
                lines.append(f"- {snip}")
            lines.append("")

        if self.scholar_hits:
            lines.append("## Semantic Scholar")
            lines.append("")
            for hit in self.scholar_hits[:5]:
                lines.append(f"- {hit}")
            lines.append("")

        if self.insights:
            lines.append("## Key Insights")
            lines.append("")
            for insight in self.insights:
                lines.append(f"- {insight}")
            lines.append("")

        return "\n".join(lines)

    def save_to(self, directory: str) -> None:
        """Save the report to a directory."""
        import os
        os.makedirs(directory, exist_ok=True)
        filepath = os.path.join(directory, "RESEARCH.md")
        with open(filepath, "w") as f:
            f.write(self.to_markdown())

    def summary(self) -> str:
        """Short summary for memory storage."""
        return (
            f"Research sweep for '{self.query}': "
            f"{len(self.repos)} repos, {len(self.papers)} papers, "
            f"{len(self.insights)} insights"
        )


class GitHubSearcher:
    """Search GitHub for repositories and code patterns."""

    BASE_URL = "https://api.github.com"

    def __init__(
        self,
        token: str | None = None,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self._headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            self._headers["Authorization"] = f"token {token}"
        self._breaker = breaker

    async def _get_json(self, url: str, *, params: dict | None = None) -> dict | None:
        async def call() -> dict:
            async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
                resp = await client.get(url, params=params or {}, headers=self._headers)
                resp.raise_for_status()
                out = resp.json()
                if not isinstance(out, dict):
                    msg = "GitHub response JSON was not an object"
                    raise ValueError(msg)
                return out

        if self._breaker is None:
            try:
                return await call()
            except (httpx.HTTPError, ValueError) as e:
                logger.error("GitHub JSON request failed: %s", e)
                return None
        guarded = await circuit_breaker_http_guard(
            self._breaker,
            call,
            fallback=None,
            on_error=None,
        )
        return guarded if isinstance(guarded, dict) else None

    async def _get_text(self, url: str, *, timeout: float = 15.0) -> str | None:
        async def call() -> str:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.text

        if self._breaker is None:
            try:
                return await call()
            except httpx.HTTPError:
                return None
        out = await circuit_breaker_http_guard(
            self._breaker,
            call,
            fallback=None,
            on_error=None,
        )
        return out if isinstance(out, str) else None

    async def search_repos(
        self,
        query: str,
        *,
        sort: str = "stars",
        per_page: int = 10,
        language: str | None = None,
    ) -> list[RepoResult]:
        """Search GitHub repositories."""
        q = query
        if language:
            q += f" language:{language}"

        url = f"{self.BASE_URL}/search/repositories"
        params = {"q": q, "sort": sort, "order": "desc", "per_page": per_page}

        data = await self._get_json(url, params=params)
        if not data:
            return []

        results = []
        for item in data.get("items", []):
            results.append(RepoResult(
                name=item["name"],
                full_name=item["full_name"],
                url=item["html_url"],
                description=item.get("description", "") or "",
                stars=item.get("stargazers_count", 0),
                last_pushed=item.get("pushed_at", ""),
                language=item.get("language"),
                topics=item.get("topics", []),
                open_issues=item.get("open_issues_count", 0),
                license_name=(item.get("license") or {}).get("spdx_id"),
                readme_url=f"https://raw.githubusercontent.com/{item['full_name']}/main/README.md",
            ))

        return results

    async def get_readme(self, full_name: str) -> str | None:
        """Fetch a repo's README content (404 on wrong branch is expected — no breaker)."""
        for branch in ("main", "master"):
            url = f"https://raw.githubusercontent.com/{full_name}/{branch}/README.md"
            async with httpx.AsyncClient(timeout=15.0) as client:
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        return resp.text[:5000]
                except httpx.HTTPError:
                    continue
        return None

    async def search_code(
        self, query: str, *, language: str | None = None, per_page: int = 5
    ) -> list[dict]:
        """Search GitHub code for specific patterns."""
        q = query
        if language:
            q += f" language:{language}"

        url = f"{self.BASE_URL}/search/code"
        params = {"q": q, "per_page": per_page}

        data = await self._get_json(url, params=params)
        if not data:
            return []

        return [
            {
                "name": item["name"],
                "path": item["path"],
                "repo": item["repository"]["full_name"],
                "url": item["html_url"],
            }
            for item in data.get("items", [])
        ]


class ArxivSearcher:
    """Search arXiv for research papers."""

    BASE_URL = "https://export.arxiv.org/api/query"

    def __init__(self, breaker: CircuitBreaker | None = None) -> None:
        self._breaker = breaker

    async def search(
        self, query: str, *, max_results: int = 10, sort_by: str = "submittedDate"
    ) -> list[PaperResult]:
        """Search arXiv papers."""
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": max_results,
            "sortBy": sort_by,
            "sortOrder": "descending",
        }

        async def call() -> str:
            async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
                resp = await client.get(self.BASE_URL, params=params)
                resp.raise_for_status()
                return resp.text

        if self._breaker is None:
            try:
                xml_content = await call()
            except httpx.HTTPError as e:
                logger.error("arXiv search failed: %s", e)
                return []
        else:
            xml_content = await circuit_breaker_http_guard(
                self._breaker,
                call,
                fallback=None,
                on_error=None,
            )
            if not isinstance(xml_content, str):
                return []

        return self._parse_atom_feed(xml_content)

    def _parse_atom_feed(self, xml_content: str) -> list[PaperResult]:
        """Parse arXiv Atom XML feed."""
        import xml.etree.ElementTree as ET

        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
        results = []

        try:
            root = ET.fromstring(xml_content)
            for entry in root.findall("atom:entry", ns):
                title = (entry.findtext("atom:title", "", ns) or "").strip().replace("\n", " ")
                abstract = (entry.findtext("atom:summary", "", ns) or "").strip()[:500]
                published = entry.findtext("atom:published", "", ns) or ""
                arxiv_id = (entry.findtext("atom:id", "", ns) or "").split("/abs/")[-1]

                authors = []
                for author in entry.findall("atom:author", ns):
                    name = author.findtext("atom:name", "", ns)
                    if name:
                        authors.append(name)

                categories = []
                for cat in entry.findall("atom:category", ns):
                    term = cat.get("term", "")
                    if term:
                        categories.append(term)

                links = entry.findall("atom:link", ns)
                url = ""
                for link in links:
                    if link.get("type") == "text/html":
                        url = link.get("href", "")
                        break
                if not url:
                    url = f"https://arxiv.org/abs/{arxiv_id}"

                results.append(PaperResult(
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    url=url,
                    published=published[:10],
                    categories=categories,
                ))
        except ET.ParseError:
            logger.error("Failed to parse arXiv XML feed")

        return results


class PackageSearcher:
    """Search PyPI and NPM for packages."""

    def __init__(
        self,
        *,
        pypi_breaker: CircuitBreaker | None = None,
        npm_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._pypi_breaker = pypi_breaker
        self._npm_breaker = npm_breaker

    async def _pypi_json(self, url: str) -> dict | None:
        async def call() -> dict:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    msg = f"PyPI status {resp.status_code}"
                    raise httpx.HTTPStatusError(msg, request=resp.request, response=resp)
                out = resp.json()
                if not isinstance(out, dict):
                    msg = "PyPI JSON not object"
                    raise ValueError(msg)
                return out

        if self._pypi_breaker is None:
            try:
                return await call()
            except (httpx.HTTPError, ValueError):
                return None
        out = await circuit_breaker_http_guard(
            self._pypi_breaker,
            call,
            fallback=None,
            on_error=None,
        )
        return out if isinstance(out, dict) else None

    async def _npm_json(self, url: str) -> dict | None:
        async def call() -> dict:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    msg = f"npm status {resp.status_code}"
                    raise httpx.HTTPStatusError(msg, request=resp.request, response=resp)
                out = resp.json()
                if not isinstance(out, dict):
                    msg = "npm JSON not object"
                    raise ValueError(msg)
                return out

        if self._npm_breaker is None:
            try:
                return await call()
            except (httpx.HTTPError, ValueError):
                return None
        out = await circuit_breaker_http_guard(
            self._npm_breaker,
            call,
            fallback=None,
            on_error=None,
        )
        return out if isinstance(out, dict) else None

    async def search_pypi(self, package_name: str) -> dict | None:
        """Get PyPI package info."""
        url = f"https://pypi.org/pypi/{package_name}/json"
        data = await self._pypi_json(url)
        if not data:
            return None
        info = data.get("info", {})
        return {
            "name": info.get("name"),
            "version": info.get("version"),
            "summary": info.get("summary"),
            "requires_python": info.get("requires_python"),
            "license": info.get("license"),
            "home_page": info.get("home_page"),
            "project_url": info.get("project_url"),
        }

    async def search_npm(self, package_name: str) -> dict | None:
        """Get NPM package info."""
        url = f"https://registry.npmjs.org/{package_name}"
        data = await self._npm_json(url)
        if not data:
            return None
        latest = data.get("dist-tags", {}).get("latest", "")
        return {
            "name": data.get("name"),
            "version": latest,
            "description": data.get("description"),
            "license": data.get("license"),
            "modified": data.get("time", {}).get("modified"),
        }


class DuckDuckGoWebSearcher:
    """DuckDuckGo instant answer API (no browser, no API key)."""

    BASE_URL = "https://api.duckduckgo.com/"

    def __init__(self, breaker: CircuitBreaker | None = None) -> None:
        self._breaker = breaker

    async def instant_summary(self, query: str) -> list[str]:
        params = {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}

        async def call() -> dict:
            async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
                resp = await client.get(self.BASE_URL, params=params)
                resp.raise_for_status()
                out = resp.json()
                if not isinstance(out, dict):
                    msg = "DuckDuckGo JSON not object"
                    raise ValueError(msg)
                return out

        if self._breaker is None:
            try:
                data = await call()
            except (httpx.HTTPError, ValueError) as e:
                logger.debug("DuckDuckGo instant failed: %s", e)
                return []
        else:
            data = await circuit_breaker_http_guard(
                self._breaker,
                call,
                fallback=None,
                on_error=None,
            )
            if not isinstance(data, dict):
                return []

        snippets: list[str] = []
        abstract = (data.get("AbstractText") or "").strip()
        if abstract:
            snippets.append(abstract[:1200])
        for topic in data.get("RelatedTopics", [])[:5]:
            if isinstance(topic, dict) and topic.get("Text"):
                snippets.append(str(topic["Text"])[:400])
        return snippets


class SemanticScholarSearcher:
    """Semantic Scholar Graph API (public, rate-limited)."""

    BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"

    def __init__(self, breaker: CircuitBreaker | None = None) -> None:
        self._breaker = breaker

    async def search_titles(self, query: str, *, limit: int = 5) -> list[str]:
        params = {
            "query": query,
            "limit": limit,
            "fields": "title,url",
        }

        async def call() -> dict:
            async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
                resp = await client.get(self.BASE_URL, params=params)
                resp.raise_for_status()
                out = resp.json()
                if not isinstance(out, dict):
                    msg = "Semantic Scholar JSON not object"
                    raise ValueError(msg)
                return out

        if self._breaker is None:
            try:
                data = await call()
            except (httpx.HTTPError, ValueError) as e:
                logger.debug("Semantic Scholar search failed: %s", e)
                return []
        else:
            data = await circuit_breaker_http_guard(
                self._breaker,
                call,
                fallback=None,
                on_error=None,
            )
            if not isinstance(data, dict):
                return []

        hits: list[str] = []
        for item in data.get("data", [])[:limit]:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()
            if title and url:
                hits.append(f"{title} — {url}")
            elif title:
                hits.append(title)
        return hits


class ResearchSweep:
    """Orchestrates a full research sweep across all sources."""

    def __init__(
        self,
        scope: str = "full",
        github_token: str | None = None,
        *,
        breakers: dict[str, CircuitBreaker] | None = None,
    ) -> None:
        self.scope = scope
        b = breakers or {}
        self._breakers = {
            "github": b.get("github") or CircuitBreaker("github_api"),
            "arxiv": b.get("arxiv") or CircuitBreaker("arxiv_api"),
            "pypi": b.get("pypi") or CircuitBreaker("pypi_api"),
            "npm": b.get("npm") or CircuitBreaker("npm_registry"),
            "duckduckgo": b.get("duckduckgo") or CircuitBreaker("duckduckgo_instant"),
            "semantic_scholar": b.get("semantic_scholar") or CircuitBreaker("semantic_scholar_api"),
        }
        self.github = GitHubSearcher(
            token=github_token,
            breaker=self._breakers["github"],
        )
        self.arxiv = ArxivSearcher(breaker=self._breakers["arxiv"])
        self.packages = PackageSearcher(
            pypi_breaker=self._breakers["pypi"],
            npm_breaker=self._breakers["npm"],
        )
        self.duckduckgo = DuckDuckGoWebSearcher(breaker=self._breakers["duckduckgo"])
        self.semantic_scholar = SemanticScholarSearcher(
            breaker=self._breakers["semantic_scholar"],
        )

    async def run(self, query: str = "AI agent competition tournament") -> ResearchReport:
        """Run a full research sweep."""
        report = ResearchReport(query=query)

        tasks = []

        if self.scope in ("full", "competitors"):
            tasks.append(self._search_github(report, query))

        if self.scope in ("full", "papers"):
            tasks.append(self._search_arxiv(report, query))

        if self.scope in ("full", "tools"):
            tasks.append(self._search_packages(report))

        if self.scope == "full":
            tasks.append(self._search_web(report, query))
            tasks.append(self._search_semantic_scholar(report, query))

        await asyncio.gather(*tasks, return_exceptions=True)

        # Generate insights
        report.insights = self._generate_insights(report)

        logger.info(
            "Research sweep complete: %d repos, %d papers, %d web, %d s2, %d insights",
            len(report.repos),
            len(report.papers),
            len(report.web_instant_snippets),
            len(report.scholar_hits),
            len(report.insights),
        )

        return report

    async def _search_github(self, report: ResearchReport, query: str) -> None:
        """Search GitHub for relevant repos."""
        searches = [
            f"{query} production",
            "multi-agent coding competition",
            "AI agent tournament platform",
        ]
        for q in searches:
            repos = await self.github.search_repos(q, per_page=5)
            report.repos.extend(repos)

    async def _search_arxiv(self, report: ResearchReport, query: str) -> None:
        """Search arXiv for relevant papers."""
        searches = [
            "multi-agent collaboration competition",
            "LLM coding agent evaluation",
            "agent arena benchmark",
        ]
        for q in searches:
            papers = await self.arxiv.search(q, max_results=5)
            report.papers.extend(papers)

    async def _search_packages(self, report: ResearchReport) -> None:
        """Search for relevant packages."""
        packages = ["litellm", "langfuse", "autogen", "crewai", "langgraph"]
        for pkg in packages:
            info = await self.packages.search_pypi(pkg)
            if info:
                report.packages_found.append(info)

    async def _search_web(self, report: ResearchReport, query: str) -> None:
        """DuckDuckGo instant answers (circuit-broken)."""
        snippets = await self.duckduckgo.instant_summary(query)
        report.web_instant_snippets.extend(snippets)

    async def _search_semantic_scholar(self, report: ResearchReport, query: str) -> None:
        """Semantic Scholar paper titles (circuit-broken)."""
        hits = await self.semantic_scholar.search_titles(query, limit=5)
        report.scholar_hits.extend(hits)

    def _generate_insights(self, report: ResearchReport) -> list[str]:
        """Generate actionable insights from research."""
        insights = []

        # Repo insights
        high_star_repos = [r for r in report.repos if r.stars > 500]
        if high_star_repos:
            insights.append(
                f"Found {len(high_star_repos)} high-star repos (>500⭐) — "
                f"review for architecture patterns"
            )

        # Paper insights
        recent_papers = [p for p in report.papers if "2026" in p.published or "2025" in p.published]
        if recent_papers:
            insights.append(
                f"Found {len(recent_papers)} recent papers (2025-2026) — "
                f"check for new techniques"
            )

        # Package insights
        if report.packages_found:
            insights.append(
                f"Verified {len(report.packages_found)} key packages are available on PyPI"
            )

        if report.web_instant_snippets:
            insights.append(
                f"Collected {len(report.web_instant_snippets)} DuckDuckGo instant snippets"
            )

        if report.scholar_hits:
            insights.append(
                f"Semantic Scholar returned {len(report.scholar_hits)} paper hits"
            )

        return insights
