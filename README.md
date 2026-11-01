# Empório da Música

## Development Environment

The project uses Python 3.13, a virtual environment created with `venv`, dependencies installed via `pip`, and version resolution managed by `pip-tools`.

The Windows procedure below has been validated locally using PowerShell and Python 3.13.5. CI is configured to check installation on Windows, Linux, and macOS with Python 3.13; results are available in GitHub Actions after the workflow runs.

### Setting up the environment

#### Windows (PowerShell)

In the directory where the project was cloned:

```powershell
Set-Location C:\emporio-da-musica
py -3.13 --version
```

If a `.venv` directory does not yet exist, create the environment:

```powershell
py -3.13 -m venv .venv
```

Install the development dependencies using the recorded versions:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements-dev.txt
```

### Using and verifying the environment

Run Python using the path to the `.venv`. There is no need to activate the environment:

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip --version
.\.venv\Scripts\python.exe -m pip check
```

The path displayed by `pip` should point to the project's `.venv`. The `pip check` command verifies the declared compatibility between installed packages; it does not replace application-level testing.

### Linux and macOS

Install Python 3.13 using the method appropriate for your operating system. From the root of your clone, create the environment if `.venv` does not already exist, then install and verify the dependencies:

```sh
python3.13 --version
python3.13 -m venv .venv
./.venv/bin/python -m pip install -r requirements-dev.txt
./.venv/bin/python --version
./.venv/bin/python -m pip --version
./.venv/bin/python -m pip check
./.venv/bin/python -m piptools compile --version
```

Activation is not required. On Linux, your distribution may require a separate package providing `venv` support for Python 3.13.

### Recording dependencies

The `pyproject.toml` file declares the direct dependencies:

- `project.dependencies`: runtime dependencies (currently empty).
- `project.optional-dependencies.dev`: development tools.

The `requirements-dev.txt` file records the resolved versions of both runtime and development dependencies, including indirect (transitive) dependencies. Windows with Python 3.13 is currently the reference environment for generating this file, since dependency resolution can differ across platforms. After modifying the declarations in `pyproject.toml`, regenerate the file on Windows:

```powershell
.\.venv\Scripts\python.exe -m piptools compile --extra=dev --allow-unsafe --strip-extras --output-file=requirements-dev.txt pyproject.toml
```

Review the changes and install the result:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements-dev.txt
.\.venv\Scripts\python.exe -m pip check
```

Do not edit `requirements-dev.txt` manually. Include this file in version control alongside the corresponding changes in `pyproject.toml`.

The `--allow-unsafe` option includes tools like `pip` and `setuptools` when pinning versions. The `--strip-extras` option removes references to optional groups from the generated lines, while keeping their resolved dependencies intact.

The runtime dependency file, `requirements.txt`, will be introduced once the first application dependency is added.

### Recreating the environment

The following commands use Windows PowerShell. On Linux and macOS, rename `.venv` to an unused backup name, then follow the setup commands above to recreate it.

Close any processes that are using the `.venv` directory. Ensure you are at the root of the cloned repository, then rename the existing environment to a backup name that is not currently in use:

```powershell
Rename-Item -LiteralPath .\.venv -NewName .venv-backup
```

Create a new environment and install the pinned versions:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements-dev.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m piptools compile --version
```

Once the new environment has been validated, remove the `.venv-backup` folder. Do not include the backup in any commits.

### Continuous integration

For pull requests targeting `main` and pushes to `main`, GitHub Actions creates a fresh virtual environment on Windows, Linux, and macOS with Python 3.13. Each platform installs `requirements-dev.txt`, runs `pip check`, and verifies that pip-tools starts successfully. These checks cover the runner's default architecture, not every architecture supported by each operating system.

The Windows job also regenerates `requirements-dev.txt` and fails if it differs from the committed file. The three checks are named `setup-python-windows`, `setup-python-linux`, and `setup-python-macos`. All three should be required in the protection rules for `main` once available on GitHub.

These checks validate dependency setup; application tests will be added when application code is introduced.

### Local files

The `.venv` directory, Python caches, and `.env` files are ignored by Git. A `.env.example` file may be included in version control, provided it contains only examples and no actual secrets.
