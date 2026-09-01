# AGENTS.md

Working guide for AI agents (and humans) contributing to
**llm-entity-extraction** — the prompt experiment loop environment for the
llm-mailroom legal document pipeline.

## Project in one paragraph

This repo measures how well prompt versions classify legal documents and
extract entities, one prompt at a time. Datasets (CUAD contracts, LegalBench
tasks) are synced into Braintrust; eval runners send real documents through
the LangChain agents (sorter, specialists, judge) via OpenRouter; every run
produces ONE append-only record in
`reports/experiment_log.jsonl` and a fully expanded markdown section in
`reports/experiment_log.md`. **Run sink: Langfuse PRIMARY (llm-dojo project, keys in `langfuse.env`) with the local Arize Phoenix server as fallback** — the human directive (2026-08-16): every `run_langfuse_*_eval.py` runner traces to Langfuse when its keys are configured and falls back to the local Phoenix OpenTelemetry endpoint when they are not (`src/tracing.py::resolve_tracer()`); the record's `tracing_backend` reports which one fired. Braintrust experiment/span logging is DISABLED by default
(`BRAINTRUST_LOGGING=disabled` — Braintrust stays read-only for dataset
hosting, so runs never consume its plan's scored-run/log-byte quota). Traces per run land in Arize Phoenix (`PHOENIX_TRACING=enabled` by default, local SQLite/in-memory, no subscription) and every LangChain LLM call can optionally auto-trace to LangSmith (`LANGSMITH_TRACING=true`). Langfuse mirrors remain available for backward compatibility but are no longer the default primary sink. Scoring is deterministic and
field-type-aware — never exact-match-on-extraction. The agents are
pip-installable (`pip install -e .`) so llm-mailroom's LangGraph architecture
imports and calls them directly; prompt versions are the experiment identity.

## Agent message board & inter-agent workflow — READ THIS FIRST, EVERY SESSION

`governance/MESSAGE_BOARD.md` is the living Kanban canvas shared by ALL
agents working in this repository: backlog / in_progress / blocked /
in_review / done lanes, a discussion log, and an audit archive. It is the
ONLY place where cross-agent task state lives — the single source of truth
for what is claimed, in flight, blocked, and done. **Every task, objective,
or experimental run in this repository MUST have a card, and every card MUST
be kept current with timestamps. An agent is NOT done until its card says
so.** This section is the full expected workflow: session pre-flight, the
task lifecycle, the inter-agent communication framework, and the
anti-trampling protocol that keeps concurrent agents from colliding.

### 1. Session protocol (pre-flight — at every session start)

1. **Read the board FIRST** — before starting ANY task, before writing any
   code, and before committing anything. Read the Kanban table, the
   discussion log, and the open GitHub issues: (a) cards already claimed by
   another agent, (b) cards that cover the work you were about to do, and
   (c) context posts that affect your work. Never duplicate or race a
   claimed card.
2. **Run the rule-4 sanity sweep** — `git status` (and any branches/running
   evals): any uncommitted or partially landed work that belongs to a card
   makes that card `in_progress`. Fix mislabeled cards at this moment —
   set Owner to whoever holds the work, timestamp it, and post a dated note
   in the discussion log. Uncommitted work on the board = an `in_progress`
   card, never `backlog`.
3. **Check for reused experiment names** (see §4) — if a name you planned
   appears in a claimed card or a recent discussion entry, it is taken;
   pick a distinct `_suffix` or a different surface.
4. **Announce intent** — post on the discussion board before claiming, so
   other agents see the slot being taken.

### 2. The task lifecycle — end-to-end (every card, every time)

**Phase 0 — Card first. No card = no work.** If your task has no card,
create one (next free `KANBAN-00N`), add it to the Kanban table, and claim
it — in the SAME session you start the work, not after. If your work
addresses the problem identified in an existing card (even partially, or
from a different angle), update THAT card instead — never a parallel card,
never a duplicate issue. Only add a NEW card when NO card covers the task.

**Phase 1 — Claim.** A card in `backlog` is claimed by: (a) commenting on
the GitHub issue if the card is synced (see §5), or posting to the
discussion board if it is board-only; (b) moving the card to `in_progress`
with Owner (agent name) + claimed date; (c) referencing the card in your
first commit (`MESSAGE BOARD: KANBAN-00N claimed`). ONE owner per card.

**Phase 2 — Work; card `in_progress` from the first edit.** The moment ANY
work exists for a card's scope — a first working-tree edit, an uncommitted
draft (prompt constant, test, script), a branch, a run that has started, or
a partially landed commit — the card MUST be `in_progress`, NOT `backlog`
(`backlog` means ZERO work has started). Label it before the code, never
after. Every lane change carries a timestamp (`YYYY-MM-DD`, matching the
day it happened), and the card's Status AND its Updated column/entry move
together.

**Phase 3 — Communicate DURING work.** Post to the discussion board at
every material event: decision made, result obtained, blocker hit, scope
changed, handoff to another agent (see the what-to-post-when table in §3).
A silent agent is an untrusted agent. Blocked = move the card to `blocked`
with the SPECIFIC blocker (missing key, waiting on a dataset, dependent on
KANBAN-00N), a timestamp, and what unblocks it.

**Phase 4 — Verify.** Tests pass (network-free suite), the A/B run landed,
and/or the release gate (`release.py --check`) is green. `git status` is
clean for the card's scope — stray diffs mean the card is still
`in_progress`, not done. Move the card to `in_review` when the work is done
but awaiting validation, linking the evidence (run, commit, PR).

**Phase 5 — Close: post the proof BEFORE claiming done.** A card may move
to `done` only when ALL of:
(a) work verified — tests / A/B / release gate, clean `git status`;
(b) `CHANGELOG.md` `[Unreleased]` entry exists in the SAME commit that
    ships the work (no changelog entry = no done);
(c) the card was moved to the Archive with its shipped version, commit and
    key result (the archive IS the record — never delete a card, and
    closed cards leave the open table);
(d) the discussion entry is timestamped;
(e) for synced cards, the GitHub issue was CLOSED (`gh issue close NNN`)
    in that same commit, with the closing comment naming the commit +
    CHANGELOG entry. Done card + open issue (or closed issue + unarchived
    card) is a board inconsistency — fix it immediately;
(f) no orphaned scope — anything discovered but NOT delivered (a new
    confusion cluster, a follow-on arm) spawned its own card BEFORE this
    one closed.
Experiments specifically: the claim, the run, and the closing entry must
ALL be on the board; never close out an experimental run without (i) the
run's KANBAN status + result timestamped, (ii) the
`reports/experiment_log.{jsonl,md}` regeneration, and (iii) the CHANGELOG
tie-in — in that order.

**Phase 6 — Finish protocol: the LAST action of every task/run.** Before a
task, objective, or experimental run is declared finished: update your
Kanban entry — move it to its final status (`done` / archive for completed
work, `blocked` if it ended stuck), record the timestamp, update the
Owner/result fields, and post the closing discussion entry. Only then
report completion to the user.

**Reopenings are visible.** A `done`/archived card can be reopened by
moving it back to `backlog` with a timestamped post explaining why
(regression, new data, superseded assumption) — and reopening its issue
with the Discussion post as the comment, in the same pass. History is never
deleted — reopen, don't rewrite.

### 3. Inter-agent communication framework

All cross-agent communication is centralized on the board; nothing that
carries task state lives in private channels. Channel hierarchy:

| Channel | Carries | Canonical for |
|---|---|---|
| `governance/MESSAGE_BOARD.md` (table + archive) / `governance/MESSAGE_BOARD_DISCUSSION.qmd` (log) | ALL task state: claims, lane moves, decisions, results, blockers, handoffs, reopenings — the Kanban table + Archive live in the markdown; the append-only discussion log lives as a color-coordinated Quarto doc (`.qmd`, newest at top; structured `::: {.entry data-date data-agent data-card}` blocks with inline links to issues/commits/memos) | EVERYTHING — the single source of truth |
| GitHub issues (label `kanban`) | mirror of a synced card's status + externally verifiable completion | synced cards' status (must never disagree with the board) |
| Commit messages | card references (`MESSAGE BOARD: KANBAN-00N ...` / `KANBAN-00N (vX): ...`) | which commit landed which card |
| `CHANGELOG.md` | release-level history | what shipped in which version |
| `docs/memos/*.md` | research findings worth archiving for collaborators | documented results |
| `reports/experiment_log.{jsonl,md}` | run data (scores, tokens, outputs) | experiment records |

What to post, and when — every entry is dated (`YYYY-MM-DD`), card-referenced
(`KANBAN-00N`), newest at top:

| Event | Post |
|---|---|
| Claim | owner + timestamp + planned run name (reserve it — §4) |
| Lane move | status change + timestamp + one-line why |
| Decision / result | what was decided or measured, with the numbers |
| Blocker | the specific blocker + what unblocks it |
| Scope change | what changed and why |
| Handoff | who is taking over, what state it is in |
| Reopen | why, with the card moved back to `backlog` |

**Discussion log is append-only.** Newest at top, always timestamped,
always card-referenced (`KANBAN-00N`). Never edit a past entry — post a
correction. **Semver sync always:** cards name their target release; when a
release ships (`scripts/release.py --bump`), sweep the board in the same
session — landed cards → Archive under that version (timestamped), open
cards → re-targeted to the next release. The board and `CHANGELOG.md` must
never disagree.

### 4. Anti-trampling protocol (concurrency safety)

Rules that keep two agents from ever working the same thing at the same
time — read them as a contract, not a suggestion.

- **One owner at a time.** Never start work on a card owned by another
  agent. Offer help on the discussion board; take over only by handoff.
  A card is claimed by its Owner field + timestamp; an unclaimed card is
  fair game but must be claimed (Phase 1) before its first edit.
- **A card owns its files.** Claiming a card reserves its scope in the
  working tree. If your work touches files another card owns (its prompt
  constant, its runner, its tests), coordinate on the board first — post
  the intent, wait for the owner's acknowledgment or handoff. Build off
  cards, never around them: if a card your work depends on is
  `in_progress` elsewhere, wait or coordinate — do not fork the work.
- **Experiment-name reservation — claim the name BEFORE the run.** Braintrust
  silently suffixes re-runs (`-a1b2c3d4`), so two agents launching under
  the same name produce two experiments wearing one label — the classic
  silent collision. Every eval run's name (`{model-slug}_{prompt-version}[_suffix]`)
  is reserved in the card's claim entry and/or a discussion post at the
  moment the run is planned, not when it starts. Same-name race: the later
  timestamp wins; the loser renames with a `_suffix` and posts the
  correction. At every session start, check names in flight (§1.3).
- **One run, one owner.** A running eval belongs to the card that claimed
  it; never start a run on a card another agent is running. `--dry-run`
  before paying for LLM calls on unfamiliar evals.
- **Task-relation rule — update, don't duplicate.** Work that addresses the
  problem in an existing card updates THAT card (comment on its issue /
  post to the discussion board, move its status to reality, extend its
  summary). Never create a parallel card or duplicate issue for covered
  work.
- **Conflict rule.** If two agents updated the same card, the later
  timestamp wins the lane; the overwritten party posts a reconciliation
  entry rather than reverting blindly.
- **No silent completion.** A card is not done until its closing entry is
  on the board (§2 Phase 5/6) — "done" without a board record is, to every
  other agent, still in flight.

### 5. GitHub issue sync (critical / high-priority cards)

Critical, high-priority, and cross-repo cards are routed to GitHub issues
(label `kanban`) so agents can open/close them like normal issues while the
board remains the source of truth. Board-only cards (small,
single-session, low-risk) do NOT need issues.

- Open the issue FIRST (in the repo where the work lands), then write its
  link into the card: `gh issue create --label kanban --title "KANBAN-00N:
  <task>" --body "<card summary + evidence>"`. **Every synced card's `Issue`
  column carries the FULL markdown link to its own dedicated issue**
  (`[#NNN](https://github.com/Exios66/<repo>/issues/NNN)`) — one card = one
  issue; never a bare number, never a shared issue.
- Cross-reference both ways: the issue body names its `KANBAN-00N`; the
  card names its issue link. They must never disagree about status — a lane
  move on the card is mirrored on the issue (claim → comment, blocked →
  blocker comment, done → closed).
- Close the issue (`gh issue close NNN`, closing comment naming the commit
  and CHANGELOG entry) in the SAME commit that archives the card; reopen it
  when a card is reopened (comment = the discussion post).
- Sync sweep: after any board edit, audit the table — every open card has a
  link in its `Issue` column, and every link points at an issue that is
  OPEN (`gh issue list --label kanban`), except archived cards, whose
  issues are CLOSED. A missing link = an unsynced card = not ready for
  assignment.

## Environment & setup

- Python 3.10+ (tested on 3.13). Deps ship as purpose-scoped batches:
  `requirements.txt` is the CORE floor only; task batches live in
  `requirements/<batch>.txt` mirroring pyproject extras (`tracing`, `evals`,
  `datasets`, `reporting`, `embeddings`, `dev`, `all` — pinned by
  `tests/test_dependency_manifests.py`). The repo is also a Python package
  (`pyproject.toml` — packages `agents`, `src`, `config`).
- Two dotenv files, both gitignored, both living under `config/environments/`
  (templates committed as `.example`, live files gitignored): `braintrust.env`
  (Braintrust org/project/keys — the source of truth for config, see
  `src/braintrust_config.py`) and `.env` (OpenRouter key + provider overrides).
  Copy from the `.example` files. `src/env_utils.py` loads both (plus the
  shared `ENV_DIR` / `BRAINTRUST_ENV_FILE` / `DOTENV_FILE` /
  `LANGFUSE_ENV_FILE` path constants and `resolve_env_file()` for CLI
  `--env-file` args); real shell env vars always win.
- **Externally-funded OpenRouter key (research funding)**: `RESEARCH_FUNDING_OPENROUTER_API_KEY`
  in `.env` pays with external research funding and is ONLY reachable through
  the `--research-funding-key` flag on the eval runners (default `OPENROUTER_API_KEY`
  is untouched). The gate (`src/env_utils.py::assert_production_run`) HARD-REFUSES
  dry-runs and pilot-scale samples (fewer than 100 rows, or less than the full
  dataset when it is smaller) with a `SystemExit` before any LLM call — external
  funding is reserved for fully-ready production runs. `resolve_openrouter_key()`
  resolves either key; `add_research_funding_flag(parser)` registers the flag.
- **Arize Phoenix tracing** (default, local): `PHOENIX_TRACING=enabled` (default)
  + `PHOENIX_ENDPOINT` (default http://localhost:6006/v1/traces) + `PHOENIX_SERVICE_NAME`
  in `.env`. Phoenix is Apache/Elastic-licensed, runs as a single local process
  with SQLite/in-memory storage, OpenTelemetry-native, no Docker/multi-service
  stack, and requires no cloud subscription. Spans are poured in, inspected
  locally, and discarded by deleting the DB file. Enable LangChain OpenTelemetry
  instrumentation via `LANGCHAIN_TRACING_V2=true` + `OTEL_EXPORTER_OTLP_ENDPOINT`
  pointing at Phoenix for full LLM call traces. Full documentation — including
  the **resume / checkpoint / queue / cache** cost-efficiency configuration
  (manifest resume + header contract, append-only experiment-log checkpoint,
  HITL annotation queue, embedding-cache reuse, `--dry-run` /
  `assert_production_run` cost gates) — lives in `docs/wiki/Phoenix-Tracing.md`;
  env-var templates are in `config/environments/.env.example`.
- **LangSmith tracing** (optional, off by default): set `LANGSMITH_TRACING=true`
  + `LANGSMITH_API_KEY` + `LANGSMITH_PROJECT` in `.env` (see `.env.example`) and
  every LangChain LLM call (sorter/specialists via OpenRouter) auto-traces to
  that LangSmith project — verified to coexist with Braintrust's
  `setup_langchain` patch. The `llm-mailroom` project
  (`bbf45300-ca81-4126-99a0-2e02a49c2ceb`) additionally receives OpenRouter's
  OWN OTEL export (runs named `OpenRouter Request` / `provider attempt N: …`
  with `provider_responses` metadata) when the OpenRouter dashboard integration
  is configured — that export is where per-provider 429/limit spans come from;
  analyze with the `langsmith` SDK (`Client(api_key=…).list_runs(project_name=…)`).
- Vision classification needs poppler (`brew install poppler` /
  `apt install poppler-utils`) for PDF→PNG rendering.
- `OPENROUTER_BASE_URL` can point at any OpenAI-compatible endpoint (Ollama,
  vLLM) — used for testing without paying.
- Optional but recommended: the `embeddings` batch
  (`pip install -r requirements/embeddings.txt`) — the semantic embedding
  rescue then runs the local `all-MiniLM-L6-v2` model (free, offline,
  reproducible) instead of paid OpenRouter embedding calls. Both
  routes are verified; the fallback triggers automatically when the local
  model is unavailable.

```bash
python3 -m venv .venv && source .venv/bin/activate   # recommended; .venv/ is gitignored
pip install -r requirements.txt        # CORE only — batches: README §Setup
pip install -r requirements/all.txt    # + every non-dev batch (old full-install behavior)
pip install -e .        # editable install: agents/src/config importable from ANY codebase
                        # (e.g. llm-mailroom's LangGraph) — new changes picked up instantly
cp config/environments/braintrust.env.example config/environments/braintrust.env   # fill in creds
cp config/environments/.env.example config/environments/.env                       # fill in OPENROUTER_API_KEY
```

## Command cheatsheet

```bash
# Sync corpora -> Braintrust datasets
python scripts/datasets/stream_cuad_to_bt.py --limit 12 --dry-run   # preview first
python scripts/datasets/stream_cuad_to_bt.py                        # all 510 PDFs (page images)
python scripts/datasets/stream_cuad_to_bt.py --text-only            # 510 rows, TEXT only (no poppler)
python scripts/datasets/download_cuad_pdfs.py --dry-run             # keep the corpus locally
python scripts/datasets/stream_legalbench_to_bt.py --limit 6 --dry-run
python scripts/datasets/stream_legalbench_tasks_to_bt.py --tasks all
python scripts/datasets/stream_legalbench_tasks_to_bt.py --tasks hearsay  # e.g. the hearsay task
                                    # (binary Yes/No, 5 train rows / 95 test, 5 slices; reruns
                                    # UPSERT via deterministic row ids — never duplicate)

# Evals (each tests ONE prompt version; naming is {model-slug}_{prompt-version}[_suffix])
# Hierarchical doc-class eval (KANBAN-033): extended 7-class primary dimension
# (incl. merger_agreement from MAUD) + doc_subclass second level (consideration
# type for merger agreements — MAUD expert GT; record type for corporate
# records — content-detected). Data: data/maud/*.jsonl (152 merger agreements
# + 25,827 per-question rows), data/s1_corporate_records/*.jsonl (EDGAR S-1
# corporate-record exhibits), CUAD contracts. Tertiary level dropped by
# design (data-necessity rule): MAUD categories + exhibit codes are metadata.
python scripts/eval/run_langfuse_docclass_eval.py --dry-run
python scripts/eval/run_langfuse_docclass_eval.py --local-dumps data/maud/contracts.jsonl,data/s1_corporate_records/corporate-records.jsonl \
    --stratified 120 --seed 42
# Correspondence-only Enron eval (KANBAN-103): subclass + sentiment on
# Lucius-Morningstar/enron-correspondence-dedup. Default 200 stratified,
# seed 42; Braintrust traces ON. Reserved name
# qwen3.7-flash_sorter_docclass_correspondence_v0_enron200_s42.
python scripts/eval/run_correspondence_eval.py --dry-run --stratified 200 --seed 42
python scripts/eval/run_correspondence_eval.py --stratified 200 --seed 42
python scripts/datasets/stream_maud_to_bt.py --local-dump data/maud/          # rebuild MAUD dumps
python scripts/datasets/stream_s1_exhibits.py --max-filings 40 --local-dump data/s1_corporate_records/  # EDGAR S-1 exhibits
python scripts/eval/sync_langfuse_datasets.py --maud --s1 --dry-run           # mirror dumps into Langfuse
# Run sink is Langfuse + LangSmith + the repo experiment log — Braintrust
# experiment/span logging is OFF by default (BRAINTRUST_LOGGING=disabled), so
# the run_langfuse_*_eval.py runners are the PRIMARY eval path (per-document
# Langfuse traces with scores; every LLM call also auto-traces to LangSmith).
# The run_*_eval.py runners are the local-scoring / manifest-resume path —
# with Braintrust logging disabled they skip braintrust.Eval entirely; opt
# back in per run with BRAINTRUST_LOGGING=enabled.
# Langfuse projects (two environments, two purposes):
#   - llm-dojo: where THIS repo's prompt iterations run — individual prompt
#     improvements and enhancements, evaluated one prompt version at a time.
#     ALL eval runs trace here (keys in langfuse.env are project-scoped and
#     route every trace to llm-dojo; the LANGFUSE_PROJECT label and the code
#     default in src/langfuse_config.py are both "llm-dojo").
#   - llm-mailroom (llm-mailroom-experiments): EXCLUSIVELY for testing and
#     improving the FULL mailroom pipeline (the llm-mailroom repo). Insights
#     and results from llm-dojo iterations are applied there — prompt
#     enhancements flow llm-dojo -> llm-mailroom, never the reverse.
#   Prompt iteration sync: after every prompt iteration, mirror the versioned
#   prompts into Langfuse (idempotent; each PROMPT_VERSIONS key becomes a
#   text prompt; repeatable --env-file adds projects, e.g. a key file for the
#   llm-mailroom project when pipeline tests need the same prompt versions):
#   python scripts/eval/sync_langfuse_prompts.py            # -> llm-dojo (langfuse.env)
#   python scripts/eval/sync_langfuse_prompts.py --env-file langfuse.env \
#       --env-file langfuse-llm-mailroom.env               # -> both projects
#   (add --dry-run to preview; a missing env file / missing keys is skipped
#   with a warning, so another project is a drop-in — create an env file
#   with that project's key pair and pass it on the command line.)

# PRIMARY — Langfuse sink (one trace per document with scores) + LangSmith spans
python scripts/eval/run_langfuse_subtype_eval.py --dataset mailroom-cuad-contracts-full \
    --stratified 250 --seed 42 --sorter-prompt-version sorter_v11  # sorter-only, even across classes
python scripts/eval/run_langfuse_chained_eval.py --sample 5 --seed 42 \
    --sorter-prompt-version sorter_v6 --extractor-prompt-version contracts_specialist_v11
python scripts/eval/run_langfuse_extraction_eval.py --dataset mailroom-cuad-contracts \
    --prompt-version contracts_specialist_v11 --chunked --manifest data/manifests/extract_chunked.jsonl
python scripts/eval/run_langfuse_classification_eval.py --dataset mailroom-cuad-contracts \
    --prompt-version sorter_v6
python scripts/eval/run_langfuse_classification_eval.py --dataset mailroom-lb-hearsay \
    --prompt-mode task --valid-classes Yes,No --prompt-version legalbench_task_v0  # LegalBench task mode

# Directly-mirrored ContractEval benchmark (arXiv 2508.03080, KANBAN-052): the CUAD
# test split, one (contract, question) call per row, faithful full-context (temp 0,
# max_tokens 5000, --max-input-chars 0 = no cap), ContractEval's EXACT rubric (F1/F2,
# Jaccard over positives, false-"no related clause" rate over the paper's 1,244
# positives + per-category). Build the dataset first (network, ~18MB), then run:
python scripts/datasets/build_contracteval_testset.py --dry-run   # 4,182 pairs / 102 contracts / 41 cats
python scripts/datasets/build_contracteval_testset.py
python scripts/eval/run_langfuse_contracteval_eval.py --dry-run
python scripts/eval/run_langfuse_contracteval_eval.py --sample 100 --seed 42   # pilot
python scripts/eval/run_langfuse_contracteval_eval.py --model gpt-4.1-mini --research-funding-key  # full
python scripts/reporting/run_contracteval_report.py   # our runs vs the 19-model Table III + per-category

# LOCAL / RESUME path (no Braintrust experiment; Braintrust logging off by default):
python scripts/eval/run_classification_eval.py --dataset mailroom-cuad-contracts \
    --input-mode vision --prompt-version sorter_vision_v0          # vision, all pages
python scripts/eval/run_classification_eval.py --dataset mailroom-cuad-contracts \
    --input-mode text --prompt-version sorter_v0                    # full text
python scripts/eval/run_extraction_eval.py --dataset mailroom-cuad-contracts \
    --prompt-version contracts_specialist_v2 --manifest data/manifests/extract_v2.jsonl
python scripts/eval/run_chained_eval.py --dataset mailroom-cuad-contracts \
    --sorter-prompt-version sorter_v5 --extractor-prompt-version contracts_specialist_v11 \
    --manifest data/manifests/chained_5.jsonl                      # sorter -> extractor
python scripts/eval/run_chained_eval.py ... --handoff-scope none   # legacy handoff (no subtype cue)
python scripts/eval/run_chained_eval.py ... --handoff-scope ground_truth  # error-propagation ablation:
                            # specialist ALSO runs with the GT-subtype handoff; scores.ablation
                            # splits sorter routing loss from specialist error
python scripts/eval/run_model_matrix.py --task subtype --models qwen/qwen3.7-flash,deepseek/deepseek-v4-flash \
                            --prompts sorter_v5,sorter_v6 --sample 10 --seed 42  # cross-model matrix
python scripts/eval/evaluate_prompt_version.py --dataset mailroom-cuad-contracts \
    --prompt-a sorter_vision_v0 --prompt-b sorter_vision_v1         # A/B

# HITL annotation queue (llm-dojo mirror): filter IN low performers / failed classifications
python scripts/eval/run_annotation_queue.py build --dry-run --threshold 0.85   # extraction: scan + rank, no writes
python scripts/eval/run_annotation_queue.py build --threshold 0.85             # extraction: create queue + enqueue PENDING items
python scripts/eval/run_annotation_queue.py build --task subtype --dry-run     # sorter: failed doc_type/subtype classifications
python scripts/eval/run_annotation_queue.py build --task subtype               # sorter: enqueue classification failures
python scripts/eval/run_annotation_queue.py status [--task subtype]            # queue items + scores + trace URLs

# Wiki (version-controlled here, pushed to the public GitHub wiki)
./docs/wiki/sync-wiki.sh                # push docs/wiki/ -> https://github.com/Exios66/llm-entity-extraction/wiki

# Site data (derived from the experiment log; never hand-edit docs/data)
python scripts/site/build_site.py          # regenerate docs/data/ (index, meta, runs/, trends.json, prompts.json, benchmarks.json)
python scripts/site/build_site.py --check  # verify it is current
python scripts/site/build_site.py --benchmarks-key $OPENROUTER_API_KEY  # include live OpenRouter benchmarks (best-effort)
node tests/assets/site_render_audit.js     # headless render audit of EVERY view (after any site.js edit)

# Releases (mechanical steps automated; the commit/tag are always explicit)
python scripts/release.py --check                     # validate state (version == changelog header, site data, tests, audit)
python scripts/release.py --bump minor --note "<summary>"   # move [Unreleased] -> [vX.Y.Z], bump pyproject, print commands
python scripts/release.py --bump patch --note "<summary>" --dry-run
# Note: docs/assets/site.js + index.html are HAND-maintained (trend charts,
# cost-vs-quality scatter, failure-mode stacked bars, #/prompts diff view).
# Charts: log-scale cost axis, Catmull-Rom smoothing, curated palette/dashes,
# hover tooltips + click-to-run on every point; nav tasks live under the
# single "tasks" dropdown (populated from meta.tasks). Run
# `node tests/assets/site_render_audit.js` after any site.js edit.

# Reporting (all offline except the two Braintrust fetchers)
python scripts/reporting/report_generator.py --experiment <name>        # fetches Braintrust
python scripts/reporting/confusion_matrix.py --experiment <name>        # fetches Braintrust
python scripts/reporting/score_extraction_manifest.py data/manifests/extract_v2.jsonl
python scripts/reporting/render_experiment_log.py                       # rebuild md log from jsonl

# Tests (never hit the network) — surgical by default; full suite only for significant changes / releases
python -m pytest tests/test_<area>.py -v                       # surgically relevant area
python -m pytest tests/ -v                                     # full suite (significant changes / release gate only)
```

Always run `--dry-run` on an unfamiliar eval before paying for LLM calls.

## Architecture & data flow

```
HF/GitHub corpora ──stream_cuad/legalbench──▶ Braintrust datasets
                                                  │
local PDFs ──--pdf-dir──┐                        │ load_braintrust_dataset()
                         ▼                        ▼
               run_*_eval.py ──▶ LangChain agent ──▶ OpenRouter LLM
                    │                                │
                    │                 setup_langchain() traces spans
                    ▼                                ▼
deterministic scoring          Braintrust experiment
              (llm-dojo-scoring pkg,          │
               via src/*.py shims)            │
                    │                             │
                    ▼                             ▼
   data/manifests/*.jsonl ◀── resumable ──  report_generator / confusion_matrix
                    │
                    ▼
   reports/experiment_log.{jsonl,md}   (append-only; md rebuilt by render script)
```

Key modules:

| Module | Responsibility |
|---|---|
| `src/taxonomy.py` | loads `config/taxonomy.yaml` — doc classes, field types, agent→model mapping, thresholds. Changing the taxonomy = YAML edit, not code. |
| `src/prompts.py` | ALL prompts, versioned in `PROMPT_VERSIONS`; `get_prompt(version)`, `list_prompts()`. The version key IS the experiment identity. |
| `src/field_scoring.py` | re-export shim → `llm_dojo_scoring.field_scoring` (field-type-aware content scorer: date/money/id/name/free_text/entity_list (bipartite matching), embedding rescue (local sentence-transformers, OpenRouter fallback, empty-string guard), factuality verification, ambiguous band). |
| `src/dojo_config.py` | wires `config/taxonomy.yaml` into the `llm_dojo_scoring` package `Settings` at import (thresholds, cost table, type coercion, `LLM_DOJO_SCORING_CONFIG` escape hatch). |
| `src/dojo_compat.py` | docclass failure-mode classifier `classify_failure(doc_type_ok, subclass_ok, predicted_subclass)` (positional-boolean contract, `None` on success). |
| `src/cuad_ground_truth.py` | CUAD 41-category catalog → per-document expected fields (type-aware by CUAD folder) + YES/NO presence expectations + `build_subtype_handoff()` (the subtype-scoped specialist cue used by `--handoff-scope subtype`). |
| `src/master_labels.py` | loader for the curated master ground-truth CSV (`master_clauses.csv`, default the repo-local `data/cuad/master_clauses.csv`; `MASTER_LABELS_CSV` env / `--master-labels` override it; sibling `../llm-mailroom/data/cuad/` kept as fallback) — per-category NORMALIZED answers ("5/8/14", "2 years") preferred over raw clause text by the MAE diagnostics; degrades to `{}` when absent. |
| `src/metrics.py` | re-export shim → `llm_dojo_scoring.diagnostics` (run-level extraction diagnostics `scores.diagnostics` in the experiment log): raw list precision/recall/F1 (macro + micro), field exact/partial/miss error decomposition + per-field presence, date/duration MAE (days) + money MAE (USD) with median + per-field buckets + pair counts, R² for dates/durations, span-count drift (MAE + signed mean). Consumes the per-row composite; the experiment-log renderer and the site display it. |
| `src/monte_carlo.py` | zero-spend robustness simulation primitives over the joint reasoning corpus (committee voting, confidence-gated escalation, paired-bootstrap prompt ablation, failure-pipeline sim, exemplar mining — KANBAN-048). |
| `src/langfuse_tracing.py` | Langfuse mirror tracer: one trace per document (session-scoped deterministic id), `agent_observation()` opens one span per pipeline agent with its designated task scores attached to that observation; graceful no-op when keys are missing. |
| `src/experiment_log.py` | append-only JSONL + markdown renderer (tables, confusion matrices, scoring matrices, outputs, failure insights); `render_full_log()` for the rebuild; the append/git-snapshot/mean/tokens core re-exports `llm_dojo_scoring.experiment` + `.cost`. |
| `src/correspondence_eval.py` | Enron correspondence eval primitives (KANBAN-103): blind↔GT join on `filename`, subclass-stratified sample, sentiment label/score scoring, predicted↔GT field alignment. |
| `src/evaluation.py` | dataset validation, fingerprints, `ManifestStore` (thread-safe JSONL resume checkpoints), adaptive `resolve_concurrency`, `call_with_rate_limit_retry`. |
| `src/scorers.py` | re-export shim → `llm_dojo_scoring.classification` (deterministic scorers exact_match, failure, `normalize_label`) + the local `cost` scorer and name registry. |
| `src/score_emitter.py` | bridge → `llm_dojo_scoring.emitter` + `.pruning` (KANBAN-061 unified layer): `build_emitter()` (JSONL manifest sink + inert-unless-configured Langfuse), `emit_run_scores()` (registry-validated; unknown/None names returned as skipped, never dropped), `dashboard_names()` / `headline_names()` tier-capped views. |
| `src/braintrust_utils.py` | Braintrust HTTP: list/fetch experiments, load/upload datasets, attachment handling. |
| `agents/` | LangChain agents: `BaseAgent` (structured output, vision, `_last_usage`, head+tail `truncate_input`), `SorterAgent` (doc_type + 25 contract subtypes, default `reasoning_effort="medium"`, `SUBTYPE_EQUIVALENCES`), specialists (per-class schemas), `JudgeAgent` (offline classification/completeness/correctness). |

## Scoring model (read before touching scorers)

The canonical, formula-level reference for every scorer and metric is
**`docs/SCORING.md`** — where scoring lives (the **`llm-dojo-scoring` package**,
pinned `@v0.10.0` and shared with llm-mailroom; the local `src/` modules are
thin re-export shims), classification, binary, multiclass, subtype, docclass
hierarchical, task-aware (MAUD / LegalBench / court opinions / chained), the
field-type-aware content scorer, factuality audit, judge calibration, chained
stage trackers + ablation, A/B deltas, token/cost accounting, the Monte Carlo
robustness suite, and bootstrap CIs. **Never edit the scoring algorithm in the
shims** — change the shared `llm-dojo-scoring` package (upstream repo) and
re-pin the dependency. The rules below are the invariants:

- **Content accuracy** — per-field deterministic scores by type
  (see README "Scoring"); entity lists via optimal bipartite matching
  (Hungarian) over pairwise similarity, threshold 0.6.
- **Partial ground truth** — CUAD clause-QA labels are partial samples of the
  document. List fields in `partial_gt_fields` (`parties`,
  `key_obligations`, `termination_clauses`) are scored by **ground-truth
  coverage** (recall over matched labels), NOT F1, which would penalize
  correct extractions. Raw precision/recall/F1 always stay in
  `entity_list_scores`.
- **Containment fields** — `containment_fields` (`governing_law`,
  `term_length`, `renewal_terms`) are scored by expected-within-predicted
  token containment.
- **Factuality guard** — every predicted list item must match a GT label OR
  be grounded in the source document (token coverage ≥ 0.7). Neither ⇒
  hallucination ⇒ drives `verified_precision` down.
- **Ambiguous band** `[0.5, 0.85]` — fields in this band trigger the optional
  `--judge` LLM pass.
- **Tracker consistency rule** — the per-field score, the `*_f1` tracker, and
  `overall_extraction_score` must all report the SAME list score. Registered
  Braintrust scorers are trivial lookups on the locally computed composite —
  never recompute on the Braintrust side.
- **Subtype equivalence** — the subtype eval reports BOTH strict accuracy
  (`subtype_accuracy`, exact CUAD-folder key) and family-level accuracy
  (`subtype_accuracy_equiv`; `equivalent_subtypes()` honors
  `SUBTYPE_EQUIVALENCES`: reseller↔distributor, maintenance↔license,
  development↔license, affiliate↔joint_venture). Strict stays the
  discriminating signal; equiv recognizes defensible family routing.
- **Docclass hierarchy** — the docclass eval scores BOTH `doc_type_accuracy`
  and `subclass_accuracy` (rows without a subclass GT are unscored, not
  penalized), with `subclass_accuracy_equiv` honoring `DOC_SUBCLASS_EQUIVALENCES`
  (mixed_cash_stock ↔ mixed_cash_stock_election) and per-subclass accuracy +
  support counts; failure modes are `doc_type_miss` / `subclass_miss`
  (`src/dojo_compat.py`).
- **Task-aware scoring** — `llm_dojo_scoring.tasks::score_task` dispatches by
  task kind (MAUD consideration strict/equiv, LegalBench binary P/R/F1,
  multiclass macro/micro, court opinions, chained composite 0.25/0.75);
  unknown MAUD consideration values degrade to `other` (the GT-gap convention).

## Experimental testing workflow (the loop)

1. **Diagnose with data** — read `reports/experiment_log.md` (or the jsonl)
   for the last runs; identify the failure pattern (per-field scores,
   confusion matrices, `failure_insights` reasoning on failed rows, model
   reasoning quotes). Fetch full traces from Braintrust when the stored
   reasoning is truncated.
2. **Change ONE thing** — new prompt version (constant + `PROMPT_VERSIONS`
   entry in `src/prompts.py`), config flag, or scorer rule. The version key
   IS the experiment identity; never mutate a prompt string after it has run.
   Keep the change surgical and cite the data that motivates it in the
   prompt's section banner comment.
 3. **Unit-test the change** — mock-level tests (prompt content assertions,
    option-list ↔ schema-enum wiring tests, runner smoke tests). Run the
    surgically relevant tests (`python -m pytest tests/test_<area>.py -q`)
    before spending money — not the full suite (that is reserved for
    significant changes / the release gate).
4. **Dry-run** — `--dry-run` on the eval runner to confirm the plan
   (dataset size, prompt versions, experiment name).
5. **Run a cheap pilot** — small sample with the same seed as the previous
   run (e.g. `--sample 5 --seed 42`) so results are directly comparable.
6. **A/B on identical rows** — same dataset, same seed, different prompt
   versions; compare strict + equiv + cost + output cleanliness. Only prompt
   versions validated this way belong in a release.
7. **Full-sample run when meaningful** — e.g.
   `--stratified 200 --seed 42` on `mailroom-cuad-contracts-full` (8 docs per
   subtype × 25). Same-sample comparisons are the ONLY valid accuracy
   comparisons — never compare across different samples.
8. **Log & document** — verify the record in `reports/experiment_log.jsonl`
   (see "After every run" below), then update `CHANGELOG.md` (see "Release
   workflow"). Then close out the run on the message board: move its KANBAN
   card to the correct status with a timestamp and a dated discussion entry
   (result, scores, verdict) BEFORE reporting the run as finished.

## After every run (experiment log upkeep)

The eval runners append to `reports/experiment_log.jsonl` automatically. The
markdown log is DERIVED — after every completed run:

```bash
python scripts/reporting/render_experiment_log.py   # rebuild reports/experiment_log.md
python scripts/site/build_site.py                   # rebuild docs/data (the GH Pages site data)
```

Then commit + push — **GitHub Pages serves `/docs` from `main`**, so the
experiment-log site updates on every push. The log files themselves
(`reports/experiment_log.{jsonl,md}`) are gitignored — only the derived
site data is committed:

```bash
git add docs/data
git commit -m "EXPERIMENT: <experiment_name>"
git push origin main
```

Before declaring the run finished: timestamped card update + discussion
entry on `governance/MESSAGE_BOARD.md` (see the message board section above).

**Mirror sync into llm-mailroom** (the synced copy at
`docs/reports/experiments/experiment_log.md` + its own GH Pages sync):

```bash
cd ../llm-mailroom
PYTHONPATH=src python -c "from legalbench.experiment_log import regenerate, default_log_path; regenerate(default_log_path())"
git add docs/reports/experiments/experiment_log.md
git commit -m "DOCS SYNC: experiment log re-synced"
git push origin main
```

Verify the record is COMPLETE before moving on:

- `reports/experiment_log.jsonl` gained exactly ONE new line (experiment
  name, model, git snapshot, prompt version(s), data source + fingerprint,
  ALL run parameters incl. `reasoning_effort` / `max_input_chars` /
  `stratified`, tokens/cost, all scores).
- The markdown section renders: metadata, data source, parameters, tokens,
  scores + breakdowns, per-document results, scoring matrices, confusion
  matrices, model outputs — and for subtype runs: per-class accuracy table
  plus **Failed classification insights** (each failed row with its failure
  mode and the model's FULL reasoning).
- Failed rows carry full reasoning (`failure_insights` / 4000-char span);
  successes carry a bounded excerpt. If a record lacks reasoning on failures,
  backfill it from the Braintrust LLM spans before regenerating.
- Never hand-edit `reports/experiment_log.md` — regenerate it.

## Release workflow (semantic versioning + tag)

The changelog follows [Keep a Changelog](https://keepachangelog.com/) and
semver; every release maps to ONE tagged commit (`vX.Y.Z`), and the tag must
match the CHANGELOG header exactly. The mechanical steps are automated by
`scripts/release.py` — the commit/tag are always explicit git commands.

### Changelog discipline (automatic, per commit)

- **Every behavior-changing commit carries its `[Unreleased]` entry in the
  SAME commit** — `### Added` / `### Changed` / `### Fixed` bullets naming
  files, prompt versions, and the data-backed results that motivated them
  (accuracy numbers, sample sizes, seeds). Docs-only and derived-artifact
  regenerations (log/site timestamps) do not need entries.
- Structure bullets exactly like the existing history: bold lead-in,
  backticked file/flag names, and concrete numbers where they exist.
- Bump rules (semver): **major** = breaking architecture/output-contract
  changes; **minor** = new features (new prompt versions, new eval runners,
  new dataset modes, new site capabilities); **patch** = bug fixes (scoring
  guards, prompt regressions, site display fixes).

### Release steps (vX.Y.Z)

1. **Update `CHANGELOG.md`** — `scripts/release.py --bump <patch|minor|major>
   --note "<summary>"` converts the accumulated `[Unreleased]` entries into
   `## [vX.Y.Z] - <date>`, adds the `[vX.Y.Z]:` release link, and keeps an
   empty `[Unreleased]` placeholder for future entries. `--dry-run` previews
   without writing; the script refuses to run on a dirty tree.
2. **Bump `pyproject.toml`** — the script does this automatically; the
   version MUST equal the latest CHANGELOG header (`release.py --check`
   enforces it).
3. **Update repository documentation when the change touches it** —
   `README.md` (layout tree, command examples, prompt tables, the Website
   section), `docs/README.md` (the site's own doc), `docs/SCORING.md` (formula/
   metric changes), and this `AGENTS.md` itself (workflow/architecture
   changes). Never skip docs that describe the thing that changed.
   Sweep `governance/MESSAGE_BOARD.md`: move shipped cards to the Archive under this
   version, re-target open cards to the next release.
4. **Regenerate derived artifacts** — `render_experiment_log.py` (new runs)
   + `scripts/site/build_site.py` (site data) + the headless render audit
   (`node tests/assets/site_render_audit.js`).
 5. **Run the full suite** — a release is the definition of a significant
    change, so the full gate applies: `python -m pytest tests/ -q`
    (network-free) and
    `python scripts/release.py --check` (version/changelog consistency, site
    data freshness, tests, render audit).
6. **Commit** — one commit covering changelog + docs + pyproject + derived
   artifacts, message `vX.Y.Z: <summary>`.
7. **Tag and push** — annotated tag matching the changelog header exactly;
   pushing main updates the GH Pages site (`/docs` served from `main`):
   ```bash
   git tag -a vX.Y.Z -m "vX.Y.Z — <summary>"
   git push origin main --tags
   ```
8. **Mirror sync into llm-mailroom** (synced experiment log + its docs):
   run the llm-mailroom `legalbench.experiment_log.regenerate()` command from
   the "After every run" section, then commit + push there.
9. Verify the tag exists on GitHub and the README/CHANGELOG/site render
   correctly (https://exios66.github.io/llm-entity-extraction/).

## Experiment log mechanics

- `reports/experiment_log.jsonl` is the source of truth: one JSON line per
  run, append-only, never rewritten (the one exception: a documented
  one-time backfill to enrich historical records with full failure reasoning,
  fetched from Braintrust LLM spans — record it in the changelog if used).
  The markdown log is DERIVED and rebuilt whole with
  `python scripts/reporting/render_experiment_log.py`.
- Every record carries: git snapshot (`git_snapshot()`), model, prompt
  version(s), data source + fingerprint, all run parameters, tokens/cost,
  all scores, per-row results including the model's predicted outputs.
- Subtype runs additionally carry `scores.sorter.failure_insights`
  (`mode_counts` + per-failed-row `{expected, predicted, mode,
  equiv_recovered, reasoning}`) and per-row `failure_mode`; failure modes:
  `function_over_form` (doc_type miss), `other_fallback`, `equivalent_family`
  (recovered by equivalence), `family_confusion`.
- `experiment_markdown()` in `src/experiment_log.py` renders each section as
  tables: metadata, data source, parameters, tokens, scores + breakdowns,
  per-document results, document × field scoring matrices, factuality audit,
  CUAD category presence, confusion matrices, model outputs, per-class
  subtype accuracy, failed-classification insights.
- Log paths: `EXPERIMENT_LOG_PATH` / `EXPERIMENT_LOG_MD_PATH` env vars or
  `--experiment-log`. Tests redirect to tmp dirs.
- If you change the renderer, regenerate the md log so it stays in sync.

## Code conventions

- **Style**: PEP 8, `from __future__ import annotations` at the top of every
  module, docstrings on every module/function, `structlog` for logging
  (`logger = structlog.get_logger(__name__)`), type hints throughout.
- **Imports**: stdlib → third-party → repo (`sys.path.insert(0, ...)` before
  repo imports in scripts; plain absolute imports inside packages).
- **Comments**: the repo uses explanatory docstrings and section banners;
  avoid noisy inline comments in new code.
- **Scripts** are `#!/usr/bin/env python3`, live in `scripts/<area>/`, are
  runnable from the repo root, and expose `--dry-run` on anything that spends
  money. Entry points call `main_with_args(argv)` (testable) from `main()`.
- **New prompts**: add the constant + register in `PROMPT_VERSIONS`
  (`src/prompts.py`); the version key IS the experiment identity. NEVER edit
  a prompt string after it has run — a changed prompt needs a new version
  key. Derived versions (v8/v9/v10/v11 style `.replace()` on a prior
  constant) are fine as long as the base string is untouched.
- **New doc classes**: add a `doc_classes:` entry in
  `config/taxonomy.yaml` (key, label, schema, specialist, field_types) AND a
  matching schema + specialist in `agents/specialist_agents.py` (and a prompt
  in `src/prompts.py`).
- **New eval runners**: mirror `run_subtype_eval.py` / `run_chained_eval.py`
  (same flags, `main_with_args`, Braintrust composite scoring, manifest,
  experiment-log append) and add a smoke test.
- **Never commit** real keys: `config/environments/.env`,
  `config/environments/braintrust.env`, `config/environments/*.env.local` are
  gitignored; use the `.example` files.
- **Never edit `reports/experiment_log.md` by hand** — regenerate it.

## Coding guidelines (adapted from Karpathy)

Four behavioral principles govern every code, prompt, and docs edit in this
repo. They are **adapted**, not vendored, from
[multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills)
(upstream pin `2c606141936f1eeef17fa3043a72095b4765b9c2`, MIT; sources
consulted + re-sync protocol in
`.opencode/agents/CODING_GUIDELINES_PROVENANCE.md`). Where these principles
and this file's governed workflow touch, **the house workflow wins**: a
card-first lifecycle claim outranks "think before coding", and prompt edits
follow the append-only versioning rules even when a simpler rewrite looks
possible. They bias toward caution over speed — for trivial doc fixes use
judgment.

1. **Think before coding.** State assumptions explicitly; where multiple
   interpretations of a directive exist, surface them instead of picking
   silently. Concretely here: name WHICH card scope you read the task from,
   which version key the work produces, and which datasets/runners/scorers
   it touches BEFORE the first edit. Governance uncertainty (card ownership,
   release target, dependency-pin drift) is a stop-and-post condition — put
   the specific blocker on the board, never guess through it.

2. **Simplicity first.** Ship the minimum change that satisfies the card's
   stated scope. No speculative abstractions, no configurability nobody asked
   for, no error handling for impossible states. If 200 lines could be 50,
   rewrite to 50. Prompt iterations express this natively: derive the new
   constant `.replace()`-style from its predecessor so the diff IS the delta,
   instead of re-authoring prose.

3. **Surgical changes.** Every changed line must trace directly to the card.
   Do not refactor working neighbors, reformat untouched regions, or
   "improve" adjacent prompts/comments while passing through. Orphans YOUR
   change created (now-unused imports/variables/files) are yours to remove;
   pre-existing dead code gets mentioned on the board, not deleted in
   passing. On shared trees this discipline is what makes explicit-path
   commits honest — a file that doesn't serve your card doesn't enter your
   commit.

4. **Goal-driven execution.** Before editing, convert the card into
   verifiable success criteria — named tests that must pass, expected run/
   row counts, LFS-sha or pin equality, suite arithmetic against the
   documented baseline — then loop until every criterion holds with
   evidence. "Make it work" is not a criterion. Phase 4 verification and
   artifact-derived evidence numbers (never remembered ones) are this
   principle's house implementation.

## Testing rules

- **Test surgically by default; run the full suite only for significant
  changes.** Routine work — a new prompt version, a runner flag, a scorer
  tweak, a doc edit — runs ONLY the surgically relevant tests (the files
  listed below for the area changed) plus any tangentially related suites
  (e.g. the eval smoke tests when a runner's flags change). Run the FULL
  suite (`python -m pytest tests/ -q`) only when the change is significant:
  cross-cutting refactors, packaging/import changes, scorer/metrics or
  site/asset changes — and ALWAYS before a release (`release.py --check`
  enforces it at the gate). Full-suite-by-default wastes minutes per
  iteration; surgical-by-default keeps the loop cheap.
- All tests must be network-free (mocked LLM calls, tmp Braintrust config).
  Check `tests/conftest.py` for shared fixtures.
- New eval logic → add a smoke test (see `test_extraction_eval_smoke.py`,
  `test_chained_eval_smoke.py`, `test_subtype_eval_smoke.py`,
  `test_eval_loop_smoke.py`) that runs the runner's `main_with_args` with
  mocked agents/datasets.
- New agent behavior → unit tests: `test_sorter_agent.py` (prompt wiring,
  option-list ↔ schema-enum equality, subtype normalization + equivalence,
  head+tail truncation), `test_judge_agent.py` (steps, choices, reasoning,
  scoring for all three judge dimensions).
- New scoring behavior → unit tests in `test_field_scoring.py` /
  `test_extraction_normalization.py`.
- New Langfuse mirror tooling → unit tests in `test_annotation_queue.py`
  (network-free: a fake Langfuse API stand-in covers selection, idempotency,
  and CLI wiring of `run_annotation_queue.py`).
- New streamer parsing → `test_cuad_streamer.py` /
  `test_legalbench_streamer.py` / `test_streamers.py`.
- Run the relevant tests before committing: `python -m pytest
  tests/test_<area>.py -q` for the areas you touched (surgically relevant +
  tangential only — see the first bullet; the full suite is NOT required for
  routine commits).

## Gotchas

- **Manifest resume**: `--manifest` checkpoints carry a header that must
  match the rerun's metadata exactly (dataset fingerprint, model, prompt
  version); a mismatch makes the resume invalid by design. Cached rows
  predating a scorer change must NOT be resumed — use a fresh manifest.
- **Manifest-replayed rows carry no usage** — token/cost summaries count only
  rows with usage (`rows_with_usage`).
- **Braintrust experiment naming**: re-running the same experiment name
  creates a SUFFIXED experiment (`-a1b2c3d4`) instead of overwriting; the
  name-suffixed experiment holds the newer run. Fetch experiments by
  `created` order when backfilling.
- **Same-sample comparisons only**: accuracy deltas across different samples
  are meaningless (the 50-doc and 195-doc subtype runs are NOT comparable;
  the 5-doc chained sample is the controlled A/B surface).
- **Vision mode** sends ALL pages of each PDF in one call by default
  (`--vision-pages all`); `first` is for cheap pilots.
- **The sorter subtypes**: the contract subtype is normalized against the
  CUAD folder names (see `CONTRACT_SUBTYPES` in `agents/sorter_agent.py`).
  Hybrids ("distribution and development agreement") can plausibly be either —
  that's what `subtype_accuracy_equiv` and the confusion matrix are for.
  The prompt option list MUST equal the schema enum (enforced by a test).
- **`braintrust.integrations.langchain.setup_langchain()`** must be called
  before any model call or the experiment rows won't carry nested spans.
- **reasoning_effort**: the SORTER defaults to `medium` (25 near-synonymous
  families need deliberation — verified +4.6pp strict on the 200-doc sample);
  the EXTRACTOR defaults to `none` — thinking models burn the whole token
  budget on reasoning otherwise. Flags: `--reasoning-effort` (subtype /
  extraction) and `--sorter-reasoning-effort` (chained). **Production
  decision (KANBAN-008): the recommended config is a SPLIT** — the default is
  the overall arm (`reasoning_effort=none`; the ko/overall tradeoff is in
  README "Recommended production configuration"); the ko-justified arm
  (`--reasoning-effort max`, `v23×max`: ko 0.8510, 0 parse errors, lowest
  ellipsis 18.7%) is a documented opt-in for compliance/covenant-heavy reviews
  at 2.6× cost — NOT `v19×max` (1/50 parse error + worst overall).
- **Extractor reasoning trace (v24+)**: the contracts specialist emits a
  REQUIRED per-field reasoning trace (`predicted.reasoning` — `summary` +
  `entries[{field, evidence, section_ref}]`) BEFORE finalizing the
  extraction. It is a visible trace, not thinking-mode: `reasoning_effort`
  stays `none`, the reasoning rides inside the structured JSON (schema
  `reasoning` object, property first) and lands in the experiment log +
  Langfuse observation outputs. The chunked pass unions entries across
  windows (first-witness evidence wins). It is NEVER scored — the
  diagnostics read only the extracted values, which must stay in the
  canonical parseable forms (v24 format discipline: ISO dates, leading
  duration phrases, plain currency amounts) for the MAE/R² pair counts.
- **max_tokens**: extraction of 50+ verbatim clauses exceeds 16k tokens —
  chained default is 32768; a truncated JSON zeroes the row.
- **Head+tail truncation**: past `--max-input-chars` the input keeps the
  opening 60% + closing 40% (`TRUNCATION_TAIL_FRACTION`); deal-critical
  sections live in the tail. `contracts_specialist_v9+` scan both sides of
  the truncation marker.
- **Chunked extraction A/Bs (the truncation confound)**: key_obligations /
  term_length A/Bs MUST run `--chunked` (90k windows, 8k overlap) — an
  unchunked single pass truncates long documents and drops mid-document
  restriction/covenant families (measured: Phasebio 0.125 unchunked vs
  0.94 chunked). Both extraction runners support it; `run_extraction_eval.py`
  prints a dry-run warning when off. Noise floor on the 50-doc chunked
  surface at temp 0.1: ±0.03 overall (identical-prompt rerun) — a candidate
  delta inside that band is a logic repair, not a win (see
  `docs/memos/contracts_specialist_v30.md`).
- **Extractor scope (v10/v11)**: `key_obligations` is scoped to the CUAD
  restriction/covenant families (the GT spans — mean 7.4, max 22 items);
  general operative duties are NOT expected items. Output cleanliness
  (2-12 items, `verified_precision` 1.0) beats raw recall on this partial-GT
  task.
- **Reports that fetch Braintrust** (`report_generator.py`,
  `confusion_matrix.py`) need `BRAINTRUST_API_KEY`; the manifest/log
  reporting paths are fully offline.
- **CUAD ground truth is type-aware**: expected fields derive from the
  contract's CUAD folder via `build_expected_fields`; don't assume all 41
  categories apply to every document.
- **Extraction diagnostics are run-level, not trackers**: `scores.diagnostics`
  (`src/metrics.py` → `llm_dojo_scoring.diagnostics`) is computed post-hoc
  from the stored rows and lives in
  the experiment-log record + md render + site — it is NOT a Braintrust
  tracker. MAE/R² rows are only as good as their parseable-pair counts
  (`date_n_pairs` etc.) — always read the support size with the number.
  `--master-labels` is best-effort: absent CSV ⇒ raw clause-text parsing.
  Chained-eval runs do not produce diagnostics (own runner, future card).
- **Packaging**: the layout (`llm-mailroom/src/{agents,config,...}` with `src/` on the
  import path) is what llm-mailroom imports; after adding a new module, confirm it is covered by
  `pip install -e .` (setuptools `packages` list) and the out-of-repo import
  still works.

## Skills (all agents)

Project skills under `.opencode/skills/` are available to EVERY agent in this
repo (opencode auto-loads `SKILL.md` per skill; `allowed-tools` frontmatter
grants tool access when loaded):

- **langfuse** (from github.com/langfuse/skills) — CLI-based Langfuse API
  access, docs retrieval, prompt migration, trace debugging, evaluation
  setup. Consult before touching Langfuse data (queries, score configs,
  prompts, dashboards); the repo's own integration is the
  `run_langfuse_*_eval.py` mirror + `src/langfuse_tracing.py`.
- **langchain-\*** (from github.com/langchain-ai/langchain-skills) —
  `langchain-fundamentals` (create_agent, tools, middleware),
  `langchain-python-quickstart`, `langchain-dependencies` (version pinning),
  `langchain-middleware` (callbacks/instrumentation/HITL), `langchain-rag`.
- **langgraph-\*** (same upstream) — `langgraph-fundamentals` (StateGraph,
  nodes, edges, Command/Send, streaming), `langgraph-python-quickstart`,
  `langgraph-cli`, `langgraph-persistence` (checkpointers — llm-mailroom uses
  SqliteSaver), `langgraph-human-in-the-loop` (review/interrupt nodes).
- **ecosystem-primer** — how LangChain/LangGraph/LangSmith fit together.
- **eval-engineering** — Harbor-style eval design references (task design,
  verifier design, harness, multi-turn simulation) — complementary to this
  repo's own deterministic eval loop.

The agents under test and the llm-mailroom pipeline under evaluation are
built on LangChain + LangGraph — invoke the matching skill before writing or
changing any agent/graph code.

## Agents (this repo)

Project agents under `.opencode/agents/` (opencode loads `<name>.md`; the
body becomes the agent's prompt):

- **prompt-engineer** (`prompt-engineer.md`) — the master diagnostic
  evaluator and prompt engineer: its SOLE role is to review all traces,
  reasoning logic, failures, error messages, and results of every evaluated
  prompt and produce a stronger, refined, data-backed mutation (new
  version key) that is free of local plateaus and overfitting to the tested
  sample. Runs the **GEPA (Genetic-Pareto) reflective prompt-evolution
  loop** — sample trajectories → reflect on failures in natural language →
  mutate one lesson per version → same-surface A/B with a noise-floor
  control (champion rerun) → Pareto-aware selection across score/cost/
  robustness, combining complementary lessons from the candidate frontier —
  mapped onto the repo's diagnose → root-cause → mutate → verify → land
  phases: failure-insight + diagnostics review (MAE/R² with support sizes,
  span-count drift, error decomposition), sim-matrix miss classification,
  cluster-based rule drafting with data-backed tests, chunked-surface
  discipline for extraction A/Bs (the truncation confound), same-seed
  pilots and same-surface A/Bs with paired bootstrap-CI significance,
  plateau/overfit detection (sub-noise deltas are logic repairs, never
  claimed wins), and board + CHANGELOG close-out with proof. Delegate
  prompt iterations to it; never mutate a prompt version it has validated
  without a new iteration.
- **experiment-log-sync** (`experiment-log-sync.md`) — keeps the experiment
  log and the GH Pages site in sync with the latest Braintrust/Langfuse
  runs.

## Docs & READMEs

- Per-directory READMEs are the map: `src/README.md`, `agents/README.md`,
  `config/README.md`, `scripts/README.md`, `tests/README.md`,
  `reports/README.md`, `docs/README.md` (site), plus the root `README.md` —
  keep them current when the layout or a module's contract changes.
  `governance/MESSAGE_BOARD.md` is the shared agent task canvas — keep it current on
  EVERY task, not just releases (see the message board section above).
- The project **wiki** is version-controlled in `docs/wiki/` (Home,
  Getting-Started, Architecture, Eval-Runners, Experiment-Log, Scoring, Site,
  Release-Process, Taxonomy, FAQ) and pushed to the public GitHub wiki with
  `./docs/wiki/sync-wiki.sh` — run it after wiki edits and after major releases.
  The wiki is NOT a mirror of docs/; each lives its own life.

## Research memos

`docs/memos/*.md` are the archived research memoranda — key findings from
experimental runs and prompt iterations, written for collaborators and
presentation. Format: **Research question** opener, **Companions** links,
`## Answer, Response, + Summary of Results` with a **Short answer**, data
tables (with same-surface identity + bootstrap CIs where applicable), an
`### Interpretation` numbered list, `*Sources:*`, and a closing
`## What questions or uncertainties remain?`. The site ships them under the
**memos** tab (`build_site.py` emits `docs/data/memos.json`; the viewer
renders the markdown subset). Add a memo in the same commit as the finding
it archives.

## Issue & PR templates

`.github/ISSUE_TEMPLATE/` (bug_report, feature_request, experiment_report +
config.yml contact links) and `.github/PULL_REQUEST_TEMPLATE/pull_request.yml`
are YAML forms enforcing this repo's discipline: same-surface identity on
every bug/experiment report, the [Unreleased]-in-the-same-commit changelog
rule, derived-artifact regeneration, the render audit, and the
`release.py --check` gate.

## Useful one-liners

```bash
# List prompt versions
python -c "from src.prompts import list_prompts; print('\n'.join(list_prompts()))"

# Tail the experiment log
python - <<'PY'
import json
for line in open("reports/experiment_log.jsonl"):
    r = json.loads(line)
    print(r["experiment_name"], r["scores"].get("overall_extraction_score") or
          r["scores"].get("exact_match"), r["timestamp"])
PY

# Failure insights from the last subtype run
python - <<'PY'
import json
for line in open("reports/experiment_log.jsonl"):
    r = json.loads(line)
    if r["task"] != "subtype_classification":
        continue
    fi = r["scores"]["sorter"].get("failure_insights") or {}
    print(r["experiment_name"], r["timestamp"], fi.get("mode_counts"), "failed:", fi.get("n_failed"))
PY

# Import the agents from outside the repo (llm-mailroom pattern)
pip install -e . && python -c "from agents.sorter_agent import SorterAgent; from agents.judge_agent import JudgeAgent"
```
