# Sister repositories & the governed umbrella

`llm-entity-extraction` does not fly alone: it shares ONE kanban board and
discussion log (`governance/MESSAGE_BOARD.md`) with its sister pipeline, consumes
an upstream scoring package both repos pin, and publishes eval datasets the
whole family loads. This page maps every repository under the
llm-mailroom umbrella of influence and how this repo relates to each.
(The mirror view from the pipeline side lives in
[llm-mailroom's `docs/sister-repos.md`](https://github.com/Exios66/llm-mailroom/blob/main/docs/sister-repos.md).)

```
                 ┌────────────────────────────┐
                 │   llm-entity-extraction    │  ← you are here
                 │  prompt experiment loop    │
                 └───────┬───────────┬────────┘
        champion prompts │           │ deterministic scores via
        (vendored agents)│           │ thin re-export shims
                         ▼           ▼
        ┌────────────────────┐   ┌────────────────────────────┐
        │    llm-mailroom    │   │     llm-dojo-scoring       │
        │ LangGraph pipeline │   │  upstream scoring engine   │
        └────────────────────┘   └────────────────────────────┘
        corpus feeds (via the Lucius-Morningstar HF family):
        Enron-Evaluation-Environment · claims-data-eda ·
        atticus-investigation

derived artifact: llm-entity-extraction-graph (graphify knowledge-graph site)
HF datasets:      Lucius-Morningstar/* (published eval/corpus surfaces)
visualizer:       The-Mailroom (pixel-art UI over llm-mailroom's Langfuse traces)
```

## At a glance

| Repository | Role | Relationship to this repo |
|---|---|---|
| [llm-mailroom](https://github.com/Exios66/llm-mailroom) | LangGraph state machine that processes legal documents through specialist LLM agents (classify → extract → report → archive) | **Sister repo.** Deployment target of this loop's champion prompts; vendors this repo's LangChain sorter/contracts agents; shares ONE kanban board and discussion log |
| [llm-dojo-scoring](https://github.com/Exios66/llm-dojo-scoring) | Deterministic, field-type-aware scoring engine (metric registry, T0–T3 tiers, agent profiles, doc-type bundles) | **Upstream governed dependency**, pinned in `pyproject.toml` (`@v0.10.0`); consumed through six thin re-export shims in `src/` |
| [Enron-Evaluation-Environment](https://github.com/Exios66/Enron-Evaluation-Environment) | EDA + pipeline-ready correspondence dataset from the CMU Enron corpus; owns the shared ground-truth labelers | **Corpus feed** — source of [`enron-correspondence(-dedup)`](https://huggingface.co/datasets/Lucius-Morningstar/enron-correspondence-dedup); its labeler modules are imported (never forked) by this repo's HF publishers |
| [claims-data-eda](https://github.com/Exios66/claims-data-eda) | Insurance-claims candidate-corpus EDA (CMS DE-SynPUF direction) | **Corpus feed (candidate)** for future insurance-claim extraction surfaces — honest-gap benchmark source |
| [atticus-investigation](https://github.com/Exios66/atticus-investigation) | LegalBench classification prompt-engineering pipeline | **Eval sibling**: same prompt-version × model methodology, LegalBench focus |
| [The-Mailroom](https://github.com/Exios66/The-Mailroom) | Pixel-art visual engine for the sister pipeline — renders every run as an animated document conveyor (floor, review siding, inspector, metrics, TUI) driven SOLELY by llm-mailroom's Langfuse project | **Downstream of the sister repo** — reads its traces, mirrors its schema (`pipeline_schema.py` / `trace_interpreter.py`); dependency of no family repo |
| [llm-entity-extraction-graph](https://exios66.github.io/llm-entity-extraction-graph/) | Interactive graphify knowledge graph of THIS codebase | **Derived site** — build artifact only (`graphify-out/` never committed here); companion to [llm-mailroom-graph](https://exios66.github.io/llm-mailroom-graph/) |

## The Hugging Face family

Eval datasets published from this repo live under the
[`Lucius-Morningstar`](https://huggingface.co/datasets/Lucius-Morningstar)
org: `legalbench-full`, `cuad-contracts(+full)`, `lb-hearsay`,
`docclass-merged`, `enron-correspondence`, `enron-correspondence-dedup`.
One split rule for the whole family (`md5(filename) % 10 == 0 → test`,
single-source `assign_split()`); Braintrust mirrors stay read-only per
`AGENTS.md`. See `scripts/datasets/` and the board cards (KANBAN-069,
071–079) for publisher provenance.

## Governance notes

- Cross-repo work = one card, one issue, both repos' changelogs (KANBAN-061
  precedent). Cards for mailroom-side work still live on THIS repo's board —
  llm-mailroom has no local board.
- Dependency pins flow upstream→downstream; after any dojo release, audit
  every consumer manifest (`grep -n "llm-dojo-scoring" pyproject.toml requirements*.txt`
  in BOTH repos) in the same commit.
