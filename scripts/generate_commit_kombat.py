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
from typing import Dict, List, Sequence, Tuple

GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"


@dataclass(frozen=True)
class Theme:
    name: str
    background: str
    grid_empty: str
    grid_levels: Sequence[str]
    character_primary: str
    character_accent: str
    projectile: str
    flash: str


THEMES: Dict[str, Theme] = {
    "light": Theme(
        name="light",
        background="#ffffff",
        grid_empty="#ebedf0",
        grid_levels=("#9be9a8", "#40c463", "#30a14e", "#216e39"),
        character_primary="#2563eb",
        character_accent="#0f172a",
        projectile="#0ea5e9",
        flash="#22d3ee",
    ),
    "dark": Theme(
        name="dark",
        background="#0d1117",
        grid_empty="#161b22",
        grid_levels=("#0e4429", "#006d32", "#26a641", "#39d353"),
        character_primary="#60a5fa",
        character_accent="#e6edf3",
        projectile="#38bdf8",
        flash="#67e8f9",
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
    # GitHub GraphQL rejects contribution ranges longer than one year.
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
            "User-Agent": "commit-blast-generator",
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


def escape_xml(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def pick_targets(levels: Sequence[Sequence[int]], max_targets: int = 12) -> List[Tuple[int, int, int]]:
    per_column: List[Tuple[int, int, int]] = []
    for wx, week in enumerate(levels):
        best_level = max(week)
        if best_level <= 0:
            continue
        dy = week.index(best_level)
        per_column.append((wx, dy, best_level))

    if len(per_column) <= max_targets:
        return per_column

    picked: List[Tuple[int, int, int]] = []
    for i in range(max_targets):
        idx = round(i * (len(per_column) - 1) / (max_targets - 1))
        picked.append(per_column[idx])
    return picked


def render_character(theme: Theme) -> str:
    return f"""
    <g id=\"hero\">
      <rect x=\"3\" y=\"0\" width=\"6\" height=\"4\" rx=\"1\" fill=\"{theme.character_primary}\" />
      <rect x=\"2\" y=\"4\" width=\"8\" height=\"5\" rx=\"1\" fill=\"{theme.character_primary}\" />
      <rect x=\"10\" y=\"5\" width=\"3\" height=\"2\" rx=\"1\" fill=\"{theme.character_accent}\" />
      <rect x=\"0\" y=\"6\" width=\"3\" height=\"2\" rx=\"1\" fill=\"{theme.character_primary}\" />
      <rect x=\"3\" y=\"9\" width=\"2\" height=\"4\" rx=\"1\" fill=\"{theme.character_primary}\" />
      <rect x=\"7\" y=\"9\" width=\"2\" height=\"4\" rx=\"1\" fill=\"{theme.character_primary}\" />
    </g>
    """


def render_svg(username: str, levels: Sequence[Sequence[int]], theme: Theme) -> str:
    columns = max(1, len(levels))
    rows = 7

    cell, gap = 10, 3
    grid_w = columns * (cell + gap) - gap
    grid_h = rows * (cell + gap) - gap

    grid_x = 38
    grid_y = 16
    svg_w = grid_x + grid_w + 18
    svg_h = grid_y + grid_h + 26

    hero_start_x = grid_x - 16
    hero_end_x = grid_x + grid_w - 12
    hero_y = grid_y + grid_h - 15
    loop_dur = max(10.0, min(18.0, columns / 3.7))

    cells: List[str] = []
    for wx, week in enumerate(levels):
        for dy, level in enumerate(week):
            x = grid_x + wx * (cell + gap)
            y = grid_y + dy * (cell + gap)
            fill = theme.grid_empty if level == 0 else theme.grid_levels[level - 1]
            cells.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{fill}" />')

    targets = pick_targets(levels)
    projectile_fx: List[str] = []
    impact_fx: List[str] = []

    for i, (wx, dy, level) in enumerate(targets):
        tx = grid_x + wx * (cell + gap) + (cell / 2)
        ty = grid_y + dy * (cell + gap) + (cell / 2)

        if columns > 1:
            progress = wx / (columns - 1)
        else:
            progress = 0.0

        sx = hero_start_x + (hero_end_x - hero_start_x) * progress + 12
        sy = hero_y + 6

        shot_dur = 0.45
        shoot_frac = min(0.2, shot_dur / loop_dur)
        offset = (i * loop_dur) / max(1, len(targets))

        projectile_fx.append(
            f'''<circle cx="{sx:.2f}" cy="{sy:.2f}" r="1.7" fill="{theme.projectile}" opacity="0">
  <animate attributeName="cx" values="{sx:.2f};{tx:.2f};{tx:.2f}" keyTimes="0;{shoot_frac:.4f};1" dur="{loop_dur:.2f}s" begin="{offset:.2f}s" repeatCount="indefinite" />
  <animate attributeName="cy" values="{sy:.2f};{ty:.2f};{ty:.2f}" keyTimes="0;{shoot_frac:.4f};1" dur="{loop_dur:.2f}s" begin="{offset:.2f}s" repeatCount="indefinite" />
  <animate attributeName="opacity" values="0;1;1;0;0" keyTimes="0;0.01;{shoot_frac * 0.7:.4f};{shoot_frac:.4f};1" dur="{loop_dur:.2f}s" begin="{offset:.2f}s" repeatCount="indefinite" />
</circle>'''
        )

        flash_peak = 0.20 + (level * 0.14)
        flash_r1 = 1.6 + (level * 0.8)
        flash_r2 = 3.2 + (level * 1.2)
        flash_begin = (offset + shot_dur * 0.75) % loop_dur
        impact_span = min(0.16, 0.24 / loop_dur)
        impact_fx.append(
            f'''<circle cx="{tx:.2f}" cy="{ty:.2f}" r="0.9" fill="{theme.flash}" opacity="0">
  <animate attributeName="r" values="0.9;{flash_r1:.2f};{flash_r2:.2f}" keyTimes="0;{impact_span * 0.5:.4f};{impact_span:.4f}" dur="{loop_dur:.2f}s" begin="{flash_begin:.2f}s" repeatCount="indefinite" />
  <animate attributeName="opacity" values="0;{flash_peak:.2f};0;0" keyTimes="0;{impact_span * 0.45:.4f};{impact_span:.4f};1" dur="{loop_dur:.2f}s" begin="{flash_begin:.2f}s" repeatCount="indefinite" />
</circle>'''
        )

    title = f"Commit Blast contribution graph for {username}"
    desc = (
        "A minimal animated GitHub contribution grid. One original pixel character glides across the weeks and fires energy shots at active contribution cells. "
        "Impact flashes scale with contribution intensity."
    )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}" role="img" aria-labelledby="title desc">
  <title id="title">{escape_xml(title)}</title>
  <desc id="desc">{escape_xml(desc)}</desc>
  <rect width="{svg_w}" height="{svg_h}" fill="{theme.background}" />

  <g id="contribution-grid">{"".join(cells)}</g>
  <g id="projectiles">{"".join(projectile_fx)}</g>
  <g id="impacts">{"".join(impact_fx)}</g>

  <g transform="translate({hero_start_x},{hero_y})">
    {render_character(theme)}
    <animateTransform attributeName="transform" type="translate" values="{hero_start_x} {hero_y}; {hero_end_x} {hero_y}; {hero_start_x} {hero_y}" keyTimes="0;0.5;1" dur="{loop_dur:.2f}s" repeatCount="indefinite" />
  </g>
</svg>
'''


def write_svg(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Commit Blast contribution SVGs")
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

    light_svg = render_svg(args.user, levels, THEMES["light"])
    dark_svg = render_svg(args.user, levels, THEMES["dark"])

    write_svg(Path(args.output_light), light_svg)
    write_svg(Path(args.output_dark), dark_svg)

    print(
        json.dumps(
            {
                "user": args.user,
                "weeks": args.weeks,
                "targets": len(pick_targets(levels)),
                "outputs": [args.output_light, args.output_dark],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
