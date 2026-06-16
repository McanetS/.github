#!/usr/bin/env python3
"""
Updates profile/README.md with live org stats and generates a contribution heatmap SVG.
Requires: GITHUB_TOKEN env var with repo scope on McanetS org.
"""
import os
import re
import requests
from datetime import date, timedelta
from collections import defaultdict

ORG = "McanetS"
SKIP_REPOS = {".github", "mcaconnectbot-releases"}
TOP_REPOS = 8
TOP_CONTRIBUTORS = 8
LOOKBACK_DAYS = 30
HEATMAP_WEEKS = 52

TOKEN = os.environ["GITHUB_TOKEN"]
HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}


# ── API helpers ────────────────────────────────────────────────────────────────

def paginate(url, params=None):
    results, page = [], 1
    while True:
        r = requests.get(url, headers=HEADERS, params={**(params or {}), "page": page, "per_page": 100})
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


def get_commits_since(repos, since_iso, max_repos=20):
    """Returns (commits_by_user, commits_by_date) for the given period."""
    by_user = defaultdict(int)
    by_date = defaultdict(int)
    for repo in repos[:max_repos]:
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
                by_user[author["login"]] += 1
            # date from commit metadata
            committed_at = (
                commit.get("commit", {})
                      .get("committer", {})
                      .get("date", "")
            )
            if committed_at:
                by_date[committed_at[:10]] += 1
    return by_user, by_date


def get_members():
    members = paginate(f"https://api.github.com/orgs/{ORG}/members")
    return {m["login"]: m["avatar_url"] for m in members}


# ── SVG heatmap ───────────────────────────────────────────────────────────────

COLORS = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]

def commit_color(n):
    if n == 0:   return COLORS[0]
    if n <= 3:   return COLORS[1]
    if n <= 6:   return COLORS[2]
    if n <= 9:   return COLORS[3]
    return COLORS[4]


def generate_heatmap_svg(commits_by_date: dict) -> str:
    today = date.today()
    # Align start to the Sunday 52 weeks back
    raw_start = today - timedelta(weeks=HEATMAP_WEEKS)
    start = raw_start - timedelta(days=raw_start.isoweekday() % 7)  # back to Sunday

    CELL, GAP = 11, 2
    STEP = CELL + GAP
    LEFT = 28   # space for day labels
    TOP  = 18   # space for month labels

    cells, month_labels = [], []
    col, prev_month = 0, None
    cur = start

    while cur <= today:
        dow = cur.isoweekday() % 7   # Sun=0 … Sat=6

        if dow == 0:
            if cur.month != prev_month:
                month_labels.append((col, cur.strftime("%b")))
                prev_month = cur.month

        count = commits_by_date.get(cur.isoformat(), 0)
        x = LEFT + col * STEP
        y = TOP  + dow * STEP
        tip = f"{count} commit{'s' if count != 1 else ''} · {cur.strftime('%d %b %Y')}"
        cells.append(
            f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" '
            f'fill="{commit_color(count)}"><title>{tip}</title></rect>'
        )

        cur += timedelta(days=1)
        if dow == 6:
            col += 1

    W = LEFT + col * STEP + CELL + 6
    H = TOP  + 7 * STEP + 4

    day_labels = "\n  ".join(
        f'<text x="{LEFT - 4}" y="{TOP + i * STEP + CELL - 1}" '
        f'text-anchor="end" font-size="9" fill="#8b949e">{lbl}</text>'
        for i, lbl in enumerate(["", "Mon", "", "Wed", "", "Fri", ""])
        if lbl
    )
    month_svgs = "\n  ".join(
        f'<text x="{LEFT + c * STEP}" y="{TOP - 4}" font-size="9" fill="#8b949e">{m}</text>'
        for c, m in month_labels
    )

    total = sum(commits_by_date.values())
    subtitle = f"Total: {total} commits en el último año · MCAnet S.A."

    return f"""\
<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H + 18}"
     viewBox="0 0 {W} {H + 18}" style="background:#0d1117;border-radius:6px">
  <text x="{LEFT}" y="{H + 13}" font-size="10" fill="#8b949e">{subtitle}</text>
  {month_svgs}
  {day_labels}
  {"  ".join(cells)}
</svg>"""


