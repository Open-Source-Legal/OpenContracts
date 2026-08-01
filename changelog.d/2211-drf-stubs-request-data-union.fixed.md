- `opencontractserver/worker_uploads/views.py:94` — `djangorestframework-stubs`
  3.17.1 widened `request.data`'s type to `dict[str, Any] | list[Any]`
  (matching DRF's real behavior for bulk JSON array payloads), which surfaced
  a `union-attr` mypy error on `request.data.get(...)`. This view only accepts
  `MultiPartParser`, so `request.data` is always dict-like at runtime; added
  an `isinstance` narrowing consistent with the existing dict check two lines
  below rather than suppressing the type error.
