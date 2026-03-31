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

logger = logging.getLogger(__name__)


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
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def sources_found(self) -> int:
        return len(self.repos) + len(self.papers) + len(self.packages_found)

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

    def __init__(self, token: str | None = None) -> None:
        self._headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            self._headers["Authorization"] = f"token {token}"

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

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.get(url, params=params, headers=self._headers)
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPError as e:
                logger.error("GitHub search failed: %s", e)
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
        """Fetch a repo's README content."""
        for branch in ("main", "master"):
            url = f"https://raw.githubusercontent.com/{full_name}/{branch}/README.md"
            async with httpx.AsyncClient(timeout=15) as client:
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        return resp.text[:5000]  # Limit to 5000 chars
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

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.get(url, params=params, headers=self._headers)
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPError as e:
                logger.error("GitHub code search failed: %s", e)
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

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.get(self.BASE_URL, params=params)
                resp.raise_for_status()
                xml_content = resp.text
            except httpx.HTTPError as e:
                logger.error("arXiv search failed: %s", e)
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

    async def search_pypi(self, package_name: str) -> dict | None:
        """Get PyPI package info."""
        url = f"https://pypi.org/pypi/{package_name}/json"
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return None
                data = resp.json()
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
            except httpx.HTTPError:
                return None

    async def search_npm(self, package_name: str) -> dict | None:
        """Get NPM package info."""
        url = f"https://registry.npmjs.org/{package_name}"
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return None
                data = resp.json()
                latest = data.get("dist-tags", {}).get("latest", "")
                return {
                    "name": data.get("name"),
                    "version": latest,
                    "description": data.get("description"),
                    "license": data.get("license"),
                    "modified": data.get("time", {}).get("modified"),
                }
            except httpx.HTTPError:
                return None


class ResearchSweep:
    """Orchestrates a full research sweep across all sources."""

    def __init__(
        self,
        scope: str = "full",
        github_token: str | None = None,
    ) -> None:
        self.scope = scope
        self.github = GitHubSearcher(token=github_token)
        self.arxiv = ArxivSearcher()
        self.packages = PackageSearcher()

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

        await asyncio.gather(*tasks, return_exceptions=True)

        # Generate insights
        report.insights = self._generate_insights(report)

        logger.info(
            "Research sweep complete: %d repos, %d papers, %d insights",
            len(report.repos), len(report.papers), len(report.insights),
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

        return insights
