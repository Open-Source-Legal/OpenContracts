- Moved `MAX_DERIVED_MESSAGE_TITLE_CHARS` (from
  `config/graphql/conversation_mutations.py`) and `MAX_WORKSPACE_FILENAME_CHARS`
  (from `opencontractserver/corpuses/services/workspace.py`) into
  `opencontractserver/constants/truncation.py`, and replaced the inline
  `1024 * 1024` CA-certificate size cap in
  `opencontractserver/enrichment/authority_import_artifacts.py` with
  `MAX_EXTRA_CA_CERTIFICATE_BYTES` in `opencontractserver/constants/safe_http.py`
  — per the shared-constants convention in CLAUDE.md.
- Added a regression test pinning that a billion-laughs XML payload is rejected
  as malformed on both authority-source XML paths
  (`opencontractserver/tests/test_authority_sources.py`). The stdlib
  `ElementTree` calls in `authority_sources.py` are safe because the shipped
  runtime (`python:3.12.13-slim-bookworm`, expat 2.7.4) enables expat's input
  amplification limit by default; the test fails if a future base image
  regresses below expat 2.6, at which point `defusedxml` becomes necessary.
