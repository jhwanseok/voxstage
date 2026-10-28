# voxstage-normalize

Spoken numbers, days, dates and times to exact values, for English and Korean (R11). It imports nothing from
`voxstage` and has no dependencies. Dates resolve against a clock you pass in, and the rule used is returned so a caller
can trace it. Cases and rules are described in [docs/flow-spec.md](../docs/flow-spec.md); the tests are
`tests/test_normalize.py` in the repository root.

Split out of `voxstage/normalize/` by decision R11-4 as a separate package in the same repository (not yet published).

```
pip install -e normalize
```

A checkout that has not installed it still works: `voxstage/__init__.py` puts this folder on the path.
