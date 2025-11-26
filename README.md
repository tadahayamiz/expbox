# expbox

*A lightweight, non-intrusive, git-aware experiment box for Python.*

`expbox` attaches a lightweight **box** (`results/<exp_id>/`) to your project that records:

* config snapshot
* metrics & logs
* artifacts (models/tables)
* figures
* automatically captured Git metadata (commit, branch, dirty state, remote URL)
* optional free-form metadata (notes, environment info)

**It never dictates your project structure or workflow.**
It simply adds a `results/` directory and stays invisible until you want it.

```python
import expbox as xb

ctx = xb.init(...)
xb.save(ctx)
ctx = xb.load(...)
```

---

## Features

### Git-aware, GitHub-friendly

On every `init` and `save`, expbox captures:

* current commit (`HEAD`)
* branch
* dirty flag + list of modified files
* remote origin URL
* GitHub commit URL (if applicable)

This builds **true reproducibility** into your normal workflow.

### Non-intrusive by design

* No required project template
* No code generation
* No assumptions about data
* expbox *only* writes inside `results/<exp_id>/`
* Your repository remains entirely yours

### Local-first, HPC-safe

* Works on laptops, Colab, on-prem GPU servers, and HPC clusters
* Rank-0 logging avoids filesystem contention
* No external dependencies unless you opt in (e.g., wandb)

---

## Installation

```bash
pip install expbox
```

Optional extras:

```bash
pip install "expbox[yaml]"    # Enable YAML config support
pip install "expbox[wandb]"   # Enable W&B logger backend
```

Dev install:

```bash
git clone https://github.com/your-org/expbox
cd expbox
pip install -e .[dev]
pytest
```

---

## Getting Started

### 1. Clone your project (recommended flow)

```bash
git clone https://github.com/you/your-project
cd your-project
```

Use your preferred layout; expbox does **not** enforce any structure:

```text
your-project/
  data/             # any size, usually not tracked by Git
  src/              # your scripts
  configs/          # optional config directory
  notebooks/        # optional
  pyproject.toml    # or requirements.txt, etc.
  results/          # <-- created by expbox
```

The only directory expbox touches is:

```
results/
```

### 2. Place data wherever *you* want

expbox never manages your data.
Load it however your workflow already does:

```python
df = pd.read_csv("data/train.csv")
# or "datasets/liver/train.pkl"
```

### 3. Use Git commits as your timeline

* You edit code (`src/`) and configs (`configs/`)
* You commit frequently:

```bash
git add src/ configs/
git commit -m "tune lr"
```

Git stays in control of the code timeline.
expbox simply records snapshots along that timeline.

---

## Workflow Philosophy

### `init` — *start a new story / phase*

Call `xb.init(...)` **once** when starting a new experiment series:

```python
ctx = xb.init(project="ToxModel", title="baseline-series")
```

### `git commit` — *often*

Edit → run → commit as usual.
This is your main unit of iteration.

### `save` — *when you want a snapshot*

Call `xb.save(ctx)` only when you want to bookmark progress:

* after a batch of runs
* after tuning hyperparams
* before trying a risky fix
* at the end of a work session
* before switching branches

```python
ctx.meta.final_note = "seed sweep finished"
xb.save(ctx)
```

You can call `save` many times for the same experiment box.

### `init` again — *when the story changes*

Only when a new idea / dataset / model family starts:

```python
ctx = xb.init(project="ToxModel", title="contrastive-learning-v2")
```

---

## A Typical Day with expbox + GitHub

```
git clone your-project
cd your-project

# new story
python src/train_baseline.py     → xb.init()

# work continues
git commit -m "refactor training loop"
python src/train_baseline.py     → xb.save()

git commit -m "tune lr"
python src/train_baseline.py     → xb.save()

# conclude the story
ctx.meta.status = "completed"
xb.save(ctx)
```

The box now contains **snapshots** tied to specific commits.

To reproduce:

```
git checkout <git.last.commit>
python src/train_baseline.py
```


## How `results/` evolves in your project

The `results/` directory is the **only place** expbox touches.
It acts as a **gallery of experiment boxes**, growing over time as your research progresses.

```
your-project/
  src/
  data/
  configs/
  results/
    241201-1530-baseline/        ← created by xb.init()
    241202-1120-baseline/        ← new story → xb.init()
    241202-1745-lr-sweep/        ← new story → xb.init()
    241205-0910-adv-eval/        ← new story → xb.init()
```

Each entry under `results/` is one **experiment story** (one box).

### A box evolves with `save`

Inside one box:

