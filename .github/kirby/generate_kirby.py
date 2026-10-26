#!/usr/bin/env python3
"""Render a self-looping SVG where Kirby inhales the contribution grid from dark to bright greens."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

CELL, GAP = 10, 3
PITCH = CELL + GAP
PAD_L, PAD_R, PAD_T = 36, 16, 26
LANE = 56
LEGEND = 26
KIRBY_SCALE = 1.5
MOVE_PER_COL, MOVE_MIN = 0.07, 0.22
FLIGHT, STAGGER, SETTLE = 0.85, 0.35, 0.2
HOLD_EMPTY, FADE_IN, HOLD_FULL = 1.4, 0.8, 2.2
LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def read_days(source: Path) -> list[dict]:
    payload = json.loads(source.read_text(encoding="utf-8-sig"))
    weeks = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    days = []
    for col, week in enumerate(weeks):
        for day in week["contributionDays"]:
            when = date.fromisoformat(day["date"])
            days.append({
                "col": col,
                "row": (when.weekday() + 1) % 7,  # GitHub rows run Sunday to Saturday
                "level": LEVELS.get(str(day["contributionLevel"]), 0),
                "date": when,
            })
    return days


def tile(col: int, row: int) -> tuple[float, float]:
    return PAD_L + col * PITCH, PAD_T + row * PITCH


def plan_actions(cells: list[dict]) -> list[dict]:
    """Sweep darkest to brightest, alternating direction; each stop inhales a 3-column cone."""
    actions = []
    columns = max(c["col"] for c in cells) + 1
    for pass_no, level in enumerate(sorted({c["level"] for c in cells if c["level"]})):
        remaining = [c for c in cells if c["level"] == level]
        order = range(columns) if pass_no % 2 == 0 else range(columns - 1, -1, -1)
        step = 1 if pass_no % 2 == 0 else -1
        for col in order:
            if not any(c["col"] == col for c in remaining):
                continue
            # Stand on a column that holds tiles (one ahead if it has some) so Kirby never lags beside them.
            if any(c["col"] == col + step for c in remaining):
                col += step
            eaten = [c for c in remaining if abs(c["col"] - col) <= 1]
            remaining = [c for c in remaining if c not in eaten]
            actions.append({"col": col, "level": level, "cells": eaten})
    return actions


def pct(t: float, total: float) -> str:
    return f"{max(0.0, min(100.0, t / total * 100)):.3f}%"


def build(days: list[dict]) -> str:
    columns = max(d["col"] for d in days) + 1
    grid_w, grid_h = columns * PITCH - GAP, 7 * PITCH - GAP
    width = PAD_L + grid_w + PAD_R
    lane_y = PAD_T + grid_h + 30
    height = PAD_T + grid_h + LANE + LEGEND
    kirby_x = lambda col: tile(col, 0)[0] + CELL / 2

    actions = plan_actions([d for d in days if d["level"]])
    start_x = kirby_x(0)

    # Timeline: (time, x) stops for Kirby, plus one record per eaten tile.
    clock, x = 0.6, start_x
    walk = [(0.0, x), (clock, x)]
    puffs, mouths, flights = [(0.0, 1.0), (clock, 1.0)], [(0.0, 0.0), (clock, 0.0)], []
    for action in actions:
        target = kirby_x(action["col"])
        clock += max(MOVE_MIN, abs(action["col"] - (x - start_x) / PITCH) * MOVE_PER_COL)
        walk.append((clock, target))
        x = target
        arrive, ky, landed = clock, lane_y, clock
        far = max(abs(tile(0, c["row"])[1] + CELL / 2 - ky) for c in action["cells"])
        for c in action["cells"]:
            cx, cy = tile(c["col"], c["row"])
            near = abs(cy + CELL / 2 - ky) / far
            begin = arrive + 0.15 + near * STAGGER
            flights.append((c, begin, begin + FLIGHT, target - (cx + CELL / 2), ky - (cy + CELL / 2)))
            landed = max(landed, begin + FLIGHT)
        # Hold Kirby in place until the last tile has landed, otherwise he drifts off mid-inhale.
        end = landed + SETTLE
        walk.append((end, target))
        mouths += [(arrive, 0.0), (arrive + 0.2, 1.0), (landed, 1.0), (end, 0.0)]
        puffs += [(arrive, 1.0), (landed, 1.0 + 0.1 + 0.05 * action["level"]), (end + 0.3, 1.0)]
        clock = end
    reset = clock + HOLD_EMPTY
    total = reset + FADE_IN + HOLD_FULL
    walk += [(reset + FADE_IN, start_x), (total, start_x)]
    puffs.append((total, 1.0))
    mouths.append((total, 0.0))

    css = [
        ":root{--bg:#0d1117;--txt:#8b949e;--l0:#161b22;--l1:#0e4429;--l2:#006d32;--l3:#26a641;--l4:#39d353}",
        "@media(prefers-color-scheme:light){:root{--bg:#ffffff;--txt:#57606a;--l0:#ebedf0;--l1:#9be9a8;--l2:#40c463;--l3:#30a14e;--l4:#216e39}}",
        ".t{width:10px;height:10px;rx:2;ry:2}.lbl{font:10px -apple-system,Segoe UI,Helvetica,Arial,sans-serif;fill:var(--txt)}",
        ".l0{fill:var(--l0)}.l1{fill:var(--l1)}.l2{fill:var(--l2)}.l3{fill:var(--l3)}.l4{fill:var(--l4)}",
        ".f{transform-box:fill-box;transform-origin:center}",
        f"#k{{animation:walk {total:.2f}s linear infinite}}",
        f"#p{{animation:puff {total:.2f}s linear infinite;transform-box:fill-box;transform-origin:50% 85%}}",
        f"#m{{animation:mouth {total:.2f}s linear infinite;transform-box:fill-box;transform-origin:center}}",
        f"#w{{animation:wind {total:.2f}s linear infinite}}",
    ]
    frames = ["@keyframes walk{" + "".join(
        f"{pct(t, total)}{{transform:translate({px:.2f}px,{lane_y:.2f}px);animation-timing-function:ease-in-out}}" for t, px in walk) + "}",
        "@keyframes puff{" + "".join(f"{pct(t, total)}{{transform:scale({s:.3f})}}" for t, s in puffs) + "}",
        "@keyframes mouth{" + "".join(f"{pct(t, total)}{{transform:scale({s:.2f})}}" for t, s in mouths) + "}",
        "@keyframes wind{" + "".join(f"{pct(t, total)}{{opacity:{s:.0f}}}" for t, s in mouths) + "}"]

    flown = {id(f[0]): f for f in flights}
    body = []
    for d in days:
        px, py = tile(d["col"], d["row"])
        entry = flown.get(id(d))
        if not entry:
            body.append(f'<rect class="t l{d["level"]}" x="{px}" y="{py}"/>')
            continue
        name = f"c{len(frames)}"
        _, begin, land, dx, dy = entry
        hidden = f"transform:translate({dx:.1f}px,{dy:.1f}px) scale(.15);opacity:0"
        frames.append(
            f"@keyframes {name}{{0%,{pct(begin, total)}{{transform:none;opacity:1;animation-timing-function:ease-in}}"
            f"{pct(land, total)},{pct(reset, total)}{{{hidden}}}"
            f"{pct(reset + .001, total)}{{transform:none;opacity:0}}"
            f"{pct(reset + FADE_IN, total)},100%{{transform:none;opacity:1}}}}")
        css.append(f".{name}{{animation:{name} {total:.2f}s linear infinite}}")
        body.append(f'<rect class="t f l{d["level"]} {name}" x="{px}" y="{py}"/>')

    # Empty-tile layer under the animated tiles so cleared cells show GitHub's blank squares.
    empties = "".join(f'<rect class="t l0" x="{tile(d["col"], d["row"])[0]}" y="{tile(d["col"], d["row"])[1]}"/>'
                      for d in days if d["level"])

    labels, last = [], -9
    for col in range(columns):
        first = next((d for d in days if d["col"] == col), None)
        if first and (col == 0 or first["date"].month != next(d for d in days if d["col"] == col - 1)["date"].month) and col - last >= 3:
            labels.append(f'<text class="lbl" x="{tile(col, 0)[0]}" y="{PAD_T - 8}">{MONTHS[first["date"].month - 1]}</text>')
            last = col
    for row, name in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        labels.append(f'<text class="lbl" x="0" y="{tile(0, row)[1] + 9}">{name}</text>')

    legend_y = PAD_T + grid_h + LANE + 4
    lx = width - PAD_R - (5 * PITCH + 62)
    legend = [f'<text class="lbl" x="{lx}" y="{legend_y + 9}">Less</text>']
    for i in range(5):
        legend.append(f'<rect class="t l{i}" x="{lx + 28 + i * PITCH}" y="{legend_y}"/>')
    legend.append(f'<text class="lbl" x="{lx + 32 + 5 * PITCH}" y="{legend_y + 9}">More</text>')

    kirby = (
        f'<g id="k"><g transform="scale({KIRBY_SCALE})"><g id="w"opacity="0" stroke="var(--txt)" stroke-width="1" stroke-linecap="round">'
        '<path d="M-4-14v-5M0-16v-6M4-14v-5"/></g>'
        '<g id="p"><ellipse cx="-6.5" cy="6.5" rx="4" ry="2.6" fill="#e63b5a" transform="rotate(-12 -6.5 6.5)"/>'
        '<ellipse cx="6.5" cy="6.5" rx="4" ry="2.6" fill="#e63b5a" transform="rotate(12 6.5 6.5)"/>'
        '<circle cx="-8" cy="0" r="2.6" fill="#ffa0c4"/><circle cx="8" cy="0" r="2.6" fill="#ffa0c4"/>'
        '<circle r="7.5" fill="#ffb3d1"/>'
        '<ellipse cx="-4.6" cy="2" rx="1.9" ry="1.1" fill="#ff7aa8"/><ellipse cx="4.6" cy="2" rx="1.9" ry="1.1" fill="#ff7aa8"/>'
        '<ellipse cx="-2.2" cy="-2.2" rx="1.1" ry="2.1" fill="#1b1f3b"/><ellipse cx="2.2" cy="-2.2" rx="1.1" ry="2.1" fill="#1b1f3b"/>'
        '<rect x="-2.6" y="-3.9" width=".9" height="1" fill="#fff"/><rect x="1.8" y="-3.9" width=".9" height="1" fill="#fff"/>'
        '<ellipse id="m" cx="0" cy="2.6" rx="2.4" ry="2.6" fill="#9b1d3a" style="transform:scale(0)"/></g></g></g>'
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        'role="img" aria-label="Kirby inhaling the contribution graph from dark to bright greens">'
        f'<style>{"".join(css)}{"".join(frames)}</style>'
        f'<rect width="100%" height="100%" fill="var(--bg)" rx="6"/>'
        f'{"".join(labels)}{empties}{"".join(body)}{"".join(legend)}{kirby}</svg>'
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build(read_days(args.input)), encoding="utf-8")
