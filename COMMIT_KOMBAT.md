# Commit Blast Animation Guide

This repository publishes a lightweight contribution animation called **Commit Blast**.

## What it renders

- A GitHub-style **7-row contribution grid** (about 53 columns)
- One original pixel character that moves across the grid
- A small energy projectile that targets deterministic active cells
- Subtle impact flashes scaled by contribution intensity (levels 1–4)

No dashboard panel, health bars, combo UI, second fighter, or statistics are rendered.

## Files

- Workflow: `/home/runner/work/Saad-61/Saad-61/.github/workflows/commit-kombat.yml`
- Generator: `/home/runner/work/Saad-61/Saad-61/scripts/generate_commit_kombat.py`
- Published outputs (`output` branch):
  - `github-contribution-grid-snake.svg` (light)
  - `github-contribution-grid-snake-dark.svg` (dark)

## Local preview (mock data)

```bash
cd /home/runner/work/Saad-61/Saad-61
python scripts/generate_commit_kombat.py \
  --user Saad-61 \
  --mock \
  --output-light /tmp/commit-blast-preview/github-contribution-grid-snake.svg \
  --output-dark /tmp/commit-blast-preview/github-contribution-grid-snake-dark.svg
```

Open both files from `/tmp/commit-blast-preview/` in a browser.

## Local preview (real contribution data)

```bash
cd /home/runner/work/Saad-61/Saad-61
export GITHUB_TOKEN=<your_token>
python scripts/generate_commit_kombat.py \
  --user Saad-61 \
  --output-light /tmp/commit-blast-preview/github-contribution-grid-snake.svg \
  --output-dark /tmp/commit-blast-preview/github-contribution-grid-snake-dark.svg
```

The GraphQL query is constrained to a maximum of **364 days** to stay within GitHub's one-year limit.

## Workflow manual dispatch

1. Open **Actions** in GitHub.
2. Select **generate commit kombat animation**.
3. Click **Run workflow** and choose `main`.
4. Wait for the `generate` job to finish successfully.

## Output-branch preview URLs

- Light: `https://raw.githubusercontent.com/Saad-61/Saad-61/output/github-contribution-grid-snake.svg`
- Dark: `https://raw.githubusercontent.com/Saad-61/Saad-61/output/github-contribution-grid-snake-dark.svg`

## Cache refresh tips

If README still shows an old image:

- Hard refresh the page
- Or temporarily append a cache-busting query string in tests, e.g. `...?v=2`
