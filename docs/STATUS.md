# Status

Last updated: 2026-10-12. Milestone 1 complete: code, tests, and the first live-data run all done on the Mac.

## Live run (2026-10-12, on the Mac)

Full flow exercised against the real Hugging Face API from this MacBook:

- Reachability: `GET https://huggingface.co/api/models?limit=1` → HTTP 200. `HF_TOKEN` not set (public access only).
- `pytest -q` → 15 passed, 1 deselected.
- `msx discover --author Qwen --max-models 3 --lookback-days 365` → checked 3, 3 new models, 30 new claims
  (default 30-day lookback returned 0; Qwen had no repos created in the last 30 days).
  Models: `Qwen/Qwen-Drive-1.0-4B`, `Qwen/Qwen3.8-Flash-Next`, `Qwen/Qwen3.8-Flash-Next-FP8`.
  (These are post-training-cutoff releases; existence confirmed directly against the API — fabricated repo ids return an error, these return full metadata.)
- `msx draft Qwen/Qwen3.8-Flash-Next` → `content/articles/qwen-qwen3-8-flash-next.md` (fact-only, all `publisher_declared`, unknowns kept unknown).
- `msx approve qwen-qwen3-8-flash-next` → approved.
- `msx build` → 7 pages (3 models, 1 article), incl. sitemap.xml and feed.xml.
- `msx preview --port 8001` → every page (`/`, `/models/`, model page, `/blog/...`, `/methodology/`, sitemap, feed, css)
  returns HTTP 200; the model page renders the facts table, the commit sha, and the hardware estimate. Verified with real HTTP requests.
- `config.toml` `base_url` set to `http://localhost:8001` for this preview because another process held port 8000.

## Milestone 0: audit

Not run on the MacBook. The code was written and tested in a Linux cloud container:

| Item | Build environment |
| --- | --- |
| OS | Linux 6.18 (container) |
| Python | 3.13.16 |
| git | 2.43.0 |
| huggingface.co | **not reachable** (proxy returned 403 / `ProxyError`) |
| PyPI | reachable |
| Installed versions | huggingface_hub 2.2.0, jinja2 3.1.6, markdown-it-py 4.2.0, pyyaml 6.0.3, pytest 9.1.1 |

To finish Milestone 0 on the Mac, record here: macOS version, chip, RAM (`sysctl hw.memsize`),
free disk, `python3 --version`, whether `git` and `gh` exist, and whether `HF_TOKEN` is set
(yes/no only). Update `hardware.mac.memory_gb` in `config.toml` if RAM differs from 16 GB.

## Implemented

- Schema `migrations/001_init.sql`: models, sources, append-only claims (triggers block UPDATE/DELETE), runs.
- `msx discover`: allowlist × categories, lookback window, exclude patterns, dedupe, newest-first cap,
  10 claim fields, idempotent, retries (3, exponential backoff; no retry on 4xx except 429),
  zero-model authors reported, one `runs` row per invocation.
- Hardware-fit estimate for every configured target (16/8/4-bit).
- `msx draft`: deterministic fact-only Markdown with facts table, hardware table, "Not yet verified";
  never overwrites; reports material changes instead.
- `msx approve`: reports all failures (paused, frontmatter, unknown model, empty/invalid sources,
  placeholder text, slug mismatch).
- `msx build`: home, model directory, model pages, articles, methodology, sitemap.xml, RSS 2.0;
  base path taken from `site.base_url`; raw HTML disabled in Markdown; Jinja2 autoescape on.
- `msx status`, `msx preview`.

## Tested

```
pytest -q            → 15 passed, 1 deselected in 0.83s
pytest -q -m network → 1 failed: huggingface.co unreachable from the build environment (ProxyError)
```

Covered: idempotent discover; license change adds a row and keeps the first; missing parameter count
is `unknown`; append-only enforcement; retry policy; estimate arithmetic; draft content and
no-overwrite; approve refusals (placeholder, empty sources, paused); build excludes drafts; script
tags and `javascript:` links inert; end to end fixture → site; CLI flow.

Manual check: built the fixture site, served it with `msx preview`, and inspected screenshots of the
model page, an unknown-heavy model page, the article page, and a 390 px mobile view
(no page-level horizontal scroll).

## Not done

- `pytest -m network` passing (not yet run against the live API as a test).
- Fixtures are synthetic (fictional models), not recorded responses; see `tests/fixtures/README.md`.
- Public deployment (Milestone 3): not started; needs approval, a host, and a `base_url` change.
- `data/msx.sqlite` is not shipped; it is created on the first command.

## Deviations from the layout in CLAUDE.md

- Extra modules: `project.py` (config/root), `discover.py` (orchestration), `facts.py` (labels and
  formatting shared by draft and build), `articles.py` (frontmatter I/O). Each keeps one concern.
- Extra CLI options for testing and offline demos: `--fixtures`, `--lookback-days`, `--author`,
  `--max-models`, `--root`.

## Ideas (not built)

- A `--save-raw DIR` option on discover to record real API responses as fixtures.
- Pin dependency upper bounds once the live run confirms behaviour with current versions.

## Next step

Milestone 1 is done. The recommended next step is a broader `msx discover` run (more authors, the
default 30-day lookback) to fill the model directory with current releases, then decide on Milestone 3
publishing: pick a host (KICKOFF names GitHub Pages), set `base_url`, and deploy — all of which need
my approval and a `git push`.
