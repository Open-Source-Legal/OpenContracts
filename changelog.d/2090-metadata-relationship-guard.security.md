- **Bound the two remaining unguarded ZIP-member reads in the folder-structure importer: `meta.csv` and `relationships.csv`.**
  `parse_metadata_file` (`opencontractserver/utils/metadata_file_parser.py`) and
  `parse_relationship_file` (`opencontractserver/utils/relationship_file_parser.py`), both invoked
  from `import_zip_with_folder_structure` (`opencontractserver/tasks/import_tasks.py`), still read
  their member with a raw, unbounded `ZipExtFile.read()` after the rest of this PR's hardening pass.
  Unlike ordinary document members, `meta.csv`/`relationships.csv` are special-cased out of
  `validate_zip_for_import`'s per-member declared-size check entirely (`is_metadata_file`/
  `is_relationship_file` short-circuit the loop before the size check runs), so a crafted entry with a
  high compression ratio (or a large declared size) was never rejected pre-read either — the exact
  vulnerability class this PR set out to close. Both now route through `read_zip_member_bounded()`,
  bounded by `ZIP_MAX_SINGLE_FILE_SIZE_BYTES`, matching the treatment already given to `labels.json`
  and per-document reads in the same function. Regression tests:
  `test_zip_import_integration.py::TestMetadataFileImport::test_oversized_metadata_file_rejected_not_read_unbounded`,
  `test_zip_import_integration.py::TestRelationshipFileImport::test_oversized_relationship_file_rejected_not_read_unbounded`.
