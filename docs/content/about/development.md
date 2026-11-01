# Development

Python, uv, and task come from `mise.toml`. Python is pinned to 3.13.14. The package needs Python 3.13 or newer.

Package metadata, the `supershelf` script, and dependencies are in `pyproject.toml`. The lockfile is `uv.lock`. Dev dependencies include pytest. Documentation dependencies are in the `docs` group.

From the repository root, `task test` runs pytest, `task docs` serves this site, `task docs:build` writes `docs/site`, and `task ci` runs the tests and that build. `task docs:release` publishes the site when `GITHUB_OWNER` is set in `.env` or the environment. An empty `GITHUB_OWNER` stops the release before the build. From `docs/`, the same commands are `task serve`, `task build`, and `task release`.

GitHub Actions installs the tools from `mise.toml`, then calls task. Each workflow has its own Run workflow button:

- `ci` (`.github/workflows/ci.yml`): `mise x -- task test` and `mise x -- task docs:build`, on a pull request, on a push to `main`, `dev`, or `dev-*`, and on dispatch. After both succeed, a push to `main` also runs `mise x -- task docs:release`.
- `test` (`.github/workflows/test.yml`): `mise x -- task test`, on dispatch only
- `docs:build` (`.github/workflows/docs.yml`): `mise x -- task docs:build`, on dispatch only
- `docs:release` (`.github/workflows/deploy-website.yml`): `mise x -- task docs:release`, on dispatch only. The branch you pick in that dialog is the one that is published.

Layout:

- `README.md`: repository overview, included as the documentation home page
- `CODE_OF_CONDUCT.md`: project conduct
- `src/supershelf`: the package
- `tests`: pytest modules
- `examples`: sample inputs
- `docs`: design notes and this documentation, under `docs/content`
