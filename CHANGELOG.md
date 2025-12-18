# Changelog
All notable changes to this project will be documented in this file.

## [Unreleased]

## [0.4.2] – 2025-12-18

### Added

* **Git commit subject tracking**

  * Record one-line commit subjects for both `git.start` and `git.last`, alongside full commit hashes.
  * Improves human readability while keeping full hashes as the reproducibility anchor.
* **Experiment index (`.expbox/index/<exp_id>.json`)**

  * Introduced a privacy-safe, per-experiment index.
  * Generated at `init` (`status=running`) and updated at `save`.
  * CSV export now prefers the index, with fallback to `meta.json`.
* **Soft cleanup utilities**

  * Added `archive` and `sweep` (Python API and CLI).
  * Enable marking experiments as `aborted`, `stale`, or `superseded` without deleting files.

### Changed

* **Privacy-safe metadata by default**

  * Index records omit absolute paths and sensitive environment details.
  * Full metadata remains available in `meta.json`.
* **Git hash handling**

  * Full 40-character hashes are always stored.
  * Short hashes are used for display purposes only.
* **Export behavior**

  * Index-based export is now standard; flattening occurs only at export time.

### Fixed

* **Test isolation**

  * Ensured `.expbox/` and index files are created under temporary directories.
  * Added tests for `archive` and `sweep`.

### Documentation

* Clarified that expbox assumes a **Git-managed project**.
* Documented the role of `.expbox/index/`, recommended cleanup workflows, and experiment status values.