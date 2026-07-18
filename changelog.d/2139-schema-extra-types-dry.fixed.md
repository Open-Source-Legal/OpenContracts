- `config/graphql/schema.py`: collapsed the ~44 hand-copied
  `_extra_types += [v for v in vars(_module).values() if hasattr(v,
  "__strawberry_definition__")]` blocks (one per ported module, ~190 lines) into
  a single loop over an explicit `_extra_type_modules` list, per review
  feedback on PR #2139. Behavior-identical (same modules, same iteration order,
  same filter) — confirmed by `test_schema_parity.py`'s golden-SDL diff, which
  still passes with zero drift.
