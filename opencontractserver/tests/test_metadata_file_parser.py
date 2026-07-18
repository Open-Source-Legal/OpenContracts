"""
Unit tests for metadata_file_parser module.
"""

import io
import zipfile
from unittest import TestCase

from opencontractserver.utils.metadata_file_parser import (
    METADATA_FILE_NAMES,
    detect_metadata_file,
    is_metadata_file,
    parse_csv_metadata,
    parse_metadata_file,
)


class TestDetectMetadataFile(TestCase):
    """Tests for detect_metadata_file function."""

    def test_detect_meta_csv(self):
        """Detects meta.csv at root."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("meta.csv", "source_path,title\n")
            zf.writestr("doc.pdf", b"pdf content")
        buffer.seek(0)

        with zipfile.ZipFile(buffer, "r") as zf:
            result = detect_metadata_file(zf)
            self.assertEqual(result, "meta.csv")

    def test_detect_metadata_csv(self):
        """Detects metadata.csv at root."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("metadata.csv", "source_path,title\n")
        buffer.seek(0)

        with zipfile.ZipFile(buffer, "r") as zf:
            result = detect_metadata_file(zf)
            self.assertEqual(result, "metadata.csv")

    def test_detect_uppercase_meta_csv(self):
        """Detects META.csv at root."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("META.csv", "source_path,title\n")
        buffer.seek(0)

        with zipfile.ZipFile(buffer, "r") as zf:
            result = detect_metadata_file(zf)
            self.assertEqual(result, "META.csv")

    def test_no_metadata_file(self):
        """Returns None when no metadata file present."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("doc.pdf", b"pdf content")
        buffer.seek(0)

        with zipfile.ZipFile(buffer, "r") as zf:
            result = detect_metadata_file(zf)
            self.assertIsNone(result)

    def test_ignores_nested_meta_csv(self):
        """Ignores meta.csv in subdirectory."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("subdir/meta.csv", "source_path,title\n")
        buffer.seek(0)

        with zipfile.ZipFile(buffer, "r") as zf:
            result = detect_metadata_file(zf)
            self.assertIsNone(result)

    def test_priority_order(self):
        """meta.csv takes priority over metadata.csv."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("metadata.csv", "source_path,title\n")
            zf.writestr("meta.csv", "source_path,title\n")
        buffer.seek(0)

        with zipfile.ZipFile(buffer, "r") as zf:
            result = detect_metadata_file(zf)
            self.assertEqual(result, "meta.csv")


class TestIsMetadataFile(TestCase):
    """Tests for is_metadata_file function."""

    def test_meta_csv_at_root(self):
        """meta.csv at root is recognized."""
        self.assertTrue(is_metadata_file("meta.csv"))

    def test_metadata_csv_at_root(self):
        """metadata.csv at root is recognized."""
        self.assertTrue(is_metadata_file("metadata.csv"))

    def test_uppercase_variants(self):
        """Uppercase variants are recognized."""
        self.assertTrue(is_metadata_file("META.csv"))
        self.assertTrue(is_metadata_file("METADATA.csv"))

    def test_nested_not_recognized(self):
        """meta.csv in subdirectory is not recognized."""
        self.assertFalse(is_metadata_file("subdir/meta.csv"))
        self.assertFalse(is_metadata_file("a/b/meta.csv"))

    def test_other_files_not_recognized(self):
        """Other CSV files are not recognized as metadata."""
        self.assertFalse(is_metadata_file("data.csv"))
        self.assertFalse(is_metadata_file("relationships.csv"))
        self.assertFalse(is_metadata_file("meta.txt"))


