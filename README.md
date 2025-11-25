# 📦 expbox

*A lightweight, git-aware experiment box for Python.*

`expbox` gives each experiment a self-contained **box** (`results/<exp_id>/`) that records:

* configuration snapshot
* metrics & logs
* artifacts (models/tables)
* figures
* auto-captured Git metadata (commit, branch, dirty state)
* free-form metadata (notes, env info)

The API remains extremely small:

```python
import expbox as xb

ctx = xb.init(...)
ctx = xb.load(...)
xb.save(ctx)
```

---

## 🚀 Features

### ✔ Git-aware, GitHub-ready

* On `init` / `save`, expbox records:

  * commit hash
  * branch
  * dirty flag
  * remote `origin` URL
* This makes **experiments inherently reproducible across machines and collaborators**.

### ✔ Local-first, compatible with any environment

* Works the same on **laptop, Colab, on-prem GPU boxes, HPC (SLURM, MPI, DDP)**.
* Uses a **rank-0 logging strategy**, avoiding write contention on shared filesystems (NFS / Lustre / GPFS).

### ✔ Friendly with external tools

expbox is intentionally small, but integrates smoothly with:

* **Notion / Obsidian** → store `meta.json` as a structured entry
* **Weights & Biases** → optional `wandb` logger
* **MLflow** → simply push paths or metrics from `ctx.paths`
* **GitHub** → commit only lightweight metadata and figures

### ✔ A single directory per experiment

```
results/<exp_id>/
  meta.json
  artifacts/
    config.yaml
    model.pt
  logs/
    metrics.jsonl
  figures/
    loss_curve.png
```

---

## 📦 Installation

```bash
pip install expbox
```

Optional extras:

```bash
pip install "expbox[yaml]"    # YAML config support
pip install "expbox[wandb]"   # W&B logger backend
```

Dev install:

```bash
git clone https://github.com/<your-org>/expbox
cd expbox
pip install -e .[dev]
pytest
```

---

## 🔧 Quick Start (Python)

Below is a **minimal deep-learning-style loop** showing metrics logging and figure output.

```python
import expbox as xb
import torch
import matplotlib.pyplot as plt

# 1) Start a new experiment
ctx = xb.init(
    project="ToxModel",
    title="baseline",
    config={"lr": 1e-3, "epochs": 3},
    logger="file",      # "none" | "file" | "wandb"
)

# Dummy model / optimizer
model = torch.nn.Linear(10, 1)
opt = torch.optim.Adam(model.parameters(), lr=ctx.config["lr"])

# 2) Training loop (log metrics)
for step in range(50):
    loss = (model(torch.randn(4, 10)) ** 2).mean()
    loss.backward(); opt.step(); opt.zero_grad()

    ctx.logger.log_metrics(step=step, loss=float(loss))

# 3) Save a figure
plt.plot([float(i) for i in range(50)])
plt.title("Dummy Curve")
fig_path = ctx.paths.figures / "curve.png"
plt.savefig(fig_path)

# 4) Finalize
ctx.meta.final_note = "baseline run finished"
xb.save(ctx)
```

---

## 🧪 Quick Start (CLI)

```bash
# Create a new experiment
exp_id=$(expbox init --project MyProj --config configs/base.yaml --logger file)
echo "Experiment: $exp_id"

# Finalize
expbox save "$exp_id" --status done --final-note "completed"
```

---

## 🧠 HPC / Distributed Training (rank-0 pattern)

expbox is safe on HPC clusters when **only rank 0** writes experiment files.

```python
import os
import expbox as xb

rank = int(os.environ.get("RANK", 0))  # DDP / SLURM / MPI

if rank == 0:
    ctx = xb.init(project="HPC-demo", config="configs/train.yaml", logger="file")
else:
    ctx = None

for step in range(100):
    loss = train_step()
    if rank == 0:
        ctx.logger.log_metrics(step=step, loss=float(loss))

if rank == 0:
    xb.save(ctx, status="done")
```

Works on:

* DDP (PyTorch)
* SLURM (MPI/OpenMPI)
* Horovod
* Any shared filesystem (NFS / Lustre / GPFS)

---

## 🗃 Git Integration & What to Commit

**Recommended `.gitignore`:**

```gitignore
# heavy logs & artifacts out of git
results/*/logs/
results/*/artifacts/*

# optionally
# results/*/figures/

# meta.json and config.yaml are kept on git
!results/*/artifacts/config.yaml

```

**Commit manually** only lightweight files:

```
results/<exp_id>/meta.json
results/<exp_id>/artifacts/config.yaml
results/<exp_id>/figures/*.png   # optional
```

This keeps heavy models/logs local while GitHub stores the reproducibility metadata.

---

## 🗂 External Tools

### Notion / Obsidian

Just read `results/<exp_id>/meta.json` and push fields into your PKM database.
This makes experiment tracking human-friendly while keeping data in-repo.

### Weights & Biases

Enable with:

```python
ctx = xb.init(..., logger="wandb")
```

W&B run URL can be stored in:

```python
ctx.meta.extra["wandb_url"] = ctx.logger.run.url
```

### MLflow

Use `ctx.paths.artifacts` to log models / tables to MLflow manually.
MLflow and expbox do **not** conflict.

---

## 📘 More Documentation

To keep the README short, detailed documentation is in:

* module docstrings (`expbox.api`, `expbox.core`, `expbox.io`, `expbox.logger`)
* upcoming `/docs/` directory with examples & recipes

---

## 📝 License

MIT License.

---

## 👤 Author

**Tadahaya Mizuno**
tadahayamiz (at) gmail.com

---