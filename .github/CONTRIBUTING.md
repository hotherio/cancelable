# Guidelines for contributing

## Table of Contents <!-- omit in toc -->

- [Guidelines for contributing](#guidelines-for-contributing)
  - [Summary](#summary)
    - [Contributors](#contributors)
    - [Maintainers](#maintainers)
  - [Git](#git)
  - [Python](#python)
    - [Python code style](#python-code-style)
    - [UV](#uv)
      - [Highlights](#highlights)
      - [Installation](#installation)
      - [Key commands](#key-commands)
  - [Docker](#docker)

## Summary

### Contributors

**PRs welcome!**

- **Consider starting a [discussion](https://docs.github.com/en/discussions) to see if there's interest in what you want to do.**
- **Submit PRs from feature branches on forks.**
- **Ensure PRs pass all CI checks.**
- **Maintain or increase test coverage.**

### Maintainers

- **Make `develop` the default branch.**
- **Merge PRs into `develop`.** Configure repository settings so that branches are deleted automatically after PRs are merged.
- **Only merge to `main` if [fast-forwarding](https://www.git-scm.com/book/en/v2/Git-Branching-Basic-Branching-and-Merging) from `develop`.**
- **Enable [branch protection](https://docs.github.com/en/free-pro-team@latest/github/administering-a-repository/about-protected-branches) on `develop` and `main`.**
- **Release workflow is fully automated.** This project uses [python-semantic-release](https://python-semantic-release.readthedocs.io/) for automated versioning:
  - Releases happen automatically when commits are pushed to `main`
  - Version is determined by analyzing [conventional commits](https://www.conventionalcommits.org/)
  - CHANGELOG.md is automatically updated
  - Git tags are created and GPG signed
  - Package is published to PyPI via Trusted Publishing
  - GitHub Release is created with changelog
  - Documentation is deployed automatically
  - **No manual tagging or version bumping required!**
  - For detailed information, see [Release Automation Guide](../docs/releases.md)
- **Use conventional commits.** All commit messages must follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:
  - `feat:` for new features (minor version bump)
  - `fix:` for bug fixes (patch version bump)
  - `docs:`, `chore:`, `ci:`, etc. for non-releasing changes
  - `feat!:` or `BREAKING CHANGE:` for breaking changes (major version bump)
  - Commit messages are validated before commit via lefthook
  - PR titles must also follow this format
  - See [Release Automation Guide](../docs/releases.md) for examples and best practices

## Git

- _[Why use Git?](https://www.git-scm.com/about)_ Git enables creation of multiple versions of a code repository called branches, with the ability to track and undo changes in detail.
- Install Git by [downloading](https://www.git-scm.com/downloads) from the website, or with a package manager like [Homebrew](https://brew.sh/).
- [Configure Git to connect to GitHub with SSH](https://docs.github.com/en/free-pro-team@latest/github/authenticating-to-github/connecting-to-github-with-ssh)
- [Fork](https://docs.github.com/en/free-pro-team@latest/github/getting-started-with-github/fork-a-repo) this repo
- Create a [branch](https://www.git-scm.com/book/en/v2/Git-Branching-Branches-in-a-Nutshell) in your fork.
- Commit your changes with a [conventional commit message](https://www.conventionalcommits.org/). See [Release Automation Guide](../docs/releases.md) for format and examples.
- Create a [pull request (PR)](https://docs.github.com/en/free-pro-team@latest/github/collaborating-with-issues-and-pull-requests/about-pull-requests) to incorporate your changes into the upstream project you forked.

## Python

### Python code style

- Python code is formatted with [Ruff](https://docs.astral.sh/ruff/). Configuration for Ruff is stored in _pyproject.toml_.
- Python imports are organized automatically with [isort](https://pycqa.github.io/isort/).
  - The isort package organizes imports in three sections:
    1. Standard library
    2. Dependencies
    3. Project
  - Within each of those groups, `import` statements occur first, then `from` statements, in alphabetical order.
  - You can run isort from the command line with `uv run isort .`.
  - Configuration for isort is stored in _pyproject.toml_.
- Other web code (JSON, Markdown, YAML) is formatted with [Prettier](https://prettier.io/).
- Code style is enforced with [pre-commit](https://pre-commit.com/), which runs [Git hooks](https://www.git-scm.com/book/en/v2/Customizing-Git-Git-Hooks).

  - Configuration is stored in _.pre-commit-config.yaml_.
  - Pre-commit can run locally before each commit (hence "pre-commit"), or on different Git events like `pre-push`.
  - Pre-commit is installed in the uv managed environment. To use:

    ```sh
    # after running `uv install`
    path/to/repo
    ❯ uv shell

    # install hooks that run before each commit
    path/to/repo
    .venv ❯ uvx pre-commit install

    # and/or install hooks that run before each push
    path/to/repo
    .venv ❯ pre-commit install --hook-type pre-push
    ```

  - Pre-commit is also useful as a CI tool. The GitHub Actions workflows run pre-commit hooks with [GitHub Actions](https://github.com/features/actions).

### UV

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

#### Highlights

- **Automatic virtual environment management**: UV automatically manages the `virtualenv` for the application.
- **Automatic dependency management**: rather than having to run `pip freeze > requirements.txt`, UV automatically manages the dependency file (called _pyproject.toml_), and enables SemVer-level control over dependencies like [npm](https://semver.npmjs.com/). UV also manages a lockfile (called _uv.lock_), which is similar to _package-lock.json_ for npm. UV uses this lockfile to automatically track specific versions and hashes for every dependency.
- **Dependency resolution**: UV will automatically resolve any dependency version conflicts. pip did not have dependency resolution [until the end of 2020](https://pip.pypa.io/en/latest/user_guide/#changes-to-the-pip-dependency-resolver-in-20-3-2020).
- **Dependency separation**: UV can maintain separate lists of dependencies for development and production in the _pyproject.toml_. Production installs can skip development dependencies to speed up Docker builds.
- **Builds**: UV has features for easily building the project into a Python package.

#### Installation

The recommended installation method is through the [UV custom installer](hhttps://docs.astral.sh/uv/getting-started/installation/), which vendorizes dependencies into an isolated environment, and allows you to update UV with `uv self update`.

You can also install UV however you prefer to install your user Python packages (`pipx install uv`, `pip install --user uv`, etc). Use the standard update methods with these tools (`pipx upgrade uv`, `pip install --user --upgrade uv`, etc).

#### Key commands

```sh
# Basic usage:
uv install  # create virtual environment and install dependencies
uv show --tree  # list installed packages
uv add PACKAGE@VERSION # add a package to production dependencies, like pip install
uv add PACKAGE@VERSION --dev # add a package to development dependencies
uv update  # update dependencies (not available with standard tools)
uv version  # list or update version of this package
uv shell  # activate the virtual environment, like source venv/bin/activate
uv run COMMAND  # run a command within the virtual environment
uv env info  # manage environments
uv config virtualenvs.in-project true  # configure uv to install virtualenvs into .venv
uv export -f requirements.txt > requirements.txt --dev  # export dependencies
```

## Docker

- **[Docker](https://www.docker.com/)** is a technology for running lightweight virtual machines called **containers**.
  - An **image** is the executable set of files read by Docker.
  - A **container** is a running image.
  - The **[Dockerfile](https://docs.docker.com/engine/reference/builder/)** tells Docker how to build the container.
- To [get started with Docker](https://www.docker.com/get-started):
  - Ubuntu Linux: follow the [instructions for Ubuntu Linux](https://docs.docker.com/install/linux/docker-ce/ubuntu/), making sure to follow the [postinstallation steps](https://docs.docker.com/install/linux/linux-postinstall/) to activate the Docker daemon.
  - macOS and Windows: install [Docker Desktop](https://www.docker.com/products/docker-desktop) (available via [Homebrew](https://brew.sh/) with `brew cask install docker`).
- <details><summary>Expand this details element for more <a href="https://docs.docker.com/engine/reference/commandline/cli/">useful Docker commands</a>.</summary>

  ```sh
  # Log in with Docker Hub credentials to pull images
  docker login
  # List images
  docker images
  # List running containers: can also use `docker container ls`
  docker ps
  # View logs for the most recently started container
  docker logs -f $(docker ps -q -n 1)
  # View logs for all running containers
  docker logs -f $(docker ps -aq)
  # Inspect a container (web in this example) and return the IP Address
  docker inspect web | grep IPAddress
  # Stop a container
  docker stop # container hash
  # Stop all running containers
  docker stop $(docker ps -aq)
  # Remove a downloaded image
  docker image rm # image hash or name
  # Remove a container
  docker container rm # container hash
  # Prune images
  docker image prune
  # Prune stopped containers (completely wipes them and resets their state)
  docker container prune
  # Prune everything
  docker system prune
  # Open a shell in the most recently started container (like SSH)
  docker exec -it $(docker ps -q -n 1) /bin/bash
  # Or, connect as root:
  docker exec -u 0 -it $(docker ps -q -n 1) /bin/bash
  # Copy file to/from container:
  docker cp [container_name]:/path/to/file destination.file
  ```

  </summary>
