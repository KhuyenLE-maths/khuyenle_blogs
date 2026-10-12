# ModelScopeX — Kickoff (v2)

Read `CLAUDE.md` first. Its stack, evidence rules, and "Ask me before" list apply to everything below.
Do Milestone 0, then Milestone 1, then stop and report. Do not start later milestones.

Optimization target: the most useful output per unit of development time, compute, API usage, and maintenance. Not the number of features.

## Goal

ModelScopeX tracks new open-weight LLM and VLM releases on Hugging Face, keeps a sourced record of facts about each model, and publishes model pages and articles as a static blog.

Catalogs that summarize vendor claims already exist (for example llm-releases.com). ModelScopeX differs in two ways:

1. Every fact on the site shows its source and its verification status.
2. From Milestone 4 on: independent measurements on Vietnamese documents and tasks, run on hardware I own (MacBook Pro M1 Pro 16 GB; Ubuntu workstation `admin1` with an RTX 4090 24 GB).

Milestone 1 builds the foundation for both.

## Milestone 0 — Audit (short)

Record the results in `docs/STATUS.md` only. No other documents.

- macOS version, chip, RAM (`sysctl hw.memsize`), free disk space.
- `python3 --version`; whether `git` and `gh` are installed.
- `git status` and the existing files. If the folder is not a git repository, run `git init`.
- Existing `.claude/` project configuration: list it, change nothing.
- Whether `HF_TOKEN` is set: yes or no only, never the value.

If Python is below 3.11, stop and ask before installing anything.
Do not search for or install skills, plugins, or MCP servers.

## Milestone 1 — MVP, end to end

```
msx discover → SQLite → msx draft → content/articles/<slug>.md
→ I review and edit → msx approve → msx build → site/ → msx preview
```

### 1.1 `config.toml`

Create exactly this; I will tune it later.

```toml
[site]
name = "ModelScopeX Blog"
base_url = "http://localhost:8000"   # changed at deploy time (Milestone 3)

[discover]
authors = [
  "Qwen", "meta-llama", "google", "mistralai", "deepseek-ai", "microsoft",
  "nvidia", "ibm-granite", "zai-org", "moonshotai", "openbmb", "allenai",
  "tencent", "XiaomiMiMo", "inclusionAI", "baidu", "PaddlePaddle",
]
categories = ["text-generation", "image-text-to-text"]
lookback_days = 30
max_models = 200
exclude_name_patterns = ["gguf", "awq", "gptq", "mlx", "bnb", "int4", "int8"]

[hardware.mac]
label = "MacBook Pro M1 Pro"
memory_gb = 16          # confirm in Milestone 0
usable_fraction = 0.7   # heuristic share of unified memory available for weights

[hardware.admin1]
label = "admin1, RTX 4090"
memory_gb = 24
usable_fraction = 0.9

[publishing]
paused = false
```

### 1.2 Schema (`migrations/001_init.sql`)

- `models`: `id` (HF repo id, lowercased, primary key), `repo_id` (original casing), `slug` (unique), `author`, `category`, `first_seen_at`, `last_checked_at`, `downloads`, `likes`.
- `sources`: `id`, `url` (unique), `kind` (`hf_api`, `hf_model_card`, `github`, `paper`, `vendor_blog`, `own_eval`), `retrieved_at`.
- `claims`: `id`, `model_id`, `field`, `value` (JSON text), `source_id`, `status`, `observed_at`. Append-only; the current value is the latest row per (`model_id`, `field`).
- `runs`: `id`, `command`, `args`, `started_at`, `finished_at`, `ok`, `message`.

Downloads and likes change daily: keep only their latest values on `models`, never as claims.

### 1.3 `msx discover`

- For each allowlisted author and category, list models created within `lookback_days`, newest first, up to `max_models` per run in total.
- Skip repository names that contain any `exclude_name_patterns` entry (case-insensitive).
- On every run, report allowlisted authors that returned zero models. Do not invent replacements.
- Store as `publisher_declared` claims: pipeline tag, license, created time, last-modified time, latest commit sha, gated status, parameter count (only from safetensors metadata when the API returns it), base model, languages, library.
- Material fields are license, parameter count, and gated status. A change in one of them marks that model's article as needing an update.
- Idempotent: a second run with no upstream change adds zero claim rows.
- One `runs` row per invocation, with counts: new models, new claims, skipped, errors.
- Respect HF rate limits. On an HTTP error, retry 3 times with backoff, then record the error and continue with the next model.

