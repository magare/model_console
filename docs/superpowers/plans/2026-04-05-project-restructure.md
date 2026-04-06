# Project Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the Python backend into a `src/model_console` package with logical subpackages, preserve existing import compatibility, and clean the root/docs/scripts layout without breaking runtime behavior.

**Architecture:** Create a new `src/model_console` tree organized by responsibility, then copy each existing module into its target package with import rewrites. Keep the old public module paths as thin wrappers so existing tests, entry points, and downstream imports still resolve while the codebase adopts the new internal structure.

**Tech Stack:** Python 3.9+, setuptools editable installs, `unittest`, YAML + JSON schema config

---

### Task 1: Lock regression coverage for the move

**Files:**
- Create: `tests/test_000_path_setup.py`
- Create: `tests/test_package_layout.py`
- Test: `python3 -m unittest tests.test_package_layout.PackageLayoutTests.test_new_subpackage_imports_are_available -q`
- Test: `python3 -m unittest tests.test_package_layout.ScriptPortabilityTests.test_scripts_do_not_hardcode_local_home_paths -q`

- [x] **Step 1: Add a test bootstrap that adds `src/` to `sys.path` when present**
- [x] **Step 2: Add failing tests for the new subpackage imports and legacy shim compatibility**
- [x] **Step 3: Add failing tests that reject hardcoded `/Users/magare/...` script paths**
- [x] **Step 4: Run the new tests and confirm they fail for the expected reasons**

### Task 2: Move backend modules into `src/model_console`

**Files:**
- Create: `src/model_console/**`
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `docs/development.md`
- Modify: `docs/repo-map.md`

- [ ] **Step 1: Create the new package tree and move modules into `cli`, `core`, `agents`, `contracts`, `observability`, `server`, and `safety`**
- [ ] **Step 2: Rewrite internal imports to target the new package paths**
- [ ] **Step 3: Add compatibility wrapper modules for old import paths and runnable modules**
- [ ] **Step 4: Update packaging metadata for the `src/` layout**

### Task 3: Clean project layout outside the package

**Files:**
- Modify: `scripts/run_product_brief_batch.py`
- Modify: `scripts/generate_product_brief_input.py`
- Create: `docs/project-status.md`
- Create: `docs/lessons-learned.md`
- Delete: `tasks/todo.md`
- Delete: `tasks/lessons.md`
- Delete: `run_locally.txt`
- Delete: `setup.py`

- [ ] **Step 1: Replace hardcoded script paths with repo-relative or environment-driven discovery**
- [ ] **Step 2: Move project meta docs out of `tasks/`**
- [ ] **Step 3: Fold local setup instructions into maintained docs and remove redundant root files**

### Task 4: Reorganize tests and verify the result

**Files:**
- Move: `tests/*.py` into mirrored subdirectories where useful
- Test: `python3 -m unittest discover -s tests -q`
- Test: `python3 -m compileall src/model_console`

- [ ] **Step 1: Move tests into a structure that mirrors the new package layout**
- [ ] **Step 2: Run the full test suite**
- [ ] **Step 3: Run a compilation pass over `src/model_console`**
- [ ] **Step 4: Update docs to describe the new tree and commands**
