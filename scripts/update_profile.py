"""Render daily GitHub profile statistics into the profile SVG banners."""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as etree
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATHS = (ROOT / "dark.svg", ROOT / "light.svg")
TEMPLATE_PATHS = (ROOT / "dark.template.svg", ROOT / "light.template.svg")
TOKEN_NAMES = ("REPOS", "STARS", "COMMITS_YEAR", "FOLLOWERS", "LOC")
SOURCE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".c",
    ".h", ".cpp", ".cs", ".html", ".css", ".scss", ".sql", ".yml", ".yaml", ".sh",
}
EXCLUDED_PARTS = {
    ".git", "node_modules", "vendor", "dist", "build", ".next", "coverage", "__pycache__",
}
GRAPHQL_URL = "https://api.github.com/graphql"
QUERY = """
query ($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    followers { totalCount }
    repositories(first: 100, privacy: PUBLIC, ownerAffiliations: OWNER, isFork: false) {
      totalCount
      nodes { nameWithOwner stargazerCount defaultBranchRef { name } }
    }
    contributionsCollection(from: $from, to: $to) { totalCommitContributions }
  }
}
"""


def count_source_lines(root: Path) -> int:
    """Count non-empty lines in supported source files below *root*."""
    total = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SOURCE_EXTENSIONS:
            continue
        if any(part.casefold() in EXCLUDED_PARTS for part in path.parts):
            continue
        try:
            with path.open("r", encoding="utf-8", errors="strict") as source:
                total += sum(1 for line in source if line.strip())
        except UnicodeDecodeError:
            continue
    return total


def render_svg(svg: str, values: dict[str, str]) -> str:
    """Replace all required stats tokens and reject malformed SVG templates."""
    rendered = svg
    for name in TOKEN_NAMES:
        token = "{{" + name + "}}"
        if token not in rendered:
            raise ValueError(f"SVG template is missing {token}")
        rendered = rendered.replace(token, values[name])
    return rendered


def graphql_request(token: str, variables: dict[str, str]) -> dict:
    body = json.dumps({"query": QUERY, "variables": variables}).encode("utf-8")
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "tab11pm-profile-updater",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.URLError as error:
        raise RuntimeError("GitHub GraphQL request failed") from error
    if payload.get("errors"):
        raise RuntimeError("GitHub GraphQL returned errors")
    return payload["data"]


def fetch_profile_stats(token: str, login: str) -> tuple[dict[str, int], list[dict]]:
    now = dt.datetime.now(dt.timezone.utc)
    year_start = dt.datetime(now.year, 1, 1, tzinfo=dt.timezone.utc)
    data = graphql_request(
        token,
        {"login": login, "from": year_start.isoformat(), "to": now.isoformat()},
    )
    user = data.get("user")
    if not user:
        raise RuntimeError(f"GitHub user {login!r} was not found")
    repositories = user["repositories"]
    return (
        {
            "REPOS": repositories["totalCount"],
            "STARS": sum(node["stargazerCount"] for node in repositories["nodes"]),
            "COMMITS_YEAR": user["contributionsCollection"]["totalCommitContributions"],
            "FOLLOWERS": user["followers"]["totalCount"],
        },
        repositories["nodes"],
    )


def collect_line_count(repositories: list[dict], work_dir: Path) -> int:
    """Shallow-clone each default branch and count its configured source lines."""
    total = 0
    for index, repository in enumerate(repositories):
        branch = repository.get("defaultBranchRef")
        if not branch:
            continue
        destination = work_dir / f"repo-{index}"
        command = [
            "git", "clone", "--depth=1", "--single-branch", "--branch", branch["name"],
            f"https://github.com/{repository['nameWithOwner']}.git", str(destination),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"Could not clone {repository['nameWithOwner']}")
        total += count_source_lines(destination)
    return total


def atomic_write(path: Path, content: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required")
    login = os.environ.get("PROFILE_LOGIN", "tab11pm")
    templates = {
        output: template.read_text(encoding="utf-8")
        for output, template in zip(OUTPUT_PATHS, TEMPLATE_PATHS, strict=True)
    }
    metrics, repositories = fetch_profile_stats(token, login)
    with tempfile.TemporaryDirectory(prefix="profile-stats-") as directory:
        metrics["LOC"] = collect_line_count(repositories, Path(directory))
    values = {name: f"{value:,}" for name, value in metrics.items()}
    rendered = {path: render_svg(template, values) for path, template in templates.items()}
    for content in rendered.values():
        etree.fromstring(content)
    for path, content in rendered.items():
        atomic_write(path, content)


if __name__ == "__main__":
    main()