### 1.4 Hardware fit (`estimate.py`)

For models with a known parameter count:

- weight memory (GB) = parameters × bits / 8 / 1e9, for 16-bit, 8-bit, and 4-bit;
- "likely fits" on a target when weight memory ≤ `memory_gb × usable_fraction`.

Label every result `estimated`. State on the page that KV cache and runtime overhead are excluded. Explain the formula on `/methodology/`.

### 1.5 `msx draft <model-id>`

Write `content/articles/<slug>.md` deterministically from current claims:

- frontmatter: `title`, `slug`, `model_id`, `status: draft`, `created`, `updated`, `sources` (list of URLs);
- body: a short factual intro assembled from claim fields, a facts table (field, value, status, source), the hardware estimate, and a "Not yet verified" list of `unknown` fields.

No LLM prose in the generated file. If the file already exists, do not overwrite it; print which material facts changed since its `updated` date.

When I ask you in this session to write prose for a draft: use only claims in the DB or sources I give you, cite them inline, and keep `unknown` fields unknown.

### 1.6 `msx approve <slug>`

Validate, then set `status: approved` and refresh `updated`. Refuse when:

- `publishing.paused = true` in `config.toml`;
- frontmatter is incomplete, or `model_id` is not in the DB;
- `sources` is empty;
- the body contains `TODO`, `TBD`, `FIXME`, or `lorem ipsum`.

Print every failure, not only the first one.

### 1.7 `msx build` and `msx preview`

- Render only `approved` and `published` articles. Drafts never appear in `site/`.
- Pages: `/`, `/models/`, `/models/<slug>/` (every discovered model: facts table, sources, hardware estimate), `/blog/<slug>/`, `/methodology/` (statuses, formula, sources, update policy).
- Also `sitemap.xml` and `feed.xml` (RSS 2.0), with canonical URLs built from `site.base_url`.
- Markdown through `markdown-it-py` with raw HTML disabled; Jinja2 autoescape on.
- Readable on phone and desktop, no JavaScript required, one small CSS file.
- `msx preview` serves `site/` on port 8000. Start it in the background so the session does not block.

### 1.8 `msx status`

Counts by article status; models without an article; articles whose model had a material change after the article's `updated` date; the last 5 runs.

### 1.9 Tests

`pytest -q`, offline, using recorded HF API responses in `tests/fixtures/` (clearly named as fixtures). Cover:

1. discover is idempotent;
2. a changed license adds a second claim row and keeps the first;
3. a missing parameter count yields `unknown`, never a number;
4. hardware estimate arithmetic for one known case;
5. draft never overwrites an existing article;
6. approve refuses placeholder text, empty sources, and paused publishing;
7. build excludes drafts;
8. `<script>` tags and `javascript:` links in Markdown are not rendered as active content;
9. end to end: fixture → discover → draft → approve → build → the model page and article HTML contain the facts and source links.

Add one test marked `network` (registered in `pyproject.toml`, skipped by default) that runs discover against the live API for one author with `max_models = 3`.

### 1.10 Done when

- `pip install -e '.[dev]'` works in a fresh `.venv` and `pytest -q` passes.
- The full flow has run once on live data: discover, draft and approve one real model, build, preview.
- `README.md` contains setup and the command list. `docs/STATUS.md` states what is implemented, what is tested (with the actual pytest summary line), what is not done, and the next step.
- Then stop and report to me in Vietnamese: what works and how it was verified, what does not, and the one next step you recommend.

## Later milestones (do not build now)

2. Writing workflow. If writing article prose turns out to be repetitive, propose a project skill at `.claude/skills/write-article/SKILL.md`; I approve before it is created. Add update notes to articles when material facts change.
3. Publishing. Deploy `site/` to GitHub Pages and set `published` plus `published_at` on deploy; optional `launchd` job for `msx discover`. Both need my approval.
4. Independent evaluation on `admin1` over SSH: small Vietnamese OCR/document and instruction-following sets. Results become `independently_measured` claims with dataset, metric, hardware, model revision, and script commit. The first remote run needs my approval.
5. More categories (embeddings, rerankers, speech) and comparison pages, only after milestones 2 to 4 are useful.