class TestParseCsvMetadata(TestCase):
    """Tests for parse_csv_metadata function."""

    def test_parse_basic_metadata(self):
        """Parses basic metadata with title and description."""
        content = """source_path,title,description
docs/contract.pdf,Master Agreement,The main contract
docs/amendment.pdf,Amendment #1,First amendment
"""
        result = parse_csv_metadata(content)

        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.metadata), 2)
        self.assertEqual(len(result.errors), 0)

        meta1 = result.metadata["/docs/contract.pdf"]
        self.assertEqual(meta1.title, "Master Agreement")
        self.assertEqual(meta1.description, "The main contract")

        meta2 = result.metadata["/docs/amendment.pdf"]
        self.assertEqual(meta2.title, "Amendment #1")
        self.assertEqual(meta2.description, "First amendment")

    def test_parse_title_only(self):
        """Parses metadata with only title column."""
        content = """source_path,title
file.pdf,Custom Title
"""
        result = parse_csv_metadata(content)

        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.metadata), 1)

        meta = result.metadata["/file.pdf"]
        self.assertEqual(meta.title, "Custom Title")
        self.assertIsNone(meta.description)

    def test_parse_description_only(self):
        """Parses metadata with only description column."""
        content = """source_path,description
file.pdf,A detailed description
"""
        result = parse_csv_metadata(content)

        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.metadata), 1)

        meta = result.metadata["/file.pdf"]
        self.assertIsNone(meta.title)
        self.assertEqual(meta.description, "A detailed description")

    def test_empty_values_ignored(self):
        """Empty values don't create metadata entries."""
        content = """source_path,title,description
file1.pdf,Has Title,
file2.pdf,,Has Description
file3.pdf,,
"""
        result = parse_csv_metadata(content)

        self.assertTrue(result.is_valid)
        # file3.pdf has no metadata values, so it's not included
        self.assertEqual(len(result.metadata), 2)
        self.assertIn("/file1.pdf", result.metadata)
        self.assertIn("/file2.pdf", result.metadata)
        self.assertNotIn("/file3.pdf", result.metadata)

    def test_missing_source_path_column(self):
        """Fails if source_path column is missing."""
        content = """title,description
Title,Description
"""
        result = parse_csv_metadata(content)

        self.assertFalse(result.is_valid)
        self.assertIn("Missing required column: source_path", result.errors)

    def test_no_metadata_columns_warning(self):
        """Warns if no metadata columns beyond source_path.

        (Wording updated when the optional ``external_id`` column was added
        to the contract — the warning now names all three optional columns.)
        """
        content = """source_path
file.pdf
"""
        result = parse_csv_metadata(content)

        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.metadata), 0)
        self.assertTrue(
            any(
                "no title, description, or external_id columns" in w
                for w in result.warnings
            )
        )

    def test_empty_file(self):
        """Empty file returns valid result with warning."""
        content = ""
        result = parse_csv_metadata(content)

        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.metadata), 0)
        self.assertTrue(any("empty" in w.lower() for w in result.warnings))

    def test_whitespace_only_file(self):
        """Whitespace-only file returns valid result with warning."""
        content = "   \n\t\n   "
        result = parse_csv_metadata(content)

        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.metadata), 0)

    def test_path_normalization(self):
        """Paths are normalized consistently."""
        content = """source_path,title
/docs/file.pdf,Title 1
docs/file2.pdf,Title 2
./docs/file3.pdf,Title 3
docs\\file4.pdf,Title 4
"""
        result = parse_csv_metadata(content)

        self.assertTrue(result.is_valid)
        self.assertIn("/docs/file.pdf", result.metadata)
        self.assertIn("/docs/file2.pdf", result.metadata)
        self.assertIn("/docs/file3.pdf", result.metadata)
        self.assertIn("/docs/file4.pdf", result.metadata)

    def test_path_traversal_rejected(self):
        """Path traversal attempts are rejected."""
        content = """source_path,title
../etc/passwd,Bad Title
docs/../secret.pdf,Also Bad
"""
        result = parse_csv_metadata(content)

        self.assertTrue(result.is_valid)  # File is valid, rows are skipped
        self.assertEqual(len(result.metadata), 0)
        self.assertEqual(len(result.errors), 2)
        self.assertTrue(all("Path traversal" in e for e in result.errors))

    def test_duplicate_paths_warning(self):
        """Warns on duplicate paths, later entry wins."""
        content = """source_path,title,description
file.pdf,First Title,First Description
file.pdf,Second Title,Second Description
"""
        result = parse_csv_metadata(content)

        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.metadata), 1)
        self.assertTrue(any("Duplicate path" in w for w in result.warnings))

        # Second entry wins
        meta = result.metadata["/file.pdf"]
        self.assertEqual(meta.title, "Second Title")
        self.assertEqual(meta.description, "Second Description")

    def test_case_insensitive_columns(self):
        """Column names are case-insensitive."""
        content = """SOURCE_PATH,TITLE,DESCRIPTION
file.pdf,My Title,My Description
"""
        result = parse_csv_metadata(content)

        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.metadata), 1)

        meta = result.metadata["/file.pdf"]
        self.assertEqual(meta.title, "My Title")
        self.assertEqual(meta.description, "My Description")

    def test_extra_columns_ignored(self):
        """Extra columns are silently ignored."""
        content = """source_path,title,description,author,date
file.pdf,Title,Description,John,2024-01-01
"""
        result = parse_csv_metadata(content)

        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.metadata), 1)
        self.assertEqual(len(result.warnings), 0)

    def test_empty_rows_skipped(self):
        """Empty rows are skipped."""
        content = """source_path,title
file1.pdf,Title 1

file2.pdf,Title 2

"""
        result = parse_csv_metadata(content)

        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.metadata), 2)

    def test_whitespace_trimmed(self):
        """Whitespace is trimmed from values."""
        content = """source_path,title,description
  file.pdf  ,  Title  ,  Description
"""
        result = parse_csv_metadata(content)

        self.assertTrue(result.is_valid)
        meta = result.metadata["/file.pdf"]
        self.assertEqual(meta.title, "Title")
        self.assertEqual(meta.description, "Description")

    def test_utf8_content(self):
        """UTF-8 content is handled correctly."""
        content = """source_path,title,description
file.pdf,Título en Español,描述中文
"""
        result = parse_csv_metadata(content)

        self.assertTrue(result.is_valid)
        meta = result.metadata["/file.pdf"]
        self.assertEqual(meta.title, "Título en Español")
        self.assertEqual(meta.description, "描述中文")

    def test_quoted_values(self):
        """Quoted values with commas are handled."""
        content = """source_path,title,description
file.pdf,"Title, with comma","Description with ""quotes"" and, commas"
"""
        result = parse_csv_metadata(content)

        self.assertTrue(result.is_valid)
        meta = result.metadata["/file.pdf"]
        self.assertEqual(meta.title, "Title, with comma")
        self.assertEqual(meta.description, 'Description with "quotes" and, commas')

    def test_nested_folder_paths(self):
        """Handles deeply nested folder paths."""
        content = """source_path,title
a/b/c/d/e/file.pdf,Deep File
"""
        result = parse_csv_metadata(content)

        self.assertTrue(result.is_valid)
        self.assertIn("/a/b/c/d/e/file.pdf", result.metadata)


