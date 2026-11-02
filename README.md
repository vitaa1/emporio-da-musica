# Empório da Música

## Development environment

Use Python 3.13 with a project-local virtual environment. Development and dependency generation use Linux/WSL (Ubuntu); CI also checks installation on Windows and macOS. Keep Windows and Linux environments separate.

### Install Python and dependencies

If Python 3.13 is unavailable, install it with [uv](https://docs.astral.sh/uv/getting-started/installation/):

```sh
curl -LsSf https://astral.sh/uv/install.sh -o /tmp/uv-install.sh
sh /tmp/uv-install.sh
~/.local/bin/uv python install 3.13
~/.local/bin/python3.13 --version
```

From the repository root, create `.venv` only if it does not exist, then install the pinned dependencies:

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

If the interpreter is not on PATH, use `~/.local/bin/python3.13`. Activation is optional: use explicit `.venv/bin/python` paths. On Windows, create a separate environment with `py -3.13 -m venv .venv` and use `.\.venv\Scripts\python.exe` for subsequent commands.

### Verify the environment

```sh
.venv/bin/python --version
.venv/bin/python -m pip --version
.venv/bin/python -m pip check
.venv/bin/python -m piptools compile --version
.venv/bin/python -m ruff --version
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
```

Python must be 3.13.x and pip must belong to the project environment. There is no application or test suite yet; Ruff may report that no Python files exist. These commands validate tooling, not application behavior.

### Style and formatting

`.editorconfig` defines UTF-8, LF endings, a final newline, four-space indentation, and two spaces for YAML/JSON. Markdown preserves trailing spaces used for line breaks. Use an editor with EditorConfig support; no editor-specific configuration is required.

Ruff configuration lives in `pyproject.toml`: Python 3.13, 88-column formatting, double quotes, basic error checks (`E4`, `E7`, `E9`, `F`), and import sorting (`I`). Local agent tooling and environment backups are excluded. See the [Ruff configuration reference](https://docs.astral.sh/ruff/configuration/).

To apply formatting and safe lint fixes, then review the diff:

```sh
.venv/bin/python -m ruff check --fix .
.venv/bin/python -m ruff format .
```

### Generate dependencies

`pyproject.toml` declares direct dependencies; `requirements-dev.txt` pins development dependencies and their transitive dependencies. Runtime dependencies are empty. Introduce `requirements.txt` with the first runtime dependency.

Linux/WSL with Python 3.13 is now the generation reference, replacing Windows to match the development environment. The Linux CI job regenerates the file and checks for differences; all three platforms still install it and run setup checks. `colorama` is explicitly declared to retain the existing Windows dependency of `build` in this shared file. Review platform-specific dependencies whenever adding tools; a Linux-generated file alone does not guarantee compatibility elsewhere.

Generate in the reference environment using the installed pinned pip-tools, without manually editing the output:

```sh
CUSTOM_COMPILE_COMMAND='pip-compile --allow-unsafe --extra=dev --output-file=requirements-dev.txt --strip-extras pyproject.toml' .venv/bin/python -m piptools compile --extra=dev --allow-unsafe --strip-extras --output-file=requirements-dev.txt pyproject.toml
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip check
```

Review and commit declarations and generated pins together. Do not use `--upgrade` unless deliberately updating existing dependencies. Windows/macOS contributors should use Linux/WSL for generation.

### Recreate the environment

Stop processes using `.venv` and deactivate it if active. On Linux/WSL, rename it to an unused backup name:

```sh
mv -T -n .venv .venv-backup
```

Confirm `.venv` no longer exists before creating and installing again. Remove the backup after validating the new environment. Never commit environments or backups.

### Continuous integration

Pull requests targeting `main` and pushes to `main` run `setup-python-windows`, `setup-python-linux`, and `setup-python-macos`. Each creates a fresh Python 3.13 environment, installs the pins, runs `pip check`, verifies pip-tools, and checks Ruff lint and formatting. Only Linux regenerates dependencies and compares the result with the committed file.

Keep all three checks required before merge. No provider credentials are needed. New workflow changes still require a remote CI run before their cross-platform results can be claimed.

### Local configuration

Virtual environments, backups, Python/Ruff caches, and `.env` files are ignored. Commit `.env.example` only with nonsecret example values.
