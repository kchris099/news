# Development files

This directory contains repository-only files that are not part of the deployed
Worldline website.

- `tests/` contains the automated test suite and fixtures.
- `previews/` contains screenshots used for visual review and documentation.
- `pytest.ini` contains test-runner configuration.
- `requirements-dev.txt` contains optional local development dependencies.

Run the test suite from the repository root:

```powershell
python -m pytest -q -c development/pytest.ini development/tests
```

The GitHub Pages workflow builds an explicit production artifact. It does not
copy this directory, the data-generation scripts, private build configuration,
or local caches into the published site.
