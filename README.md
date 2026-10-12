# ModelScopeX

Tracks new open-weight LLM and VLM releases on Hugging Face, keeps an append-only record of
sourced facts about each model, and publishes model pages and articles as a static blog.
Every fact shows its source and one of four statuses: `publisher_declared`,
`independently_measured`, `estimated`, `unknown`. Nothing is guessed.

```
msx discover → SQLite (claims) → msx draft → content/articles/<slug>.md
→ you review / edit → msx approve → msx build → site/ → msx preview
```

## Requirements

- macOS or Linux, Python 3.11 or newer (`python3 --version`).
  On macOS the system `python3` may be older; install a newer one from python.org or Homebrew.
- Network access to `huggingface.co` for `msx discover` (everything else works offline).
- Optional: `HF_TOKEN` in your environment for higher Hub rate limits. Never commit it.

## Setup

```bash
cd modelscopex
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q                      # 15 offline tests, should all pass
```

## Daily workflow

```bash
source .venv/bin/activate

msx discover                   # fetch recent models from allowlisted authors
msx status                     # what is new, what lacks an article, what needs an update
msx draft Qwen/Qwen3-8B        # fact-only draft in content/articles/<slug>.md (example id)
# edit the draft: add prose (by hand or with Claude Code), keep claims sourced
msx approve <slug>             # validates, then status: approved
msx build                      # renders approved + published articles into site/
msx preview                    # http://127.0.0.1:8000, Ctrl+C to stop
git add -A && git commit -m "Article: <slug>"
```

`msx draft` never overwrites an existing article. Run it again to see which material facts
(license, parameter count, gated access) changed since the article's `updated` date.

## Commands

| Command | What it does |
| --- | --- |
| `msx discover [--author A] [--max-models N] [--lookback-days D] [--fixtures DIR]` | List models created in the lookback window, skip excluded names, store facts as claims. Idempotent. `--fixtures` reads saved API responses instead of the network. |
| `msx status` | Article counts by status, models without an article, articles needing an update, last 5 runs. |
| `msx draft <repo-id or slug>` | Write a deterministic, fact-only draft. |
| `msx approve <slug>` | Validate (sources present, no placeholder text, model known, publishing not paused) and set `status: approved`. Prints every failure. |
| `msx build` | Rebuild `site/`: home, model directory, one page per model, articles, methodology, `sitemap.xml`, `feed.xml`. |
| `msx preview [--port 8000]` | Serve `site/` locally. Blocking; stop with Ctrl+C. |

All commands accept `--root DIR`; by default they use the nearest folder containing `config.toml`.

## Configuration (`config.toml`)

| Key | Meaning |
| --- | --- |
| `site.name`, `site.base_url` | Site title and canonical URL. If the site will live under a sub-path (e.g. GitHub Pages project site), put the full URL here; internal links follow it. |
| `discover.authors` | Hugging Face organisations to watch. `msx discover` reports any that return zero models. |
| `discover.categories` | Pipeline tags to query (`text-generation`, `image-text-to-text`). |
| `discover.lookback_days`, `discover.max_models` | Window and per-run cap. |
| `discover.exclude_name_patterns` | Case-insensitive substrings that skip quantized re-uploads. |
| `hardware.<name>` | `label`, `memory_gb`, `usable_fraction` for the hardware-fit estimate. |
| `publishing.paused` | `true` blocks `msx approve` (emergency stop). |

## Evidence model

- `claims` is append-only (database triggers reject UPDATE and DELETE). A changed value adds a row.
- Values read from the Hub API are `publisher_declared`; missing values are `unknown`.
- The hardware table is `estimated`: weights (GB) = parameters × bits ÷ 8 ÷ 10^9, "likely fits"
  when weights ≤ memory_gb × usable_fraction. KV cache and runtime overhead are excluded.
- Downloads and likes are stored on the `models` row only (they change daily).

## Offline demo

Try the whole flow without network, in a throwaway folder (run from the repo root, venv active):

```bash
REPO="$(pwd)"
mkdir -p /tmp/msx-demo && cp -r config.toml migrations templates /tmp/msx-demo/ && cd /tmp/msx-demo
msx discover --fixtures "$REPO/tests/fixtures" --lookback-days 3650 --author FixtureLab --author FixtureVision
msx draft FixtureLab/Fixture-LM-8B && msx approve fixturelab-fixture-lm-8b && msx build && msx preview
```

The fixtures describe fictional models (see `tests/fixtures/README.md`).

## Tests

```bash
pytest -q                 # offline, uses tests/fixtures
pytest -q -m network      # live smoke test against huggingface.co (needs network)
```

## Data and backup

- `data/msx.sqlite` holds all claims and run history. Commit it while it stays under 50 MB,
  or copy the file to back it up.
- `content/articles/` is versioned in Git; Git history is the article revision history.
- `site/` is build output and is not committed.

## Layout

```
src/msx/        cli.py project.py db.py hf.py discover.py estimate.py facts.py
                articles.py draft.py validate.py build.py
migrations/     001_init.sql
templates/      Jinja2 templates + style.css
content/articles/
tests/          test_*.py, fixtures/
docs/           KICKOFF.md (milestone spec), STATUS.md (current state)
```

## Troubleshooting

- **An author returns zero models**: the organisation name in `config.toml` is wrong or it
  published nothing in that category. Check the name on huggingface.co.
- **HTTP 429 / timeouts**: discover retries 3 times with backoff, records the error, and
  continues. Re-run later or set `HF_TOKEN`.
- **`msx: command not found`**: activate the virtualenv (`source .venv/bin/activate`).
- **`No config.toml found`**: run commands inside the project folder or pass `--root`.
