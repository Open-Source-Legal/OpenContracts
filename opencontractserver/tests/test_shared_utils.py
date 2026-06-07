"""
Tests for the shared module utilities: defaults, db_utils, slug_utils, utils,
and mixin dimension-to-field mappings.

These are pure unit tests that exercise the shared utility functions directly.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from opencontractserver.constants.document_processing import MAX_FILENAME_LENGTH
from opencontractserver.shared.db_utils import table_has_column
from opencontractserver.shared.defaults import (
    create_model_icon_path,
    empty_text_label_position,
    jsonfield_default_value,
)
from opencontractserver.shared.mixins import (
    HasEmbeddingMixin,
    VectorSearchViaEmbeddingMixin,
)
from opencontractserver.shared.slug_utils import (
    generate_unique_slug,
    get_reserved_user_slugs,
    sanitize_slug,
    validate_user_slug_or_raise,
)
from opencontractserver.shared.utils import (
    calc_oc_file_path,
    sanitize_corpus_filename,
)


class TestDefaultFunctions(TestCase):
    """Tests for shared/defaults.py default value factory functions."""

    def test_empty_text_label_position_structure(self):
        result = empty_text_label_position()
        self.assertIsInstance(result, dict)
        self.assertIn("rects", result)
        self.assertIn("pageNumber", result)
        self.assertIn("boundingRect", result)
        self.assertEqual(result["rects"], [])
        self.assertEqual(result["pageNumber"], 1)
        br = result["boundingRect"]
        self.assertEqual(br["x1"], 0.0)
        self.assertEqual(br["x2"], 0.0)
        self.assertEqual(br["y1"], 0.0)
        self.assertEqual(br["y2"], 0.0)
        self.assertEqual(br["width"], 0.0)
        self.assertEqual(br["height"], 0.0)

    def test_empty_text_label_position_returns_new_instance(self):
        a = empty_text_label_position()
        b = empty_text_label_position()
        self.assertIsNot(a, b)

    def test_jsonfield_default_value(self):
        result = jsonfield_default_value()
        self.assertEqual(result, {})
        self.assertIsInstance(result, dict)

    def test_jsonfield_default_value_returns_new_instance(self):
        a = jsonfield_default_value()
        b = jsonfield_default_value()
        self.assertIsNot(a, b)

    def test_create_model_icon_path(self):
        mock_instance = MagicMock()
        mock_instance.creator.id = 42
        mock_instance.__class__.__name__ = "Corpus"
        result = create_model_icon_path(mock_instance, "icon.png")
        self.assertTrue(result.startswith("user_42/Corpus/icons/"))
        # Should contain a UUID
        parts = result.split("/")
        self.assertEqual(len(parts), 4)
        self.assertEqual(parts[0], "user_42")
        self.assertEqual(parts[1], "Corpus")
        self.assertEqual(parts[2], "icons")
        # UUID part should be non-empty
        self.assertTrue(len(parts[3]) > 0)

    def test_create_model_icon_path_unique(self):
        mock_instance = MagicMock()
        mock_instance.creator.id = 1
        mock_instance.__class__.__name__ = "Document"
        path1 = create_model_icon_path(mock_instance, "a.png")
        path2 = create_model_icon_path(mock_instance, "a.png")
        self.assertNotEqual(path1, path2)


class TestDbUtils(TestCase):
    """Tests for shared/db_utils.py database introspection utilities."""

    def setUp(self):
        # Clear the LRU cache between tests
        table_has_column.cache_clear()

    def test_existing_table_and_column(self):
        # users_user table exists (custom user model: AUTH_USER_MODEL = "users.User")
        result = table_has_column("users_user", "username")
        self.assertTrue(result)

    def test_existing_table_missing_column(self):
        result = table_has_column("users_user", "nonexistent_column_xyz")
        self.assertFalse(result)

    def test_nonexistent_table(self):
        result = table_has_column("completely_fake_table_xyz", "some_column")
        self.assertFalse(result)

    def test_result_is_cached(self):
        # First call
        result1 = table_has_column("users_user", "username")
        # Second call should hit cache
        result2 = table_has_column("users_user", "username")
        self.assertEqual(result1, result2)
        # Check cache info
        info = table_has_column.cache_info()
        self.assertGreaterEqual(info.hits, 1)


class TestSanitizeSlug(TestCase):
    """Tests for shared/slug_utils.py sanitize_slug function."""

    def test_basic_slug(self):
        result = sanitize_slug("Hello World", max_length=50)
        self.assertEqual(result, "Hello-World")

    def test_underscores_replaced(self):
        result = sanitize_slug("hello_world", max_length=50)
        self.assertEqual(result, "hello-world")

    def test_special_chars_removed(self):
        result = sanitize_slug("hello@world!#$%", max_length=50)
        self.assertEqual(result, "helloworld")

    def test_multiple_hyphens_collapsed(self):
        result = sanitize_slug("hello---world", max_length=50)
        self.assertEqual(result, "hello-world")

    def test_leading_trailing_hyphens_trimmed(self):
        result = sanitize_slug("--hello--", max_length=50)
        self.assertEqual(result, "hello")

    def test_max_length_enforced(self):
        result = sanitize_slug("a" * 200, max_length=10)
        self.assertEqual(len(result), 10)

    def test_empty_string(self):
        result = sanitize_slug("", max_length=50)
        self.assertEqual(result, "")

    def test_none_value(self):
        result = sanitize_slug(None, max_length=50)
        self.assertEqual(result, "")

    def test_case_preserved(self):
        result = sanitize_slug("MyDocument", max_length=50)
        self.assertEqual(result, "MyDocument")

    def test_spaces_and_underscores_mixed(self):
        result = sanitize_slug("my doc_title here", max_length=50)
        self.assertEqual(result, "my-doc-title-here")

    def test_only_special_chars(self):
        result = sanitize_slug("@#$%^&*()", max_length=50)
        self.assertEqual(result, "")

    def test_alphanumeric_with_hyphens(self):
        result = sanitize_slug("already-valid-slug-123", max_length=50)
        self.assertEqual(result, "already-valid-slug-123")


class TestGenerateUniqueSlug(TestCase):
    """Tests for shared/slug_utils.py generate_unique_slug function."""

    def _make_qs(self, existing_slugs):
        """Create a mock queryset that responds to filter().exists()."""
        qs = MagicMock()

        def filter_side_effect(**kwargs):
            slug_value = kwargs.get("slug")
            result = MagicMock()
            result.exists.return_value = slug_value in existing_slugs
            return result

        qs.filter.side_effect = filter_side_effect
        return qs

    def test_unique_slug_no_conflict(self):
        qs = self._make_qs(set())
        result = generate_unique_slug(
            base_value="My Title",
            scope_qs=qs,
            max_length=50,
            fallback_prefix="item",
        )
        self.assertEqual(result, "My-Title")

    def test_unique_slug_with_conflict(self):
        qs = self._make_qs({"My-Title"})
        result = generate_unique_slug(
            base_value="My Title",
            scope_qs=qs,
            max_length=50,
            fallback_prefix="item",
        )
        self.assertEqual(result, "My-Title-2")

    def test_unique_slug_multiple_conflicts(self):
        qs = self._make_qs({"My-Title", "My-Title-2", "My-Title-3"})
        result = generate_unique_slug(
            base_value="My Title",
            scope_qs=qs,
            max_length=50,
            fallback_prefix="item",
        )
        self.assertEqual(result, "My-Title-4")

    def test_empty_base_uses_fallback(self):
        qs = self._make_qs(set())
        result = generate_unique_slug(
            base_value="",
            scope_qs=qs,
            max_length=50,
            fallback_prefix="item",
        )
        self.assertEqual(result, "item")

    def test_special_chars_base_uses_fallback(self):
        qs = self._make_qs(set())
        result = generate_unique_slug(
            base_value="@#$%",
            scope_qs=qs,
            max_length=50,
            fallback_prefix="fallback",
        )
        self.assertEqual(result, "fallback")

    def test_max_length_with_suffix(self):
        qs = self._make_qs({"abcde"})
        result = generate_unique_slug(
            base_value="abcde",
            scope_qs=qs,
            max_length=7,
            fallback_prefix="x",
        )
        # "abcde" (5 chars) + "-2" fits within max_length=7
        self.assertEqual(result, "abcde-2")
        self.assertLessEqual(len(result), 7)


class TestValidateUserSlugOrRaise(TestCase):
    """Tests for shared/slug_utils.py validate_user_slug_or_raise function."""

    def test_valid_slug(self):
        # Should not raise
        validate_user_slug_or_raise("my-valid-slug")

    def test_valid_slug_alphanumeric(self):
        validate_user_slug_or_raise("User123")

    def test_empty_slug_raises(self):
        with self.assertRaises(ValueError) as ctx:
            validate_user_slug_or_raise("")
        self.assertIn("empty", str(ctx.exception).lower())

    def test_invalid_chars_raises(self):
        with self.assertRaises(ValueError) as ctx:
            validate_user_slug_or_raise("slug with spaces")
        self.assertIn("invalid characters", str(ctx.exception).lower())

    def test_special_chars_raises(self):
        with self.assertRaises(ValueError):
            validate_user_slug_or_raise("slug@here")

    def test_reserved_slug_raises(self):
        with self.assertRaises(ValueError) as ctx:
            validate_user_slug_or_raise("admin")
        self.assertIn("reserved", str(ctx.exception).lower())

    def test_other_reserved_slugs(self):
        reserved = ["login", "logout", "api", "graphql", "settings"]
        for slug in reserved:
            with self.assertRaises(ValueError):
                validate_user_slug_or_raise(slug)


class TestGetReservedUserSlugs(TestCase):
    """Tests for shared/slug_utils.py get_reserved_user_slugs function."""

    def test_returns_set(self):
        result = get_reserved_user_slugs()
        self.assertIsInstance(result, set)

    def test_default_includes_common_slugs(self):
        result = get_reserved_user_slugs()
        self.assertIn("admin", result)
        self.assertIn("api", result)
        self.assertIn("graphql", result)
        self.assertIn("login", result)
        self.assertIn("logout", result)

    @override_settings(RESERVED_USER_SLUGS=["custom1", "custom2"])
    def test_custom_settings_override(self):
        result = get_reserved_user_slugs()
        self.assertEqual(result, {"custom1", "custom2"})


class TestCalcOcFilePath(TestCase):
    """Tests for shared/utils.py calc_oc_file_path function."""

    def test_basic_path(self):
        mock_instance = MagicMock()
        result = calc_oc_file_path(mock_instance, "test.pdf", "documents")
        self.assertEqual(result, "uploadfiles/documents/test.pdf")

    def test_different_subfolder(self):
        mock_instance = MagicMock()
        result = calc_oc_file_path(mock_instance, "image.png", "thumbnails")
        self.assertEqual(result, "uploadfiles/thumbnails/image.png")

    def test_filename_with_uuid(self):
        mock_instance = MagicMock()
        result = calc_oc_file_path(mock_instance, "abc-123-def.pdf", "exports")
        self.assertEqual(result, "uploadfiles/exports/abc-123-def.pdf")


class TestSanitizeCorpusFilename(TestCase):
    """Direct unit tests for shared/utils.py sanitize_corpus_filename.

    This is the canonical sanitiser for the filename segment of a
    ``DocumentPath.path`` (shared by ``Corpus.add_document``, the text-import
    tool and ``FolderDocumentService.rename_document``). It is exercised
    indirectly through the rename integration paths, but its invariants —
    fallback on empty, special-chars-to-underscore, no directory traversal,
    truncation, and leading-dot preservation — deserve an explicit test.
    """

    def test_allowed_chars_pass_through(self):
        # Alphanumerics plus -, _ and . survive unchanged.
        self.assertEqual(
            sanitize_corpus_filename("Report-v2_final.pdf"), "Report-v2_final.pdf"
        )

    def test_empty_input_uses_fallback(self):
        self.assertEqual(sanitize_corpus_filename(""), "untitled")

    def test_none_input_uses_fallback(self):
        # ``(name or "")`` coerces None before slicing, so None -> fallback too.
        self.assertEqual(sanitize_corpus_filename(None), "untitled")

    def test_custom_fallback(self):
        self.assertEqual(sanitize_corpus_filename("", fallback="doc"), "doc")

    def test_all_special_chars_become_underscores(self):
        # Disallowed chars are replaced (never dropped), so an all-special name
        # yields underscores, not the fallback.
        self.assertEqual(sanitize_corpus_filename("!!!!"), "____")

    def test_path_separators_collapse_to_underscore(self):
        # Slashes (fwd and back) map to "_" so a sanitised name can never
        # traverse directories.
        self.assertEqual(sanitize_corpus_filename("a/b\\c"), "a_b_c")

    def test_runs_are_not_collapsed(self):
        # Each disallowed char maps to its own underscore (documented: runs are
        # intentionally NOT collapsed to a single separator).
        self.assertEqual(sanitize_corpus_filename("My  File"), "My__File")

    def test_leading_dot_preserved(self):
        # A leading dot is an allowed char, so dotfiles keep their dot.
        self.assertEqual(sanitize_corpus_filename(".gitignore"), ".gitignore")

    def test_truncated_to_max_length(self):
        result = sanitize_corpus_filename("a" * (MAX_FILENAME_LENGTH + 50))
        self.assertEqual(len(result), MAX_FILENAME_LENGTH)
        self.assertEqual(result, "a" * MAX_FILENAME_LENGTH)

    def test_truncation_happens_before_sanitisation(self):
        # The raw input is sliced to MAX_FILENAME_LENGTH first, then each
        # surviving char is mapped — so an over-long all-special string yields
        # exactly MAX_FILENAME_LENGTH underscores, not more.
        result = sanitize_corpus_filename("*" * (MAX_FILENAME_LENGTH + 10))
        self.assertEqual(result, "_" * MAX_FILENAME_LENGTH)


class TestVectorSearchMixinDimensionMapping(TestCase):
    """Tests for VectorSearchViaEmbeddingMixin._dimension_to_field mapping."""

    def setUp(self):
        self.mixin = VectorSearchViaEmbeddingMixin()
        self.mixin.EMBEDDING_RELATED_NAME = "embedding_set"

    def test_dimension_384(self):
        self.assertEqual(
            self.mixin._dimension_to_field(384), "embedding_set__vector_384"
        )

    def test_dimension_768(self):
        self.assertEqual(
            self.mixin._dimension_to_field(768), "embedding_set__vector_768"
        )

    def test_dimension_1024(self):
        self.assertEqual(
            self.mixin._dimension_to_field(1024), "embedding_set__vector_1024"
        )

    def test_dimension_1536(self):
        self.assertEqual(
            self.mixin._dimension_to_field(1536), "embedding_set__vector_1536"
        )

    def test_dimension_2048(self):
        self.assertEqual(
            self.mixin._dimension_to_field(2048), "embedding_set__vector_2048"
        )

    def test_dimension_3072(self):
        self.assertEqual(
            self.mixin._dimension_to_field(3072), "embedding_set__vector_3072"
        )

    def test_dimension_4096(self):
        self.assertEqual(
            self.mixin._dimension_to_field(4096), "embedding_set__vector_4096"
        )

    def test_unsupported_dimension_raises(self):
        with self.assertRaises(ValueError) as ctx:
            self.mixin._dimension_to_field(512)
        self.assertIn("512", str(ctx.exception))

    def test_custom_related_name(self):
        self.mixin.EMBEDDING_RELATED_NAME = "embeddings"
        self.assertEqual(self.mixin._dimension_to_field(384), "embeddings__vector_384")


class TestHasEmbeddingMixinDimensionMapping(TestCase):
    """Tests for HasEmbeddingMixin get_embedding dimension validation."""

    def test_not_implemented_error(self):
        mixin = HasEmbeddingMixin()
        with self.assertRaises(NotImplementedError):
            mixin.get_embedding_reference_kwargs()

    def test_unsupported_dimension_raises(self):
        mixin = HasEmbeddingMixin()
        with self.assertRaises(ValueError) as ctx:
            mixin.get_embedding("some-embedder", 512)
        self.assertIn("512", str(ctx.exception))

    def test_add_embedding_none_vector(self):
        mixin = HasEmbeddingMixin()
        result = mixin.add_embedding("some-embedder", None)
        self.assertIsNone(result)

    @patch(
        "opencontractserver.shared.mixins.HasEmbeddingMixin.get_embedding_reference_kwargs"
    )
    def test_get_embedding_not_found(self, mock_kwargs):
        mock_kwargs.return_value = {"document_id": 999}
        mixin = HasEmbeddingMixin()
        with patch(
            "opencontractserver.annotations.models.Embedding.objects.get"
        ) as mock_get:
            from opencontractserver.annotations.models import Embedding

            mock_get.side_effect = Embedding.DoesNotExist
            result = mixin.get_embedding("test-embedder", 384)
        self.assertIsNone(result)
