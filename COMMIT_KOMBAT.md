# Commit Kombat (Repository Fighter)

This repository replaces the default snake animation with a custom **Commit Kombat** contribution graph renderer.

## Architecture

- Workflow: `.github/workflows/commit-kombat.yml`
- Generator: `scripts/generate_commit_kombat.py`
- Published artifacts (output branch):
  - `github-contribution-grid-snake.svg` (light)
  - `github-contribution-grid-snake-dark.svg` (dark)

The workflow runs on schedule, manual dispatch, and pushes to `main`, then publishes the generated SVGs to the `output` branch.

## Contribution Data Source

The generator calls GitHub GraphQL (`https://api.github.com/graphql`) with `GITHUB_TOKEN` and fetches `contributionCalendar.weeks.contributionDays` for the repository owner.

It transforms only contribution calendar data into mechanics:

- **Contribution intensity** (`contributionCount`) → hit/impact flash strength + cell brightness
- **Consecutive active days** → combo meter (`HIT COMBO`)
- **Weekly totals** → rival health damage
- **Inactive gaps** (`0` contribution days after active streaks) → counter pressure + combo reset
- **Strong streak/weekly peaks** → special banner (`RAGE ART`, `PERFECT ROUND`)

## Visual Design Notes

- Keeps a recognizable GitHub-style **7-row x ~53-column** contribution grid.
- Uses original vector/pixel-style fighters, health bars, impact flashes, and status text.
- Uses SVG SMIL animation only (no JavaScript).
- Includes a readable static first frame so it still looks correct if animation is not played.

## Local Preview

Use mock mode for quick local rendering without API calls:

```bash
cd <repo-root>
python scripts/generate_commit_kombat.py \
  --user Saad-61 \
  --mock \
  --output-light /tmp/commit-kombat-preview/github-contribution-grid-snake.svg \
  --output-dark /tmp/commit-kombat-preview/github-contribution-grid-snake-dark.svg
```

For real contribution data, use a GitHub token that can call GraphQL APIs:

```bash
cd <repo-root>
export GITHUB_TOKEN=<your_token>
python scripts/generate_commit_kombat.py \
  --user Saad-61 \
  --output-light /tmp/commit-kombat-preview/github-contribution-grid-snake.svg \
  --output-dark /tmp/commit-kombat-preview/github-contribution-grid-snake-dark.svg
```

Open the generated SVG files in a browser.

## Temporary Branch / README Preview

1. Push your branch/PR with workflow and generator changes.
2. Run **Actions → generate commit kombat animation → Run workflow**.
3. After completion, confirm files exist on the `output` branch:
   - `https://raw.githubusercontent.com/Saad-61/Saad-61/output/github-contribution-grid-snake.svg`
   - `https://raw.githubusercontent.com/Saad-61/Saad-61/output/github-contribution-grid-snake-dark.svg`
4. In the PR Files view (or branch README), verify the contribution graph block renders using those `output` URLs.

## Determinism + Compatibility

For a fixed contribution dataset, the output SVG is deterministic:

- no random values
- fixed geometry
- deterministic metric and threshold calculations

The renderer emits valid standalone SVGs with `<title>` and `<desc>` for accessibility.
