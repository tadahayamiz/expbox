# expbox  
*A lightweight, local-first experiment box for Git-based Python research.*

`expbox` gives each experiment its own **box** — a directory such as:

```text
results/
  <exp_id>/
    meta.json
    artifacts/
    logs/
    figures/
    notebooks/
````

It provides a **minimal, non-intrusive Python API** for managing configs, logs, metadata, and reproducibility information.  
No servers, no daemons, no databases — everything lives on user-controlled filesystems.

---

## Features

* **Active Box API**
  `xb.init()` / `xb.load()` makes an experiment “active”, and
  `xb.log_metrics`, `xb.log_table`, `xb.log_figure`, `xb.final_note`, `xb.save()`
  automatically operate on it.

* **Local-first, append-only, non-destructive**
  expbox **never deletes your files**.
  Saving is always incremental and safe.

* **Reproducibility baked in**

  * Git-anchored snapshots (start / last commit; best-effort, read-only)
  * config snapshot (`artifacts/config.yaml`)
  * timestamped metadata (`created_at`, `finished_at`)

* **Zero magic**
  Files go exactly where you expect them to go.
  You can inspect everything manually in `results/<exp_id>/`.

* **CLI included**
  For quick scripting:

  ```bash
  expbox init ...
  expbox save <exp_id>
  ```

---

# Philosophy

expbox is built on three principles:

1. **Local-first, project-native**
   No experiment management servers, no dashboards, no databases.
   All experiment data lives on user-controlled filesystems
   (local machines, HPC clusters, or shared storage),
   and is managed directly as files.

2. **Non-intrusive**
   It never tells you how to structure your experiments.
   It only helps you **track** what you already do.

3. **Safe, append-only**
   No automatic deletion.
   Saving is always incremental.
   Reproducibility information is guaranteed to be preserved.

---

# Installation

From PyPI:

```bash
pip install expbox
```

For development:

```bash
pip install -e .
```

---

# Quick Start (Python)

```python
import expbox as xb

# 1) create a new experiment box (also becomes the active box)
xb.init(project="demo", config={"lr": 1e-3}, logger="file")  # logger is optional

# (optional) log metrics, tables, and figures
# You can skip logging entirely if you manage logs elsewhere (e.g. W&B).
for step in range(100):
    loss = ...
    xb.log_metrics(step=step, loss=float(loss))
xb.log_table("eval", df)        # df: e.g., pandas.DataFrame
xb.log_figure("roc", fig)       # fig: e.g., matplotlib.figure.Figure

# 2) add a final note and save
xb.final_note("Initial test run.")
xb.set_status("done")
xb.save()
```

The following shortcuts always refer to the **active box**:

```python
xb.paths      # directory paths (root, artifacts, logs, figures, notebooks)
xb.config     # configuration dict
xb.meta       # experiment metadata object
xb.logger     # logger backend (NullLogger or FileLogger)
xb.exp_id     # experiment ID (e.g., "241126-1030-demo")
xb.project    # project name
```

---

# Using Existing Boxes

```python
# Load an existing experiment and make it active
xb.load("241126-1030-demo")

# More logs…
xb.log_metrics(step=200, lr=1e-4)
xb.save()
```

You can also load without specifying the ID:

```python
xb.load()   # loads the ID recorded in .expbox/active
```

`.expbox/active` is a small text file stored in your project root that records the last active experiment id.

---

# Directory Structure

After running:

```python
xb.init(project="demo")
```

you get:

```text
results/
  241126-1030-demo/
    meta.json
    artifacts/
      config.yaml
    logs/
      metrics.jsonl
    figures/
    notebooks/
```

* `artifacts/` : models, tables, and other derived files
  (`xb.log_table` saves `*.csv` here by default)
* `logs/`      : scalar metrics (`metrics.jsonl`)
* `figures/`   : images saved via `xb.log_figure`
* `notebooks/` : optional notebook exports

---

# Usage Patterns (Best Practices)
expbox supports multiple usage styles, from minimal experiment tracking
to full experiment notebook workflows.  

## 1. Minimal Mode (Box + Git snapshot)

**For users who already use external logging tools (e.g. W&B, MLflow),
or manage results manually.**

1. `xb.init(...)` to create a box
2. run your experiment
3. commit your code
4. `xb.save(...)` to record the snapshot

This mode uses expbox purely as a local experiment box
anchored to Git commits.

## 2. Local Helper Mode

Use expbox helpers (`log_metrics`, `log_figure`, `log_table`) to organize
lightweight local results when you do not rely on external tracking services.
All helpers are optional.

## 3. Scratch / Story Box Modes

**For early, messy, exploratory experiments**

These modes treat each experiment box as a lab notebook page,
supporting exploratory (scratch) and result-oriented (story) workflows.

### 3-1. Scratch Box Mode

* Use a **single box** for a while
* Let files accumulate
* `save()` periodically to capture notes, Git state, and timestamps

This is like an “experiment notebook page”.

```python
xb.init(project="scratch-demo")

