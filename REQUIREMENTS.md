# Requirements

## Runtime

- Python 3.11+
- SQLite 3, usually provided by macOS and Python's standard `sqlite3` module
- ADB, required only for connected Android publishing workflows

## Operator Tools

- DB Browser for SQLite 3.13.1+
  - Purpose: inspect `data/mcn_ops.sqlite`, including JSON columns such as `raw_json`, `source_package_json`, and `material_understanding_json`.
  - macOS install target: `/Applications/DB Browser for SQLite.app`
  - Official release source: `https://github.com/sqlitebrowser/sqlitebrowser/releases`

## External Services

- MXNZP credentials for real Douyin collection:
  - `MXNZP_APP_ID`
  - `MXNZP_APP_SECRET`
  - optional `DOUYIN_COOKIE`

## Python Package Dependencies

The project intentionally has no required third-party Python dependencies at this stage. Install the local CLI with:

```bash
python -m pip install -e .
```
