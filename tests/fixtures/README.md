# Test fixtures

Saved responses in the shape of the Hugging Face REST API:

- `list/<author>__<pipeline_tag>.json`: `GET /api/models?author=...&pipeline_tag=...&sort=createdAt&direction=-1`
- `models/<org>__<name>.json`: `GET /api/models/<org>/<name>`

**These are synthetic, not recorded.** The repository was first built in an environment
that could not reach huggingface.co, so the files were written by hand to follow the API's
field names (`id`, `createdAt`, `lastModified`, `sha`, `gated`, `library_name`,
`pipeline_tag`, `tags`, `cardData`, `safetensors`). All publishers and models are fictional
(`FixtureLab`, `FixtureVision`) so no invented fact is attached to a real model.

What each fixture exercises:

| Repo | Purpose |
| --- | --- |
| `FixtureLab/Fixture-LM-8B` | complete metadata, 8,030,261,248 parameters |
| `FixtureLab/Fixture-LM-8B-GGUF` | skipped by `exclude_name_patterns` |
| `FixtureLab/Fixture-LM-Old` | outside a 30-day lookback window |
| `FixtureVision/Fixture-VL-3B` | no safetensors metadata (parameters unknown), gated, no base model |
| `FixtureEmpty` (author) | returns zero models, must be reported |

To replace them with real recordings later, save live API responses under the same layout
and adjust the assertions in `tests/` that depend on fixture values.
