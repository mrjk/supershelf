# Development

Python, uv, and task come from `mise.toml`. Python is pinned to 3.13.14. The package needs Python 3.13 or newer.

Package metadata, the `supershelf` script, and dependencies are in `pyproject.toml`. The lockfile is `uv.lock`. Dev dependencies include pytest. Documentation dependencies are in the `docs` group.

From the repository root, `task test` runs pytest and `task docs` serves this site. From `docs/`, `task serve` previews the site and `task build` writes `docs/site`. Both write the command listings and the version line into the pages first. `task release` publishes that build when `GITHUB_OWNER` is set in `.env`. An empty `GITHUB_OWNER` stops the release before the build.

Layout:

- `README.md`: repository overview, included as the documentation home page
- `CODE_OF_CONDUCT.md`: project conduct
- `src/supershelf`: the package
- `tests`: pytest modules
- `examples`: sample inputs
- `docs`: design notes and this documentation, under `docs/content`