class TestParseMetadataFile(TestCase):
    """Tests for parse_metadata_file function with actual zip files."""

    def test_parse_from_zip(self):
        """Parses metadata file from zip archive."""
        csv_content = b"""source_path,title,description
docs/file.pdf,My Document,A test document
"""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("meta.csv", csv_content)
            zf.writestr("docs/file.pdf", b"pdf content")
        buffer.seek(0)

        with zipfile.ZipFile(buffer, "r") as zf:
            result = parse_metadata_file(zf, "meta.csv")

        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.metadata), 1)
        self.assertIn("/docs/file.pdf", result.metadata)

    def test_parse_nonexistent_file(self):
        """Returns error for nonexistent file."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("doc.pdf", b"content")
        buffer.seek(0)

        with zipfile.ZipFile(buffer, "r") as zf:
            result = parse_metadata_file(zf, "meta.csv")

        self.assertFalse(result.is_valid)
        self.assertTrue(any("Could not read" in e for e in result.errors))


class TestMetadataFileNames(TestCase):
    """Tests for METADATA_FILE_NAMES constant."""

    def test_file_names_defined(self):
        """All expected file names are defined."""
        self.assertIn("meta.csv", METADATA_FILE_NAMES)
        self.assertIn("META.csv", METADATA_FILE_NAMES)
        self.assertIn("metadata.csv", METADATA_FILE_NAMES)
        self.assertIn("METADATA.csv", METADATA_FILE_NAMES)

    def test_priority_order(self):
        """meta.csv variants come before metadata.csv variants."""
        meta_idx = METADATA_FILE_NAMES.index("meta.csv")
        metadata_idx = METADATA_FILE_NAMES.index("metadata.csv")
        self.assertLess(meta_idx, metadata_idx)


class TestExternalIdColumn(TestCase):
    """Tests for the optional external_id column (durable source identity,
    stored on DocumentPath.external_id by the ZIP import task)."""

    def test_parse_external_id(self):
        content = """source_path,title,external_id
HQ/H022844.txt,Plastic trays; classification,cross:H022844
"""
        result = parse_csv_metadata(content)

        self.assertTrue(result.is_valid)
        meta = result.metadata["/HQ/H022844.txt"]
        self.assertEqual(meta.external_id, "cross:H022844")
        self.assertEqual(meta.title, "Plastic trays; classification")

    def test_external_id_only_row_is_kept(self):
        """A row carrying ONLY an external_id is still metadata."""
        content = """source_path,external_id
doc.txt,cross:H000001
"""
        result = parse_csv_metadata(content)

        self.assertTrue(result.is_valid)
        meta = result.metadata["/doc.txt"]
        self.assertEqual(meta.external_id, "cross:H000001")
        self.assertIsNone(meta.title)
        self.assertIsNone(meta.description)

    def test_empty_external_id_is_none(self):
        content = """source_path,title,external_id
doc.txt,A title,
"""
        result = parse_csv_metadata(content)

        self.assertIsNone(result.metadata["/doc.txt"].external_id)

    def test_overlong_external_id_rejected_with_warning(self):
        """Values beyond DocumentPath.external_id's max_length are ignored
        per-row (never silently truncated)."""
        overlong = "cross:" + "X" * 513
        content = f"""source_path,title,external_id
doc.txt,A title,{overlong}
"""
        result = parse_csv_metadata(content)

        self.assertTrue(result.is_valid)
        meta = result.metadata["/doc.txt"]  # title still applied
        self.assertIsNone(meta.external_id)
        self.assertTrue(any("external_id exceeds" in w for w in result.warnings))

    def test_missing_column_backward_compatible(self):
        content = """source_path,title
doc.txt,A title
"""
        result = parse_csv_metadata(content)

        self.assertTrue(result.is_valid)
        self.assertIsNone(result.metadata["/doc.txt"].external_id)
