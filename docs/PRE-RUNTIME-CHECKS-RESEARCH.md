# Pre-runtime checks for Python: research summary

**Goal:** Use linting, type checking, and unit tests during development **without modifying** the `.py` files, so scripts can be copied as-is to the runtime environment (e.g. TrueNAS).

**Conclusion:** All of the following can be done with **configuration only** (in `pyproject.toml` and/or separate config files). The tools **read** your source; they do not need to insert comments or change code. Your `.py` files stay portable.

---

## 1. Commonly used tools (overview)

| Category        | Purpose                         | Typical tools              | Modifies source? |
|----------------|----------------------------------|----------------------------|-------------------|
| **Linting**    | Style, bugs, complexity          | Ruff, Flake8, Pylint       | No (config only)  |
| **Type checking** | Static types, catch type errors | mypy, Pyright              | No (config only)  |
| **Formatting** | Consistent style                 | Ruff (format), Black       | Only if you run “format” and commit |
| **Unit tests** | Correctness, regressions         | pytest, unittest           | No                |

For “check only, don’t modify,” you run **lint** and **typecheck** and **tests**. You can avoid running **format** (or run it in a separate workflow that you don’t use before copy-to-runtime).

---

## 2. Linting

**What it does:** Analyses code for style issues, common bugs, and rule violations (unused imports, undefined names, etc.). Pure static analysis; no execution.

**Common choices:**

- **Ruff** (recommended): Single tool, very fast (Rust), replaces Flake8 + isort + often Black. Config in `pyproject.toml` under `[tool.ruff]`. No need to add `# noqa` etc. if you configure rules and exclusions in the config file.
- **Flake8:** Classic, plugin ecosystem. Config in `setup.cfg`, `.flake8`, or `pyproject.toml`.
- **Pylint:** More rules, heavier. Config in `.pylintrc` or `pyproject.toml`.

**Config location:** All of them support config in a **project file** (e.g. `pyproject.toml` or `.flake8`). You do **not** need to put config inside the `.py` files.

**Runtime:** Linters only **read** the files. They are not imported or run by your scripts. You install them as **dev dependencies** (or in a dev/CI environment). The copied scripts do not depend on them.

---

## 3. Type checking

**What it does:** Checks that type hints are used consistently and that types match (e.g. function return types, argument types). Catches many bugs before run.

**Common choices:**

- **mypy:** Standard, widely used. Config in `mypy.ini`, `setup.cfg`, or `pyproject.toml` under `[tool.mypy]`.
- **Pyright:** Fast, used by Pylance (VS Code). Config in `pyrightconfig.json` or `pyproject.toml` under `[tool.pyright]`.

**Config location:** Entirely in config files. You can set `exclude`, `strict`, per-module overrides, etc. No need to add `# type: ignore` in the scripts if you’re happy to fix the reported issues or relax options in config.

**Runtime:** Type checker only **reads** the code. It is not imported at runtime. Scripts can be copied without mypy/pyright.

---

## 4. Unit tests

**What it does:** Runs small tests (e.g. pure functions, or code with mocked IO) to verify behaviour and avoid regressions.

**Common choice:** **pytest**. Config in `pytest.ini`, `pyproject.toml` under `[tool.pytest.ini_options]`, or `conftest.py`. Tests live in separate files (e.g. `tests/`); the scripts under the project root are **not** modified.

**Runtime:** Tests are only run in development/CI. The scripts you copy to TrueNAS do not reference pytest. No change to the `.py` scripts for “just running tests.”

---

## 5. Keeping .py files untouched and portable

- **Linters and type checkers:** Configure them in `pyproject.toml` (or other config files). They only need to **read** your sources. No tool needs to write into `zfs-restic-backup.py` or `zfs-check-unlocked.py` for checks to work.
- **Formatting:** If you use Ruff (or Black) **format**, that **does** rewrite files. To keep “no modifications,” either:
  - Don’t run the formatter, and only run lint + typecheck + tests, or
  - Run format in a separate step and only commit the result when you explicitly want to.
- **Tests:** Live in `tests/` (or similar). The main scripts stay as they are; tests import and call functions. At runtime you copy only the scripts you need, not the test suite.
- **Dev-only install:** Use a virtualenv (or uv/poetry) and install ruff, mypy, pytest as **dev dependencies**. The runtime box only needs Python and the copied `.py` files; no need for those tools there.

So: **yes**, you can have linting, type checking, and unit tests as pre-runtime checks **without modifying** the production `.py` files, and still copy those files to the runtime environment as-is.

---

## 6. Suggested layout for this project

- **Config in one place:** `pyproject.toml` with:
  - `[tool.ruff]` (and optionally `[tool.ruff.format]`) for lint (and format, if you want it).
  - `[tool.mypy]` for type checking.
  - `[tool.pytest.ini_options]` for pytest (paths, options).
- **Dev dependencies:** Listed in `pyproject.toml` (e.g. under `[project.optional-dependencies]` dev or a dev group). Install with `pip install -e ".[dev]"` or `uv sync` in dev only.
- **Scripts:** `zfs-restic-backup.py`, `zfs-check-unlocked.py` stay at repo root; no extra comments or config inside them.
- **Tests:** e.g. `tests/` with `test_*.py` (or `*_test.py`). They import from the scripts (or from a small wrapper) and run assertions. Not copied to runtime.
- **CI/local:** Run `ruff check .`, `mypy .`, `pytest`. All read from config and sources; no writes to the two main scripts unless you explicitly run a formatter and commit.

That gives you pre-runtime checks (lint + typecheck + unit tests) while keeping the scripts safe to copy to the runtime environment without any changes.
