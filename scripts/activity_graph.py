#!/usr/bin/env python3
"""Render the last N weeks of GitHub contributions as a themed SVG area chart.

Standard library only. Reads GITHUB_TOKEN from the environment.

    python3 scripts/activity_graph.py <username> <output.svg> [weeks]
"""

import datetime as dt
import json
import os
import sys
import urllib.request

BG = "#0d1117"
BORDER = "#2d2a55"
TITLE = "#a78bfa"
MUTED = "#8b949e"
GRID = "#21262d"
LINE = "#8b5cf6"
POINT = "#c4b5fd"
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Sans-Serif"

WIDTH, HEIGHT = 1000, 340
LEFT, RIGHT, TOP, BOTTOM = 58, 30, 74, 46

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def fetch_weeks(login, weeks, token):
    """Return [(week_start_date, contributions)] for the last `weeks` calendar weeks."""
    today = dt.datetime.now(dt.timezone.utc).date()
    start = today - dt.timedelta(days=7 * weeks)
    variables = {
        "login": login,
        "from": f"{start.isoformat()}T00:00:00Z",
        "to": f"{today.isoformat()}T23:59:59Z",
    }
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "profile-activity-graph",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("errors") or not payload.get("data", {}).get("user"):
        raise SystemExit(f"GitHub API error: {payload.get('errors') or 'user not found'}")

    calendar = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    totals = [
        (
            dt.date.fromisoformat(week["contributionDays"][0]["date"]),
            sum(day["contributionCount"] for day in week["contributionDays"]),
        )
        for week in calendar["weeks"]
    ]
    return totals[-weeks:]


def nice_ceiling(value):
    """Smallest round axis maximum that clears `value` and splits into 4 whole steps."""
    step = 1
    while True:
        for factor in (1, 2, 3, 5):
            if 4 * factor * step >= value * 1.08:
                return 4 * factor * step
        step *= 10


def monotone_path(points):
    """Cubic Bezier path through points that never overshoots (Fritsch-Carlson)."""
    n = len(points)
    if n < 3:
        return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in points)

    dx = [points[i + 1][0] - points[i][0] for i in range(n - 1)]
    slope = [(points[i + 1][1] - points[i][1]) / dx[i] for i in range(n - 1)]
    tangent = [slope[0]] + [0.0] * (n - 2) + [slope[-1]]
    for i in range(1, n - 1):
        if slope[i - 1] * slope[i] > 0:
            tangent[i] = (
                3 * (dx[i - 1] + dx[i])
                / ((2 * dx[i] + dx[i - 1]) / slope[i - 1] + (dx[i] + 2 * dx[i - 1]) / slope[i])
            )

    path = [f"M{points[0][0]:.1f},{points[0][1]:.1f}"]
    for i in range(n - 1):
        x0, y0 = points[i]
        x1, y1 = points[i + 1]
        path.append(
            f"C{x0 + dx[i] / 3:.1f},{y0 + tangent[i] * dx[i] / 3:.1f} "
            f"{x1 - dx[i] / 3:.1f},{y1 - tangent[i + 1] * dx[i] / 3:.1f} "
            f"{x1:.1f},{y1:.1f}"
        )
    return " ".join(path)


def render(weeks):
    days = weeks
    total = sum(count for _, count in days)
    top = nice_ceiling(max(count for _, count in days))
    plot_w = WIDTH - LEFT - RIGHT
    plot_h = HEIGHT - TOP - BOTTOM
    floor_y = TOP + plot_h

    def x_at(index):
        return LEFT + plot_w * index / (len(days) - 1)

    def y_at(count):
        return floor_y - plot_h * count / top

    points = [(x_at(i), y_at(count)) for i, (_, count) in enumerate(days)]
    line = monotone_path(points)
    area = f"{line} L{points[-1][0]:.1f},{floor_y:.1f} L{points[0][0]:.1f},{floor_y:.1f} Z"

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" '
        f'aria-label="Contribution activity, last {len(days)} weeks: {total} contributions">',
        "<defs>",
        '<linearGradient id="area" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{LINE}" stop-opacity="0.42"/>'
        f'<stop offset="1" stop-color="{LINE}" stop-opacity="0"/></linearGradient>',
        '<linearGradient id="stroke" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0" stop-color="#6366f1"/><stop offset="0.5" stop-color="#8b5cf6"/>'
        '<stop offset="1" stop-color="#c084fc"/></linearGradient>',
        "</defs>",
        "<style>"
        f"text{{font-family:{FONT}}}"
        ".line{stroke-dasharray:1;stroke-dashoffset:1;animation:draw 2.4s ease-out forwards}"
        ".fade{opacity:0;animation:fade .9s ease-out 1.5s forwards}"
        "@keyframes draw{to{stroke-dashoffset:0}}@keyframes fade{to{opacity:1}}"
        "</style>",
        f'<rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{HEIGHT - 1}" rx="8" '
        f'fill="{BG}" stroke="{BORDER}"/>',
        f'<text x="{LEFT - 30}" y="38" fill="{TITLE}" font-size="18" font-weight="600">'
        "Contribution Activity</text>",
        f'<text x="{WIDTH - RIGHT}" y="38" fill="{MUTED}" font-size="12.5" text-anchor="end">'
        f"Weekly contributions · last {len(days)} weeks · {total:,} total</text>",
    ]

    for step in range(5):
        value = top * step / 4
        y = y_at(value)
        dash = "" if step == 0 else ' stroke-dasharray="3 5"'
        out.append(
            f'<line x1="{LEFT}" y1="{y:.1f}" x2="{WIDTH - RIGHT}" y2="{y:.1f}" '
            f'stroke="{GRID}"{dash}/>'
        )
        out.append(
            f'<text x="{LEFT - 12}" y="{y + 4:.1f}" fill="{MUTED}" font-size="11.5" '
            f'text-anchor="end">{value:g}</text>'
        )

    label_every = max(1, round(len(days) / 9))
    for i, (date, _) in enumerate(days):
        if (len(days) - 1 - i) % label_every == 0:
            out.append(
                f'<text x="{x_at(i):.1f}" y="{floor_y + 22}" fill="{MUTED}" font-size="11.5" '
                f'text-anchor="middle">{date.day} {date.strftime("%b")}</text>'
            )

    out.append(f'<path class="fade" d="{area}" fill="url(#area)"/>')
    out.append(
        f'<path class="line" d="{line}" pathLength="1" fill="none" stroke="url(#stroke)" '
        'stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>'
    )
    out.append('<g class="fade">')
    for (x, y), (_, count) in zip(points, days):
        if count:
            out.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="{BG}" stroke="{POINT}" '
                'stroke-width="1.8"/>'
            )
    out.append("</g></svg>")
    return "\n".join(out) + "\n"


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    login, output = sys.argv[1], sys.argv[2]
    weeks = int(sys.argv[3]) if len(sys.argv) > 3 else 26
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is not set")

    svg = render(fetch_weeks(login, weeks, token))
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    with open(output, "w", encoding="utf-8") as handle:
        handle.write(svg)
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
