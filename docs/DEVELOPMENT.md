# Development and validation

Linux, macOS, or WSL (from the project root, after the README setup):

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
```

Windows (PowerShell, from the project root):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

The 761 deterministic tests need no model or credentials. They run in CI on Linux, Windows, and macOS.

On 2026-11-03, a clean copy of this documentation's working tree was verified on WSL2 with Python 3.13 in a new virtual environment: installing the pins, the data validation, the offline commands, and the model example under Quick start all worked, as did the checks above. The Quick start's PowerShell commands were also run manually on Windows with a fresh clone. A single example run does not guarantee identical model output later.

Model behavior is evaluated separately, because it depends on a local server and is not deterministic. The following command is for Linux/macOS/WSL; when Ollama runs on Windows, use the host URL described in the [README](../README.md):

```sh
.venv/bin/python -m evals.suite --url http://localhost:11434 --output /tmp/emporio-evaluation.json
```

The latest recorded full-suite run passed 49 of 49 turns across 19 scenarios. The cases were informed by development, so this is a regression check rather than an independent accuracy measure. [The evaluation report](EVALUATION.md) keeps the earlier failing runs and their corrections, including one provider error whose cause was not determined.

## Dependency maintenance (Linux/WSL)

Use Python 3.13 with a project-local `.venv`, keeping Windows and Linux environments separate:

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip check
```

To apply formatting and safe lint fixes:

```sh
.venv/bin/python -m ruff check --fix .
.venv/bin/python -m ruff format .
```

`pyproject.toml` declares direct dependencies. `requirements.txt` and `requirements-dev.txt` are generated pins: never edit them by hand, and regenerate both together on Linux or WSL when declarations change:

```sh
CUSTOM_COMPILE_COMMAND='pip-compile --allow-unsafe --output-file=requirements.txt --strip-extras pyproject.toml' .venv/bin/python -m piptools compile --allow-unsafe --strip-extras --output-file=requirements.txt pyproject.toml
CUSTOM_COMPILE_COMMAND='pip-compile --allow-unsafe --extra=dev --output-file=requirements-dev.txt --strip-extras pyproject.toml' .venv/bin/python -m piptools compile --extra=dev --allow-unsafe --strip-extras --output-file=requirements-dev.txt pyproject.toml
```

Pull requests and pushes to `main` run `setup-python-windows`, `setup-python-linux`, and `setup-python-macos`. Each installs the pins in a fresh environment and runs `pip check`, Ruff, and pytest. Only Linux regenerates the pins and compares them. No credentials are needed. [AGENTS.md](../AGENTS.md) holds the repository conventions.

