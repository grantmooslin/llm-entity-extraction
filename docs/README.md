# Experiment Log — static viewing site

This directory is the static GitHub Pages site for the
[llm-entity-extraction](https://github.com/Exios66/llm-entity-extraction)
experiment log: a clean, filterable, searchable viewer over every eval run in
`reports/experiment_log.jsonl` — **plus the complementary Posit Cloud portal**
(`posit/`): a Quarto website integrating the experiment log, the agent kanban
board, and the discussion board under one themed URL.

## Viewing

**Live site:** `https://exios66.github.io/llm-entity-extraction/`
**Posit portal:** `https://exios66.github.io/llm-entity-extraction/posit/`
(once GitHub Pages is enabled — see below).

## Layout

| Path | Contents |
|---|---|
| `index.html` | The interactive viewer (single page, hash-routed: `#/` index, `#/task/{slug}` / `#/prompt/{v}` / `#/model/{m}` group views, `#/run/{n}` detail, `#/run/{n}/doc/{i}` single-document trace) |
| `posit/` | **Posit Cloud portal** (rendered Quarto website — sources in [`posit-src/`](posit-src/README.md), see its README): `index.html` landing, `experiment-log.html` (generated from the JSONL), `kanban.html`, `discussion.html`, `search.json`, `site_libs/`. Regenerate with `quarto render docs/posit-src`; rendered output is committed. |
| `assets/` | `site.css` + `site.js` — dependency-free, no CDN, no build step; dark "gradient night" theme via masthead toggle, `?theme=dark`, or system preference |
| `data/` | **Generated** — `meta.json`, `index.json` (run summaries), `runs/{n}.json` (full records) |
| `slides/` | **Scoring-method decks** (hand-written markdown) — worked example inputs/outputs + concise scientific explanations of every scoring method, written for parallel researchers who do not have time to read all the docs: field-type scoring, entity lists + bipartite matching, MAE/R² regression diagnostics, factuality audit, failure analysis, and how to read the experiment log |
| `configuration.md` | **Environment configuration guide** — per-provider (OpenRouter / Modal-vLLM / Ollama / generic) and per-trace-sink (Phoenix / Langfuse / Braintrust / LangSmith) setup for THIS repo and llm-mailroom together, with copy-paste recipes |
| `README.md` | this file |

## Viewer features

- **Sample-size-aware scoring** — every headline score carries a Wilson 95%
  CI (n=5 → ±27pp, n=509 → ±2.2pp) with the sample size shown; the
  **Δ vs best** column is colored only when the difference is statistically
  significant at 95% (two-proportion z-test), otherwise shown as "≈" — small
  samples are never presented as beating or losing to large ones.
- **Scoring reference card** — display bands (≥85% Strong · 60–85% Moderate ·
  <60% Weak), per-task headline formulas, each metric's calculation +
  meaning, a "sample sizes matter" explainer, and links to [`SCORING.md`](SCORING.md).
- **Group views** — `#/task/{slug}`, `#/prompt/{version}`, `#/model/{model}`:
  aggregates (runs / documents / tokens / best / median / worst), a
  grouped-by table (tasks → prompts, prompts → tasks), and the filtered run
  list. Task tags, prompt names, and models link to their group views
  everywhere.
- **Dashboard** — stat cards per task (best / median / worst + run link),
  filterable runs table (search + task/model/prompt + **minimum sample
  size**), score cells with band-colored %, raw value, CI + n, and
  composition line.
- **Run detail** — banded metric cards, task-specific **score composition**
  card, per-field content scores, per-subtype accuracy + confusion matrix +
  failure insights, a **Run-level diagnostics** card for extraction runs
  (raw list precision/recall/F1, date/duration/money MAE + R² vs ground
  truth, span-count drift, field-level error decomposition —
  `scores.diagnostics`, see [`SCORING.md`](SCORING.md) §4), and a per-document results
  table.
- **Trace view** — `#/run/{n}/doc/{i}` shows the full record: classification
  verdicts + reasoning, and — where applicable — **interpreted extraction
  scores** (what each metric means, type-aware field scoring, entity-list
  factuality audit with hallucination counts, CUAD category presence,
  ambiguous fields, and the raw predicted extraction), with prev/next
  navigation.
- **Agent kanban board** — a `#/board` tab rendering `MESSAGE_BOARD.md`
  (the cross-repo agent work-progress board: kanban lanes, GitHub-issue
  links, discussion log, archive) read-only for visual inspection
  (`build_site.py` emits `docs/data/board.json`).
- **Research memos** — a dedicated `#/memos` tab rendering `docs/memos/*.md`
  (the archived research memoranda: subtype-classification improvements,
  entity-extraction v2→v15, contracts-specialist v17→v18) with a memo
  selector and cross-memo companion links (`build_site.py` emits
  `docs/data/memos.json`).
- **OpenRouter benchmarks** — a dedicated `#/benchmarks` view with
  Artificial Analysis (intelligence/coding/agentic index rankings with
  pricing) and Design Arena (ELO/win-rate by category) data, fetched
  best-effort at build time (`--benchmarks-key`), with citation metadata and
  the availability caveat — so model candidates can be compared on benchmark
  evidence before running the eval loop.
- **Cost accounting** — real billed totals from an **OpenRouter activity-log
  export** (Settings → Activity Logs): every generation under the eval key
  (qwen + text-embedding-3-small) is attributed to the run whose completion
  timestamp is the next boundary after the generation time. The dashboard
  shows a cumulative-cost card (with export window), a **Cost** column
  (total + avg $/document + call counts) in the runs table, per-run billing
  in the Tokens & cost card, and group-view cost aggregates; runs outside
  the export window are explicitly marked "—" with instructions to export a
  fresh CSV. Ingest with:
  `python scripts/site/build_site.py --openrouter-csv <activity.csv>`
- **Dark mode** — light and dark themes share the same markup; the dark
  "gradient night" theme adds radial glows, gradient score bars and title,
  and tuned chips/tables. `?theme=light|dark` forces a theme (shareable).

## Rebuilding the data

`docs/data/` is DERIVED from `reports/experiment_log.jsonl`, exactly like
`reports/experiment_log.md` — never hand-edit it. After every run:

```bash
python scripts/site/build_site.py                              # regenerate docs/data/
python scripts/site/build_site.py --openrouter-csv openrouter_activity_2026-08-11.csv \
                                                                 # also bill costs from the activity export
python scripts/site/build_site.py --check                      # verify it is current
```

The index view is served by `data/index.json` (small); detail pages lazy-load
`data/runs/{id}.json`, so the site stays fast as the log grows.

## Enabling GitHub Pages (one-time, no Actions runners)

The site is committed to the repo and served directly from the `main` branch,
so no CI is involved:

1. GitHub → repo → **Settings → Pages**
2. **Source**: *Deploy from a branch*
3. **Branch**: `main` → `/docs` → **Save**
4. The site appears at `https://exios66.github.io/llm-entity-extraction/`
   with the Posit portal at `.../posit/`

## Posit Cloud deployment (complementary, no Actions)

The `posit/` portal is a Quarto website whose **sources live in `posit-src/`**
(theme, pages, `_pre-render.py` hook). Deploy from Posit Cloud:

```bash
quarto render docs/posit-src  # regenerates posit-src/_includes + _variables.yml,
                          # renders docs/posit/ (gitignored includes)
```

Then either push `docs/` (GH Pages serves it — the default path), run
`quarto publish quarto-pub` from `docs/posit-src/`, or deploy `docs/` as a static
site to Posit Connect. Full instructions: [`posit-src/README.md`](posit-src/README.md).

## Keeping the log and site in sync

The source of truth is `reports/experiment_log.jsonl`. The pipeline is:

```bash
# after every completed run:
python scripts/reporting/render_experiment_log.py   # -> reports/experiment_log.md
python scripts/site/build_site.py                   # -> docs/data/
```
