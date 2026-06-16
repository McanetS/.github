#!/usr/bin/env python3
"""
Updates profile/README.md with live org stats from the GitHub API.
Requires: GITHUB_TOKEN env var with repo scope on McanetS org.
"""
import os
import re
import requests
from datetime import datetime, timedelta, timezone
from collections import defaultdict

ORG = "McanetS"
SKIP_REPOS = {".github", "mcaconnectbot-releases"}
TOP_REPOS = 8
TOP_CONTRIBUTORS = 8
LOOKBACK_DAYS = 30

TOKEN = os.environ["GITHUB_TOKEN"]
HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}


def paginate(url, params=None):
    params = params or {}
    results = []
    page = 1
    while True:
        r = requests.get(url, headers=HEADERS, params={**params, "page": page, "per_page": 100})
        if r.status_code != 200:
            break
        data = r.json()
        if not data:
            break
        results.extend(data)
        if len(data) < 100:
            break
        page += 1
    return results


def get_repos():
    repos = paginate(f"https://api.github.com/orgs/{ORG}/repos", {"sort": "pushed"})
    return [r for r in repos if r["name"] not in SKIP_REPOS]


def get_recent_commits(repos, since_iso):
    commits_by_user = defaultdict(int)
    for repo in repos[:20]:
        r = requests.get(
            f"https://api.github.com/repos/{ORG}/{repo['name']}/commits",
            headers=HEADERS,
            params={"since": since_iso, "per_page": 100},
        )
        if r.status_code != 200:
            continue
        for commit in r.json():
            author = commit.get("author")
            if author and author.get("login"):
                commits_by_user[author["login"]] += 1
    return commits_by_user


def get_members():
    members = paginate(f"https://api.github.com/orgs/{ORG}/members")
    return {m["login"]: m["avatar_url"] for m in members}


def build_repos_section(repos):
    LANG_ICONS = {
        "JavaScript": "🟨", "TypeScript": "🔷", "PHP": "🐘",
        "Python": "🐍", "C": "⚙️", "C++": "⚙️", "Kotlin": "🟣",
        "Shell": "🐚", "Perl": "🦪", "HTML": "🌐",
    }
    lines = ["| Repositorio | Descripción | Lenguaje | Última actividad |"]
    lines.append("|-------------|-------------|----------|:----------------:|")
    for repo in repos[:TOP_REPOS]:
        name = repo["name"]
        desc = (repo.get("description") or "—")[:55]
        lang = repo.get("language") or "—"
        icon = LANG_ICONS.get(lang, "")
        pushed = (repo.get("pushed_at") or "")[:10] or "—"
        lines.append(f"| **{name}** | {desc} | {icon} `{lang}` | {pushed} |")
    return "\n".join(lines) + "\n"


def build_contributors_section(commits_by_user, members):
    if not commits_by_user:
        return "_Sin actividad registrada en los últimos 30 días._\n"

    MEDALS = ["🥇", "🥈", "🥉"]
    ranked = sorted(commits_by_user.items(), key=lambda x: x[1], reverse=True)[:TOP_CONTRIBUTORS]

    lines = ["| # | Usuario | Commits (30d) |"]
    lines.append("|:-:|---------|:-------------:|")
    for i, (login, count) in enumerate(ranked):
        medal = MEDALS[i] if i < 3 else f"`{i+1}`"
        avatar = members.get(login, "")
        img = f'<img src="{avatar}&s=20" width="20" height="20" style="border-radius:50%"> ' if avatar else ""
        lines.append(f"| {medal} | {img}[@{login}](https://github.com/{login}) | **{count}** |")
    return "\n".join(lines) + "\n"


def replace_section(content, tag, new_body):
    pattern = rf"<!-- {tag}-START -->.*?<!-- {tag}-END -->"
    replacement = f"<!-- {tag}-START -->\n{new_body}<!-- {tag}-END -->"
    return re.sub(pattern, replacement, content, flags=re.DOTALL)


def main():
    print("Fetching repos...")
    repos = get_repos()
    repos.sort(key=lambda r: r.get("pushed_at") or "", reverse=True)

    since = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).isoformat()
    print("Fetching recent commits...")
    commits_by_user = get_recent_commits(repos, since)

    print("Fetching members...")
    members = get_members()

    repos_section = build_repos_section(repos)
    contributors_section = build_contributors_section(commits_by_user, members)

    readme_path = "profile/README.md"
    with open(readme_path) as f:
        content = f.read()

    content = replace_section(content, "REPOS", repos_section)
    content = replace_section(content, "CONTRIBUTORS", contributors_section)

    with open(readme_path, "w") as f:
        f.write(content)

    print(f"README updated. Top repos: {len(repos[:TOP_REPOS])}, contributors: {len(commits_by_user)}")


if __name__ == "__main__":
    main()