for trial in range(20):
    ...
    xb.log_metrics(step=trial, acc=float(acc))
    xb.save()
```

---

### 3-2. Story Box Mode

**When results start to matter (e.g., for papers or reports)**

* Create a **new box per story**
  (ablation study, figure generation, hyperparameter sweep, etc.)
* Organize artifacts using subfolders or filenames
* Keep each box clean and meaningful

```python
xb.init(project="paperX_fig3")

for seed in [0, 1, 2]:
    run_dir = xb.paths.artifacts / f"seed{seed}"
    run_dir.mkdir(exist_ok=True)
    ...
    torch.save(model.state_dict(), run_dir / "model.pt")
    xb.log_metrics(step=seed, val_auc=float(auc))

xb.final_note("Ablation experiments for Figure 3")
xb.set_status("done")
xb.save()
```

---

## A very important invariant

### **expbox never deletes anything.**

* `save()` only appends metadata and logs.
* No automatic cleanup or overwriting of artifacts.
* If you want a clean directory:

  1. **Start a new box (`xb.init()`), or**
  2. Delete files manually via `xb.paths.*` (your responsibility).

This preserves safety, transparency, and local-first principles.  
Note: expbox also stores the ID of the *current active experiment* in a small
file at the project root:

  ```
  .expbox/active
  ```

This file is **local state only** (it simply remembers the last active box)
and is **automatically recreated** when needed.  

In addition, expbox maintains a lightweight experiment index under:

  ```
  .expbox/index/
  ```

Each experiment is summarized as a single JSON file
(`<exp_id>.json`) containing privacy-safe metadata.
This index can be safely committed and used for lightweight project-wide
overviews, listing, export, or reporting, even when `results/` is not tracked by Git.

---

# CLI Usage

The CLI wraps the same high-level API.

### Initialize

```bash
expbox init --project demo --config configs/base.yaml --logger file
```

Prints the new `<exp_id>`.

### Load an experiment

```bash
expbox load 241126-1030-demo
```

Outputs metadata as JSON.

### Save / finalize

```bash
expbox save 241126-1030-demo --status done --final-note "finished"
```

---

# Configuration Snapshot

`config` can be:

* a Python dict (recommended)
* a path to YAML/JSON
* or `None`

The effective config is always stored in:

```text
results/<exp_id>/artifacts/config.yaml
```

Snapshots are **immutable** once created (append-only).

---

# Logging Details

### Metrics

```python
xb.log_metrics(step=step, loss=loss, acc=acc)
```

Metrics are stored as JSON lines under:

```text
results/<exp_id>/logs/metrics.jsonl
```

### Tables

```python
xb.log_table("eval", df)  # df.to_csv(...) will be called
```

By default this saves:

```text
results/<exp_id>/artifacts/eval.csv
```

### Figures

```python
xb.log_figure("roc_curve", fig)
```

By default this saves:

```text
results/<exp_id>/figures/roc_curve.png
```

---

# Reproducibility Metadata

`meta.json` automatically records:

* timestamps (`created_at`, `finished_at`)
* Git-anchored snapshots (commit hashes, branches; read-only)
* optional dirty state indicators
* privacy-aware environment snapshots (coarse-grained by default)
* status
* config snapshot path
* logger backend

By default, expbox records metadata in a **privacy-safe** manner.
More detailed information can be enabled explicitly when needed.

You can also edit notes via shortcuts:

```python
xb.final_note("best model among seeds")
xb.set_status("done")
xb.save()
```

---

# Recommended Project Layout

```text
your-project/
  src/
  notebooks/
  configs/
  pyproject.toml
  results/  # expbox made
  .expbox/  # expbox made
    active
    index

```

expbox does **not** require this layout, but it works well in practice.  
Note: `results/` typically contains local experiment artifacts and
is not expected to be tracked in public Git repositories.

---

# License

MIT License.

# Author
Tadahaya Mizuno (tadahayamiz)