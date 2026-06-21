- `AuthorityKeyEquivalence` now has a DB-level `CheckConstraint`
  (`authority_key_equiv_no_self_reference`, migration `annotations/0098`)
  forbidding self-referential rows (`from_key == to_key`). The
  `AuthorityKeyEquivalenceService` already rejected identical keys in Python, but
  a direct ORM insert / admin action / data import bypassed that guard and a
  self-row would let `find_authority_target` "hop" a key onto itself. The
  constraint makes the invariant unbypassable
  (`opencontractserver/annotations/models.py`); covered by
  `test_db_constraint_rejects_self_referential_row`
  (`opencontractserver/tests/test_authority_mapping_crud.py`). Run `migrate` on
  deploy.