```
results/241201-1530-baseline/
  meta.json             ← updated each time you xb.save()
  artifacts/
    config.yaml         ← snapshot from init()
    model.pt
  logs/
    metrics.jsonl
  figures/
    loss_curve.png
```

* **`save` does NOT create a new box.**
  Instead, it updates the *same* box:

  * updates `meta.json` (git.last, notes, timestamps)
  * writes more figures/logs/artifacts
  * preserves the history of your experiment series

### A new box only appears when YOU start a new story

You get a new directory under `results/` **only when you call `xb.init()`**:

```
ctx = xb.init(project="ToxModel", title="contrastive-v2")
```

This produces:

```
results/241205-0910-adv-eval/
```

This separation naturally organizes your project:

* Code timeline → **Git commits**
* Story timeline → **expbox boxes**

---

## Visual timeline diagram (optional but helpful)

```
git commits:   C1 ---- C2 ---- C3 ---- C4 ---- C5 ---- C6 ---- C7
                 \      \      \            \
expbox boxes:    [baseline box]             [lr-sweep box]
                     |     |     |             |      |
                   save   save  save         save   save
```

* Frequent **Git commits** reflect your coding iteration
* Occasional **expbox save snapshots** preserve important milestones
* **New expbox box** only when the story / experiment phase changes

---

## Short Summary

| Action               | Effect on `results/`                                        |
| -------------------- | ----------------------------------------------------------- |
| `xb.init()`          | **Creates a NEW box** under `results/`                      |
| `xb.save(ctx)`       | **Updates the SAME box** (snapshot)                         |
| `git commit`         | No change to `results/`; expbox records commit on next save |
| New story/experiment | Call `xb.init()` → new directory appears                    |


---

## Quick Start (Python)

```python
import expbox as xb
import torch
import matplotlib.pyplot as plt

# Start a new experiment series
ctx = xb.init(
    project="ToxModel",
    title="baseline-series",
    config={"lr": 1e-3, "epochs": 5},
    logger="file",
)

model = torch.nn.Linear(10, 1)
opt = torch.optim.Adam(model.parameters(), lr=ctx.config["lr"])

# Training loop
for step in range(100):
    loss = (model(torch.randn(8, 10)) ** 2).mean()
    loss.backward(); opt.step(); opt.zero_grad()
    ctx.logger.log_metrics(step=step, loss=float(loss))

# Create a snapshot
ctx.meta.final_note = "initial baseline run finished"
xb.save(ctx)
```

---

## Quick Start (CLI)

CLI usage mirrors the Python API:

```bash
# Create a new experiment box — prints exp_id
exp_id=$(expbox init --project MyProj --config configs/base.yaml --logger file)
echo "Experiment box: $exp_id"

# ...run your script multiple times as you iterate...

# Save a snapshot with a note
expbox save "$exp_id" --final-note "batch completed"

# You may call `expbox save` as many times as you want for the same box.
```

---

## HPC-safe Example (rank-0 pattern)

```python
import os
import expbox as xb

rank = int(os.environ.get("RANK", 0))  # DDP / SLURM / MPI

if rank == 0:
    ctx = xb.init(project="HPC-demo", config="configs/train.yaml", logger="file")
else:
    ctx = None

for step in range(200):
    loss = train_step()
    if rank == 0:
        ctx.logger.log_metrics(step=step, loss=float(loss))

if rank == 0:
    ctx.meta.final_note = "HPC batch snapshot"
    xb.save(ctx)
```

---

## Git Metadata Structure

Each box stores a structured snapshot:

```json
"git": {
  "repo_root": "/abs/path/to/repo",
  "project_relpath": "src",
  "start": {
    "commit": "a1b2c3d4",
    "branch": "dev-route3",
    "dirty": true,
    "captured_at": "2025-11-25T10:00:00Z"
  },
  "last": {
    "commit": "9a0b1c2d",
    "branch": "main",
    "dirty": false,
    "saved_at": "2025-11-26T08:30:00Z"
  },
  "dirty_files": ["src/model.py", "configs/baseline.yaml"],
  "remote": {
    "name": "origin",
    "url": "git@github.com:you/your-project.git",
    "github_commit_url": "https://github.com/you/your-project/commit/9a0b1c2d"
  }
}
```

---

## Philosophy Summary

* **Your project stays yours.**
  expbox adds nothing except `results/`.

* **Git is your timeline.**
  Commit freely; expbox simply records what matters.

* **Save when you want a snapshot.**
  Not more, not less.

* **Init only when the story changes.**
  Each box = a chapter in your research.

---

## Author

**Tadahaya Mizuno**
tadahayamiz (at) gmail.com

MIT License

---