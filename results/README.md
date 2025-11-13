Results Directory Overview
===========================

The `results/` tree collects evaluation artifacts that can accompany research
reports or demos. To keep the Git history manageable, prefer lightweight
summaries over raw model outputs.

Sub-directories:

- `figures/` – charts exported from notebooks or dashboards (currently empty).
- `logs/` – evaluation-time logs too verbose for `logs/runtime/`.
- `tables/` – tabular summaries (CSV/Markdown) derived from experiments.

Guidelines:

1. Commit only aggregated metrics, plots, and short excerpts that help reproduce
   published numbers.
2. Keep large raw traces (per-sample JSONL, confusion matrices in binary
   formats, etc.) in `experiments/<run>/` or an external storage bucket.
3. If you regenerate results, prefer replacing files over appending duplicates.