# ── README sections ────────────────────────────────────────────────────────────

LANG_ICONS = {
    "JavaScript": "🟨", "TypeScript": "🔷", "PHP": "🐘",
    "Python": "🐍", "C": "⚙️", "C++": "⚙️", "Kotlin": "🟣",
    "Shell": "🐚", "Perl": "🦪", "HTML": "🌐",
}

def build_repos_section(repos):
    lines = [
        "| Repositorio | Descripción | Lenguaje | Última actividad |",
        "|-------------|-------------|----------|:----------------:|",
    ]
    for repo in repos[:TOP_REPOS]:
        name  = repo["name"]
        desc  = (repo.get("description") or "—")[:55]
        lang  = repo.get("language") or "—"
        icon  = LANG_ICONS.get(lang, "")
        pushed = (repo.get("pushed_at") or "")[:10] or "—"
        lines.append(f"| **{name}** | {desc} | {icon} `{lang}` | {pushed} |")
    return "\n".join(lines) + "\n"


def build_contributors_section(commits_by_user, members):
    if not commits_by_user:
        return "_Sin actividad registrada en los últimos 30 días._\n"
    MEDALS = ["🥇", "🥈", "🥉"]
    ranked = sorted(commits_by_user.items(), key=lambda x: x[1], reverse=True)[:TOP_CONTRIBUTORS]
    lines = ["| # | Usuario | Commits (30d) |", "|:-:|---------|:-------------:|"]
    for i, (login, count) in enumerate(ranked):
        medal  = MEDALS[i] if i < 3 else f"`{i+1}`"
        avatar = members.get(login, "")
        img    = f'<img src="{avatar}&s=20" width="20" height="20" style="border-radius:50%"> ' if avatar else ""
        lines.append(f"| {medal} | {img}[@{login}](https://github.com/{login}) | **{count}** |")
    return "\n".join(lines) + "\n"


def replace_section(content, tag, new_body):
    return re.sub(
        rf"<!-- {tag}-START -->.*?<!-- {tag}-END -->",
        f"<!-- {tag}-START -->\n{new_body}<!-- {tag}-END -->",
        content,
        flags=re.DOTALL,
    )


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("Fetching repos...")
    repos = get_repos()
    repos.sort(key=lambda r: r.get("pushed_at") or "", reverse=True)

    since_30d  = (date.today() - timedelta(days=30)).isoformat() + "T00:00:00Z"
    since_year = (date.today() - timedelta(weeks=HEATMAP_WEEKS)).isoformat() + "T00:00:00Z"

    print("Fetching commits (30d for ranking)...")
    commits_by_user, _ = get_commits_since(repos, since_30d, max_repos=20)

    print("Fetching commits (1 year for heatmap)...")
    _, commits_by_date  = get_commits_since(repos, since_year, max_repos=30)

    print("Fetching members...")
    members = get_members()

    print("Generating heatmap SVG...")
    svg = generate_heatmap_svg(commits_by_date)
    svg_path = "profile/assets/contribution-graph.svg"
    os.makedirs(os.path.dirname(svg_path), exist_ok=True)
    with open(svg_path, "w") as f:
        f.write(svg)

    print("Updating README...")
    with open("profile/README.md") as f:
        content = f.read()

    content = replace_section(content, "REPOS",        build_repos_section(repos))
    content = replace_section(content, "CONTRIBUTORS", build_contributors_section(commits_by_user, members))

    with open("profile/README.md", "w") as f:
        f.write(content)

    total = sum(commits_by_date.values())
    print(f"Done — {total} commits en el año, {len(commits_by_user)} contribuidores activos.")


if __name__ == "__main__":
    main()
