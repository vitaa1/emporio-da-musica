# Empório da Música

## Development Environment

The project uses Python 3.13, a virtual environment created with `venv`, dependencies installed via `pip`, and version resolution managed by `pip-tools`.

The procedure below has been validated on Windows using PowerShell and Python 3.13.5.

### Setting up the environment

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

### Recording dependencies

The `pyproject.toml` file declares the direct dependencies:

- `project.dependencies`: runtime dependencies (currently empty).
- `project.optional-dependencies.dev`: development tools.

The `requirements-dev.txt` file records the resolved versions of both runtime and development dependencies, including indirect (transitive) dependencies. After modifying the declarations in `pyproject.toml`, regenerate the file:

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

The pinned versions have been validated on Windows using Python 3.13. Other operating systems will require their own validation. ### Local files

The `.venv` directory, Python caches, and `.env` files are ignored by Git. A `.env.example` file may be included in version control, provided it contains only examples and no actual secrets.