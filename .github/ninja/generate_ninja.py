#!/usr/bin/env python3
"""Render a restrained pixel-ninja contribution animation as an animated GIF."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

CELL, GAP, COLUMNS, ROWS = 12, 2, 53, 7
PITCH = CELL + GAP
PAD_X, PAD_Y = 30, 38
WIDTH = PAD_X * 2 + COLUMNS * PITCH - GAP
HEIGHT = PAD_Y * 2 + ROWS * PITCH - GAP
SCALE = 2
FPS_MS = 48
LEVEL_COLOURS = {0: "#161b22", 1: "#0e4429", 2: "#006d32", 3: "#26a641", 4: "#39d353"}
GITHUB_LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}


def read_days(source: Path) -> list[dict[str, Any]]:
    payload = json.loads(source.read_text(encoding="utf-8"))
    weeks = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    days = [day for week in weeks for day in week["contributionDays"]]
    if len(days) != COLUMNS * ROWS:
        raise ValueError(f"Expected {COLUMNS * ROWS} contribution days, got {len(days)}")
    return days


def active_cells(days: list[dict[str, Any]]) -> dict[tuple[int, int], int]:
    result: dict[tuple[int, int], int] = {}
    for index, day in enumerate(days):
        count = int(day["contributionCount"])
        if count:
            level = day.get("contributionLevel", "FIRST_QUARTILE")
            level_number = GITHUB_LEVELS.get(str(level), level if isinstance(level, int) else 1)
            result[(index // ROWS, index % ROWS)] = min(4, max(1, int(level_number)))
    return result


def action_points(cells: dict[tuple[int, int], int]) -> list[tuple[int, int]]:
    remaining, points = set(cells), []
    for column in range(COLUMNS):
        rows = range(ROWS) if column % 2 == 0 else range(ROWS - 1, -1, -1)
        for row in rows:
            key = (column, row)
            if key not in remaining:
                continue
            points.append(key)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    remaining.discard((column + dx, row + dy))
    return points


def center(cell: tuple[int, int]) -> tuple[float, float]:
    col, row = cell
    return (PAD_X + col * PITCH + CELL / 2, PAD_Y + row * PITCH + CELL / 2)


def draw_ninja(draw: ImageDraw.ImageDraw, x: float, y: float, facing: int, slashing: bool) -> None:
    x, y = int(x), int(y)
    draw.rectangle((x - 5, y + 6, x + 5, y + 7), fill="#010409")
    draw.rectangle((x - 4, y - 5, x + 4, y + 5), fill="#7ee787")
    draw.rectangle((x - 5, y - 3, x + 5, y - 1), fill="#1f6feb")
    draw.rectangle((x + facing * 5, y - 3, x + facing * 8, y - 2), fill="#58a6ff")
    draw.rectangle((x - 2, y - 2, x + 2, y), fill="#010409")
    draw.rectangle((x - 3, y + 6, x - 1, y + 8), fill="#7ee787")
    draw.rectangle((x + 1, y + 6, x + 3, y + 8), fill="#7ee787")
    if slashing:
        sx = x + facing * 9
        draw.line((x + facing * 5, y, sx + facing * 8, y - 7), fill="#f0f6fc", width=2)
        draw.point((sx + facing * 9, y - 8), fill="#d2a8ff")


def draw_frame(cells, cleared, pos, facing, slashing) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), "#0d1117")
    draw = ImageDraw.Draw(image)
    for (col, row), level in cells.items():
        if (col, row) not in cleared:
            x, y = PAD_X + col * PITCH, PAD_Y + row * PITCH
            draw.rounded_rectangle((x, y, x + CELL - 1, y + CELL - 1), radius=2, fill=LEVEL_COLOURS[level])
    draw_ninja(draw, *pos, facing, slashing)
    return image.resize((WIDTH * SCALE, HEIGHT * SCALE), Image.Resampling.NEAREST)


def render(days: list[dict[str, Any]], output: Path) -> None:
    cells, points = active_cells(days), action_points(active_cells(days))
    if not points:
        points = [(0, ROWS - 1)]
    frames, cleared = [], set()
    previous = (PAD_X - 10, PAD_Y + (ROWS - 1) * PITCH + CELL / 2)
    for point in points:
        target, facing = center(point), 1 if center(point)[0] >= previous[0] else -1
        for step in range(1, 4):
            ratio = step / 3
            pos = (previous[0] + (target[0] - previous[0]) * ratio, previous[1] + (target[1] - previous[1]) * ratio)
            frames.append(draw_frame(cells, cleared, pos, facing, False))
        col, row = point
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if (col + dx, row + dy) in cells:
                    cleared.add((col + dx, row + dy))
        frames.append(draw_frame(cells, cleared, target, facing, True))
        previous = target
    rest = (WIDTH - PAD_X + 8, PAD_Y - 8)
    for step in range(1, 5):
        ratio = step / 4
        pos = (previous[0] + (rest[0] - previous[0]) * ratio, previous[1] + (rest[1] - previous[1]) * ratio)
        frames.append(draw_frame(cells, cleared, pos, 1, False))
    frames.extend([draw_frame(cells, cleared, rest, 1, False)] * 10)
    for column in range(COLUMNS):
        for row in range(ROWS):
            cleared.discard((column, row))
        if column % 4 == 3 or column == COLUMNS - 1:
            frames.append(draw_frame(cells, cleared, rest, 1, False))
    frames.extend([draw_frame(cells, cleared, rest, 1, False)] * 12)
    output.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(output, save_all=True, append_images=frames[1:], duration=FPS_MS, loop=0, disposal=2, optimize=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    render(read_days(arguments.input), arguments.output)
