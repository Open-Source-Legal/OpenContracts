- Fixed an `AttributeError` crash in `Datacell._validate_manual_entry`
  (`opencontractserver/extracts/models.py`, issue #1986 item 7). The "required"
  check in the missing-`value` branch called
  `self.column.validation_config.get("required")` *before* the
  `config = self.column.validation_config or {}` guard, so validating a
  manual-entry datacell with no `value` key on a column whose `validation_config`
  is `None` (a nullable JSONField — legitimately null on explicitly-cleared or
  legacy rows) raised `'NoneType' object has no attribute 'get'`. The `or {}`
  guard is now resolved once at the top of the method and reused, so a config-less
  column validates cleanly (nothing is required) while a column that *does* set
  `required` still raises the expected `ValidationError`.
