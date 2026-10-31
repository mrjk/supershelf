# Development

Python comes from `mise.toml`. That file pins Python 3.13.14. The package needs Python 3.13 or newer.

Package metadata, the `supershelf` script, and dependencies are in `pyproject.toml`. The lockfile is `uv.lock`. Dev dependencies include pytest. Documentation dependencies are in the `docs` group.

From the repository root, `task docs` serves this site. From `docs/`, `task serve` previews it, `task build` writes `docs/site`, and `task release` publishes that build.

From a checkout, install the package and run the tests with pytest at the repository root.

Layout:

- `src/supershelf`: the package
- `tests`: pytest modules
- `examples`: sample inputs
- `docs`: design notes and this documentation, under `docs/content`
