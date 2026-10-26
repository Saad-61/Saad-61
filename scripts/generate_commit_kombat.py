#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence

GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"


@dataclass(frozen=True)
class Theme:
    name: str
    background: str
    panel: str
    title: str
    subtitle: str
    grid_empty: str
    grid_levels: Sequence[str]
    left_fighter: str
    right_fighter: str
    left_health: str
    right_health: str
    combo_fill: str
    combo_track: str
    impact: str
    special: str
    border: str


THEMES: Dict[str, Theme] = {
    "light": Theme(
        name="light",
        background="#f8fafc",
        panel="#ffffff",
        title="#0f172a",
        subtitle="#334155",
        grid_empty="#ebedf0",
        grid_levels=("#9be9a8", "#40c463", "#30a14e", "#216e39"),
        left_fighter="#2563eb",
        right_fighter="#dc2626",
        left_health="#16a34a",
        right_health="#eab308",
        combo_fill="#7c3aed",
        combo_track="#dbeafe",
        impact="#f97316",
        special="#be123c",
        border="#cbd5e1",
    ),
    "dark": Theme(
        name="dark",
        background="#0d1117",
        panel="#161b22",
        title="#e6edf3",
        subtitle="#8b949e",
        grid_empty="#161b22",
        grid_levels=("#0e4429", "#006d32", "#26a641", "#39d353"),
        left_fighter="#60a5fa",
        right_fighter="#fb7185",
        left_health="#22c55e",
        right_health="#f59e0b",
        combo_fill="#a78bfa",
        combo_track="#1f2937",
        impact="#fb923c",
        special="#f43f5e",
        border="#30363d",
    ),
}


