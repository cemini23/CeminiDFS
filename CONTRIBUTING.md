# Contributing to CeminiDFS

Thank you for your interest. CeminiDFS is a DIY NFL DFS projection pipeline. It
uses the MIT license. The operator submits every lineup. The agent does not Enter.

## Before you open a pull request

1. Read [`docs/REFUSED.md`](docs/REFUSED.md). The refused list is a guardrail.
2. Read [`docs/GPP-WORKFLOW.md`](docs/GPP-WORKFLOW.md). It names the accepted GPP path.
3. Keep one change per pull request. Explain the use case.
4. Run the tests and the linter.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,data,optimize]"
pytest
ruff check src tests
```

## Hard rules

A pull request must not:

- Add `draftfast` or any optimizer with no LICENSE.
- Add a scraper, a browser bot, or site automation.
- Add a site password, a token, or any secret. Use `.env` (gitignored).
- Enter, Submit, or late-swap for the user. The human is in the loop. The agent does not Enter.
- Commit a salary CSV, a `.env` file, or `reports/`.
- Retune FPPG, CIN, Chase, or weather from one Sunday.

Paid CSVs (Stokastic, FantasyLabs) are accuracy and ownership benchmarks only.
Do not scrape a paid site.

## Tests and style

- Tests live in `tests/`. Run `pytest` (no network; end-to-end tests need pydfs).
- Run `ruff check src tests` before you push. CI runs pytest and ruff on Python 3.11 and 3.12.
- Write chat replies, commit messages, and pull request text in ASD-STE100 Simplified Technical English (adapted). Use short, direct sentences.
- Do not edit `src/` or `tests/` for a documentation-only change.

## Docs

- Operator path: [`docs/SUNDAY.md`](docs/SUNDAY.md).
- GPP detail: [`docs/GPP-WORKFLOW.md`](docs/GPP-WORKFLOW.md).
- Human gate: [`docs/REVIEW-REPORTS.md`](docs/REVIEW-REPORTS.md).
- Refused list: [`docs/REFUSED.md`](docs/REFUSED.md).

## License

By contributing, you agree that your contribution is licensed under the MIT
License. See [`LICENSE`](LICENSE).
