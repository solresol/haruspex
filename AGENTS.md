# Repository Guidelines

## Project Structure & Module Organization
- Core work lives in `.claude/skills/astro-literature/`. Scripts in `scripts/` provide CLIs for ADS queries, citation classification, database management, and migrations. Docs and usage notes sit in `docs/`, while `examples.md` and `SKILL.md` explain the skill workflow.
- The SQLite knowledge base defaults to `~/.astro-literature/citations.db`; CLI entry points read/write there. `uv.lock`/`pyproject.toml` define dependencies and console scripts (`litdb`, `ads-search`, `citation-analysis`, etc.).

## Setup, Build & Run Commands
- Install deps with `cd .claude/skills/astro-literature && uv sync`.
- Quick ADS query: `uv run scripts/ads_search.py --query 'abstract:"dark matter" year:2023-' --rows 10`. Set `ADS_DEV_KEY` or `~/.ads/dev_key` before running.
- Inspect or create sessions: `uv run litdb session list` or `uv run litdb session create --question "..."`.
- Classification pipeline (simplified): `uv run scripts/classify_citations.py --bibcode <id>` and `uv run scripts/reclassify_citations.py --help` for options. Use `uv run scripts/migrate_to_postgresql.py --help` before touching migrations.
- No compiled build step; commands above double as smoke tests. Add new CLIs under `scripts/` and wire them via `[project.scripts]` in `pyproject.toml`.

## Coding Style & Naming Conventions
- Python 3.10+, 4-space indentation, PEP 8 spacing. Prefer `pathlib.Path` over `os.path` and inject config via env vars.
- Functions and modules use `snake_case`; classes `CapWords`; CLI entrypoints expose a `main()` guarded by `if __name__ == "__main__":`.
- Keep docstrings concise; log/print actionable errors (e.g., missing tokens). Avoid committing generated databases or `__pycache__/`.

## Testing Guidelines
- No automated suite is present. When adding logic, include targeted checks (e.g., small ADS queries with `rows` capped) and note expected outputs in PRs.
- If you add tests, place them under a new `tests/` directory and run with `uv run -m pytest`; keep network calls stubbed or fixture-backed to avoid flaky runs.

## Commit & Pull Request Guidelines
- Git history favors short, imperative commits (e.g., `Add subagent architecture`, `Add REFUTING classification`). Follow that style and keep each commit scoped.
- PRs should include: summary of behavior, linked issues (if any), CLI examples or screenshots when UX changes, and a checklist of manual checks run. Surface schema or migration impacts explicitly.

## Security & Configuration Notes
- Do not commit API keys or local DB files. Store ADS tokens in `ADS_DEV_KEY` or `~/.ads/dev_key`.
- SQLite lives in the home directory; handle copies carefully and avoid embedding user data in logs. PostgreSQL migration scripts assume credentials are provided via environment variables.