GRAPHQL_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        weeks {
          contributionDays {
            contributionCount
            date
            weekday
          }
        }
      }
    }
  }
}
"""


def fetch_contribution_weeks(username: str, token: str, weeks: int) -> List[List[Dict[str, object]]]:
    today = dt.datetime.now(dt.timezone.utc)
    # GitHub GraphQL rejects contribution ranges longer than one year. Keep the
    # requested calendar within 365 days while still allowing the API to return
    # the usual 52/53 calendar columns, including partial boundary weeks.
    lookback_days = min(364, max(1, weeks * 7 - 1))
    start = today - dt.timedelta(days=lookback_days)
    payload = json.dumps(
        {
            "query": GRAPHQL_QUERY,
            "variables": {
                "login": username,
                "from": start.isoformat(),
                "to": today.isoformat(),
            },
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        GITHUB_GRAPHQL_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "commit-kombat-generator",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"GitHub GraphQL request failed: {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitHub GraphQL request failed: {exc.reason}") from exc

    if body.get("errors"):
        raise RuntimeError(f"GitHub GraphQL errors: {body['errors']}")

    weeks_data = (
        body.get("data", {})
        .get("user", {})
        .get("contributionsCollection", {})
        .get("contributionCalendar", {})
        .get("weeks", [])
    )
    if not weeks_data:
        raise RuntimeError("No contribution weeks returned by GitHub API")

    trimmed = weeks_data[-weeks:]
    if len(trimmed) < weeks:
        padding = [[{"contributionCount": 0, "date": "", "weekday": i} for i in range(7)] for _ in range(weeks - len(trimmed))]
        trimmed = padding + trimmed

    normalized: List[List[Dict[str, object]]] = []
    for week in trimmed:
        days = week.get("contributionDays", week)
        if len(days) < 7:
            full = list(days) + [
                {
                    "contributionCount": 0,
                    "date": "",
                    "weekday": i,
                }
                for i in range(len(days), 7)
            ]
            days = full
        normalized.append(days[:7])

    return normalized


def build_mock_contribution_weeks(weeks: int) -> List[List[Dict[str, object]]]:
    start = dt.date.today() - dt.timedelta(days=weeks * 7 - 1)
    data: List[List[Dict[str, object]]] = []
    for w in range(weeks):
        week: List[Dict[str, object]] = []
        for d in range(7):
            current = start + dt.timedelta(days=w * 7 + d)
            streak_band = (w + d) % 11
            if streak_band in (0, 6):
                count = 0
            else:
                count = ((w * 3 + d * 2) % 14) + 1
            week.append(
                {
                    "contributionCount": count,
                    "date": current.isoformat(),
                    "weekday": d,
                }
            )
        data.append(week)
    return data


def compute_levels(weeks: Sequence[Sequence[Dict[str, object]]]) -> List[List[int]]:
    counts = [int(day.get("contributionCount", 0)) for week in weeks for day in week]
    non_zero = sorted(c for c in counts if c > 0)
    if not non_zero:
        return [[0 for _ in week] for week in weeks]

    def quantile(q: float) -> int:
        idx = min(len(non_zero) - 1, max(0, math.floor((len(non_zero) - 1) * q)))
        return non_zero[idx]

    t1, t2, t3 = quantile(0.25), quantile(0.5), quantile(0.75)

    levels: List[List[int]] = []
    for week in weeks:
        w: List[int] = []
        for day in week:
            count = int(day.get("contributionCount", 0))
            if count <= 0:
                w.append(0)
            elif count <= t1:
                w.append(1)
            elif count <= t2:
                w.append(2)
            elif count <= t3:
                w.append(3)
            else:
                w.append(4)
        levels.append(w)
    return levels


def compute_metrics(weeks: Sequence[Sequence[Dict[str, object]]], levels: Sequence[Sequence[int]]) -> Dict[str, int]:
    days = [day for week in weeks for day in week]
    ordered_days = sorted(
        days,
        key=lambda d: d.get("date", "9999-12-31") or "9999-12-31",
    )

    longest_streak = 0
    current_streak = 0
    inactive_gaps = 0
    total_commits = 0

    for day in ordered_days:
        count = int(day.get("contributionCount", 0))
        total_commits += count
        if count > 0:
            current_streak += 1
            longest_streak = max(longest_streak, current_streak)
        else:
            if current_streak > 0:
                inactive_gaps += 1
            current_streak = 0

    weekly_totals = [sum(int(day.get("contributionCount", 0)) for day in week) for week in weeks]
    max_weekly = max(weekly_totals, default=0)
    max_level = max((level for week in levels for level in week), default=0)

    player_health = 100
    rival_health = 100
    for total in weekly_totals:
        if max_weekly > 0:
            scaled = int(round((total / max_weekly) * 9))
        else:
            scaled = 0
        rival_health = max(0, rival_health - scaled)
        if total == 0:
            player_health = max(0, player_health - 4)

    return {
        "longest_streak": longest_streak,
        "current_streak": current_streak,
        "inactive_gaps": inactive_gaps,
        "total_commits": total_commits,
        "max_weekly": max_weekly,
        "player_health": player_health,
        "rival_health": rival_health,
        "max_level": max_level,
    }


def escape_xml(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def render_fighter(x: int, y: int, facing: int, body_color: str, tag: str) -> str:
    scale = -1 if facing < 0 else 1
    tx = x if facing > 0 else x + 28
    transform = f"translate({tx},{y}) scale({scale},1)"
    return f"""
    <g id="{tag}" transform="{transform}">
      <rect x="8" y="3" width="12" height="10" rx="3" fill="{body_color}" />
      <rect x="10" y="13" width="8" height="9" rx="2" fill="{body_color}" />
      <rect x="2" y="12" width="6" height="4" rx="1" fill="{body_color}" />
      <rect x="20" y="12" width="6" height="4" rx="1" fill="{body_color}" />
      <rect x="9" y="22" width="4" height="8" rx="1" fill="{body_color}" />
      <rect x="15" y="22" width="4" height="8" rx="1" fill="{body_color}" />
    </g>
    """


def render_svg(username: str, weeks: Sequence[Sequence[Dict[str, object]]], levels: Sequence[Sequence[int]], metrics: Dict[str, int], theme: Theme) -> str:
    width, height = 940, 300
    grid_x, grid_y = 75, 70
    cell, gap = 11, 3

    combo_value = min(metrics["longest_streak"], 99)
    combo_ratio = min(1.0, combo_value / 30.0)
    combo_width = int(210 * combo_ratio)

    special = "RAGE ART" if metrics["longest_streak"] >= 14 else "COUNTER HIT"
    if metrics["max_weekly"] >= 45:
        special = "PERFECT ROUND"

    player_health_w = int((metrics["player_health"] / 100) * 175)
    rival_health_w = int((metrics["rival_health"] / 100) * 175)

    cells: List[str] = []
    flashes: List[str] = []
    pulse_group_duration = "16s"

    for wx, week in enumerate(levels):
        for dy, level in enumerate(week):
            x = grid_x + wx * (cell + gap)
            y = grid_y + dy * (cell + gap)
            fill = theme.grid_empty if level == 0 else theme.grid_levels[level - 1]
            cells.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{fill}" />'
            )
            if level > 0:
                strength = 0.2 + level * 0.17
                begin = f"{(wx * 7 + dy) * 0.03:.2f}s"
                flashes.append(
                    f'''<rect x="{x-1}" y="{y-1}" width="{cell+2}" height="{cell+2}" rx="3" fill="{theme.impact}" opacity="0">
  <animate attributeName="opacity" values="0;{strength:.2f};0" begin="{begin}" dur="0.85s" repeatDur="{pulse_group_duration}" repeatCount="indefinite" />
</rect>'''
                )

    title = f"Commit Kombat contribution graph for {username}"
    desc = (
        "Animated GitHub-style 7-row contribution grid. "
        "Contribution intensity drives hit flashes, active streaks build combo, "
        "weekly totals damage rival health, and inactive gaps trigger counters."
    )

    return f"""<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{width}\" height=\"{height}\" viewBox=\"0 0 {width} {height}\" role=\"img\" aria-labelledby=\"title desc\">
  <title id=\"title\">{escape_xml(title)}</title>
  <desc id=\"desc\">{escape_xml(desc)}</desc>
  <rect x=\"0\" y=\"0\" width=\"{width}\" height=\"{height}\" fill=\"{theme.background}\" />
  <rect x=\"24\" y=\"22\" width=\"892\" height=\"254\" rx=\"14\" fill=\"{theme.panel}\" stroke=\"{theme.border}\" />

  <text x=\"44\" y=\"45\" fill=\"{theme.title}\" font-size=\"21\" font-family=\"Segoe UI, DejaVu Sans, Arial\" font-weight=\"700\">COMMIT KOMBAT</text>
  <text x=\"286\" y=\"45\" fill=\"{theme.subtitle}\" font-size=\"13\" font-family=\"Segoe UI, DejaVu Sans, Arial\">{escape_xml(username)} • Repository Fighter</text>

  <rect x=\"44\" y=\"58\" width=\"175\" height=\"10\" rx=\"4\" fill=\"{theme.combo_track}\" />
  <rect x=\"44\" y=\"58\" width=\"{player_health_w}\" height=\"10\" rx=\"4\" fill=\"{theme.left_health}\" />
  <text x=\"44\" y=\"84\" fill=\"{theme.subtitle}\" font-size=\"11\" font-family=\"Segoe UI, DejaVu Sans, Arial\">PLAYER HP</text>

  <rect x=\"721\" y=\"58\" width=\"175\" height=\"10\" rx=\"4\" fill=\"{theme.combo_track}\" />
  <rect x=\"{896 - rival_health_w}\" y=\"58\" width=\"{rival_health_w}\" height=\"10\" rx=\"4\" fill=\"{theme.right_health}\" />
  <text x=\"799\" y=\"84\" text-anchor=\"middle\" fill=\"{theme.subtitle}\" font-size=\"11\" font-family=\"Segoe UI, DejaVu Sans, Arial\">RIVAL HP</text>

  <rect x=\"365\" y=\"42\" width=\"210\" height=\"14\" rx=\"7\" fill=\"{theme.combo_track}\" />
  <rect x=\"365\" y=\"42\" width=\"{combo_width}\" height=\"14\" rx=\"7\" fill=\"{theme.combo_fill}\" />
  <text x=\"470\" y=\"38\" text-anchor=\"middle\" fill=\"{theme.title}\" font-size=\"10\" font-family=\"Segoe UI, DejaVu Sans, Arial\">{combo_value} HIT COMBO</text>

  <g id=\"grid\">{''.join(cells)}</g>
  <g id=\"impact\">{''.join(flashes)}</g>

  {render_fighter(292, 219, 1, theme.left_fighter, 'fighter-left')}
  {render_fighter(620, 219, -1, theme.right_fighter, 'fighter-right')}

  <text x=\"470\" y=\"219\" text-anchor=\"middle\" fill=\"{theme.title}\" font-size=\"12\" font-family=\"Segoe UI, DejaVu Sans, Arial\">WEEKLY POWER: {metrics['max_weekly']} • INACTIVE GAPS: {metrics['inactive_gaps']}</text>

  <g>
    <rect x=\"380\" y=\"230\" width=\"182\" height=\"28\" rx=\"6\" fill=\"{theme.special}\" opacity=\"0.85\" />
    <text x=\"471\" y=\"249\" text-anchor=\"middle\" fill=\"#ffffff\" font-size=\"14\" font-family=\"Segoe UI, DejaVu Sans, Arial\" font-weight=\"700\">{special}</text>
    <animateTransform attributeName=\"transform\" type=\"scale\" values=\"1;1.04;1\" begin=\"0s\" dur=\"2s\" repeatCount=\"indefinite\" />
  </g>

  <g opacity=\"0\">
    <text x=\"470\" y=\"158\" text-anchor=\"middle\" fill=\"{theme.special}\" font-size=\"22\" font-family=\"Segoe UI, DejaVu Sans, Arial\" font-weight=\"800\">K.O.</text>
    <animate attributeName=\"opacity\" values=\"0;0;0;1;1\" keyTimes=\"0;0.70;0.85;0.95;1\" dur=\"{pulse_group_duration}\" repeatCount=\"indefinite\" />
  </g>
</svg>
"""


def write_svg(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Commit Kombat contribution SVGs")
    parser.add_argument("--user", required=True, help="GitHub username")
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""), help="GitHub token")
    parser.add_argument("--weeks", type=int, default=53, help="How many contribution weeks to render")
    parser.add_argument("--output-light", required=True, help="Light theme output SVG path")
    parser.add_argument("--output-dark", required=True, help="Dark theme output SVG path")
    parser.add_argument("--mock", action="store_true", help="Use deterministic mock contribution data")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.token and not args.mock:
        print("GITHUB_TOKEN is required to fetch contribution data.", file=sys.stderr)
        return 1

    weeks = build_mock_contribution_weeks(args.weeks) if args.mock else fetch_contribution_weeks(args.user, args.token, args.weeks)
    levels = compute_levels(weeks)
    metrics = compute_metrics(weeks, levels)

    light_svg = render_svg(args.user, weeks, levels, metrics, THEMES["light"])
    dark_svg = render_svg(args.user, weeks, levels, metrics, THEMES["dark"])

    write_svg(Path(args.output_light), light_svg)
    write_svg(Path(args.output_dark), dark_svg)

    print(
        json.dumps(
            {
                "user": args.user,
                "weeks": args.weeks,
                "max_weekly": metrics["max_weekly"],
                "longest_streak": metrics["longest_streak"],
                "outputs": [args.output_light, args.output_dark],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
