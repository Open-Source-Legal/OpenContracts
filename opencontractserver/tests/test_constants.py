"""
Tests for the constants module.

Validates that all constants have the expected types, values, and that
Django-settings-configurable constants respect overrides.
"""

from django.test import TestCase, override_settings

from opencontractserver.constants.auth import (
    ADMIN_CLAIMS_CACHE_TTL,
    TOKEN_LOG_PREFIX_LENGTH,
)
from opencontractserver.constants.context_guardrails import (
    CHARS_PER_TOKEN_ESTIMATE,
    COMPACTION_SUMMARY_MAX_TOKENS,
    COMPACTION_SUMMARY_PREFIX,
    COMPACTION_SUMMARY_TARGET_TOKENS,
    COMPACTION_THRESHOLD_RATIO,
    DEFAULT_CONTEXT_WINDOW,
    MAX_RECENT_MESSAGES,
    MAX_TOOL_OUTPUT_CHARS,
    MIN_RECENT_MESSAGES,
    MODEL_CONTEXT_WINDOWS,
    TOOL_OUTPUT_TRUNCATION_NOTICE,
)
from opencontractserver.constants.corpus_actions import (
    DEFAULT_DOCUMENT_ACTION_TOOLS,
    DEFAULT_THREAD_ACTION_TOOLS,
    DEFAULT_TOOLS_BY_TRIGGER,
    MAX_DESCRIPTION_PREVIEW_LENGTH,
    MAX_MESSAGE_PREVIEW_LENGTH,
    TRIGGER_DESCRIPTIONS,
)
from opencontractserver.constants.document_processing import (
    DEFAULT_CHUNK_RETRY_LIMIT,
    DEFAULT_DOCUMENT_PATH_PREFIX,
    DEFAULT_MAX_CONCURRENT_CHUNKS,
    DEFAULT_MAX_PAGES_PER_CHUNK,
    DEFAULT_MIN_PAGES_FOR_CHUNKING,
    EMBEDDING_BATCH_SIZE,
    MAX_CHUNK_RETRY_BACKOFF_SECONDS,
    MAX_FILENAME_LENGTH,
    MAX_PROCESSING_ERROR_DISPLAY_LENGTH,
    MAX_PROCESSING_ERROR_LENGTH,
    MAX_PROCESSING_TRACEBACK_LENGTH,
    MAX_REEMBED_TASKS_PER_RUN,
    MAX_UPLOAD_ERROR_MESSAGE_LENGTH,
    PERSONAL_CORPUS_DESCRIPTION,
    PERSONAL_CORPUS_TITLE,
)
from opencontractserver.constants.moderation import (
    MODERATION_HOURLY_RATE_THRESHOLD,
    UNTRUSTED_CONTENT_SIZE_WARNING_THRESHOLD,
)


class TestAuthConstants(TestCase):
    """Tests for authentication constants."""

    def test_token_log_prefix_length_type_and_range(self):
        self.assertIsInstance(TOKEN_LOG_PREFIX_LENGTH, int)
        self.assertGreater(TOKEN_LOG_PREFIX_LENGTH, 0)
        self.assertLessEqual(TOKEN_LOG_PREFIX_LENGTH, 50)

    def test_admin_claims_cache_ttl_type_and_range(self):
        self.assertIsInstance(ADMIN_CLAIMS_CACHE_TTL, int)
        self.assertGreater(ADMIN_CLAIMS_CACHE_TTL, 0)
        self.assertLessEqual(ADMIN_CLAIMS_CACHE_TTL, 3600)


class TestContextGuardrailsConstants(TestCase):
    """Tests for LLM context management constants."""

    def test_model_context_windows_is_dict(self):
        self.assertIsInstance(MODEL_CONTEXT_WINDOWS, dict)

    def test_model_context_windows_has_entries(self):
        self.assertGreater(len(MODEL_CONTEXT_WINDOWS), 0)

    def test_model_context_windows_all_positive_ints(self):
        for model_name, window_size in MODEL_CONTEXT_WINDOWS.items():
            self.assertIsInstance(model_name, str, f"Key {model_name} not str")
            self.assertIsInstance(window_size, int, f"Value for {model_name} not int")
            self.assertGreater(window_size, 0, f"Window for {model_name} not positive")

    def test_well_known_models_present(self):
        self.assertIn("gpt-4o", MODEL_CONTEXT_WINDOWS)
        self.assertIn("claude-3-5-sonnet", MODEL_CONTEXT_WINDOWS)
        self.assertIn("gemini-1.5-pro", MODEL_CONTEXT_WINDOWS)

    def test_default_context_window(self):
        self.assertIsInstance(DEFAULT_CONTEXT_WINDOW, int)
        self.assertGreater(DEFAULT_CONTEXT_WINDOW, 0)

    def test_compaction_threshold_ratio(self):
        self.assertIsInstance(COMPACTION_THRESHOLD_RATIO, float)
        self.assertGreater(COMPACTION_THRESHOLD_RATIO, 0)
        self.assertLessEqual(COMPACTION_THRESHOLD_RATIO, 1.0)

    def test_min_recent_messages(self):
        self.assertIsInstance(MIN_RECENT_MESSAGES, int)
        self.assertGreater(MIN_RECENT_MESSAGES, 0)

    def test_max_recent_messages(self):
        self.assertIsInstance(MAX_RECENT_MESSAGES, int)
        self.assertGreater(MAX_RECENT_MESSAGES, MIN_RECENT_MESSAGES)

    def test_max_tool_output_chars(self):
        self.assertIsInstance(MAX_TOOL_OUTPUT_CHARS, int)
        self.assertGreater(MAX_TOOL_OUTPUT_CHARS, 0)

    def test_tool_output_truncation_notice_is_template(self):
        self.assertIsInstance(TOOL_OUTPUT_TRUNCATION_NOTICE, str)
        self.assertIn("{limit}", TOOL_OUTPUT_TRUNCATION_NOTICE)

    def test_compaction_summary_target_tokens(self):
        self.assertIsInstance(COMPACTION_SUMMARY_TARGET_TOKENS, int)
        self.assertGreater(COMPACTION_SUMMARY_TARGET_TOKENS, 0)

    def test_compaction_summary_max_tokens(self):
        self.assertIsInstance(COMPACTION_SUMMARY_MAX_TOKENS, int)
        self.assertGreaterEqual(
            COMPACTION_SUMMARY_MAX_TOKENS, COMPACTION_SUMMARY_TARGET_TOKENS
        )

    def test_compaction_summary_prefix(self):
        self.assertIsInstance(COMPACTION_SUMMARY_PREFIX, str)
        self.assertTrue(len(COMPACTION_SUMMARY_PREFIX) > 0)

    def test_chars_per_token_estimate(self):
        self.assertIsInstance(CHARS_PER_TOKEN_ESTIMATE, float)
        self.assertGreater(CHARS_PER_TOKEN_ESTIMATE, 0)


class TestCorpusActionConstants(TestCase):
    """Tests for corpus action configuration constants."""

    def test_default_document_action_tools_is_list(self):
        self.assertIsInstance(DEFAULT_DOCUMENT_ACTION_TOOLS, list)
        self.assertGreater(len(DEFAULT_DOCUMENT_ACTION_TOOLS), 0)

    def test_default_document_action_tools_all_strings(self):
        for tool in DEFAULT_DOCUMENT_ACTION_TOOLS:
            self.assertIsInstance(tool, str)

    def test_default_thread_action_tools_is_list(self):
        self.assertIsInstance(DEFAULT_THREAD_ACTION_TOOLS, list)
        self.assertGreater(len(DEFAULT_THREAD_ACTION_TOOLS), 0)

    def test_default_thread_action_tools_all_strings(self):
        for tool in DEFAULT_THREAD_ACTION_TOOLS:
            self.assertIsInstance(tool, str)

    def test_default_tools_by_trigger_keys(self):
        expected_keys = {
            "add_document",
            "edit_document",
            "new_thread",
            "new_message",
            "manual_batch",
        }
        self.assertEqual(set(DEFAULT_TOOLS_BY_TRIGGER.keys()), expected_keys)

    def test_document_triggers_use_document_tools(self):
        self.assertEqual(
            DEFAULT_TOOLS_BY_TRIGGER["add_document"],
            DEFAULT_DOCUMENT_ACTION_TOOLS,
        )
        self.assertEqual(
            DEFAULT_TOOLS_BY_TRIGGER["edit_document"],
            DEFAULT_DOCUMENT_ACTION_TOOLS,
        )
        self.assertEqual(
            DEFAULT_TOOLS_BY_TRIGGER["manual_batch"],
            DEFAULT_DOCUMENT_ACTION_TOOLS,
        )

    def test_thread_triggers_use_thread_tools(self):
        self.assertEqual(
            DEFAULT_TOOLS_BY_TRIGGER["new_thread"],
            DEFAULT_THREAD_ACTION_TOOLS,
        )
        self.assertEqual(
            DEFAULT_TOOLS_BY_TRIGGER["new_message"],
            DEFAULT_THREAD_ACTION_TOOLS,
        )

    def test_trigger_descriptions_keys_match_tools(self):
        self.assertEqual(
            set(TRIGGER_DESCRIPTIONS.keys()),
            set(DEFAULT_TOOLS_BY_TRIGGER.keys()),
        )

    def test_trigger_descriptions_all_strings(self):
        for key, value in TRIGGER_DESCRIPTIONS.items():
            self.assertIsInstance(key, str)
            self.assertIsInstance(value, str)
            self.assertTrue(len(value) > 0)

    def test_max_description_preview_length(self):
        self.assertIsInstance(MAX_DESCRIPTION_PREVIEW_LENGTH, int)
        self.assertGreater(MAX_DESCRIPTION_PREVIEW_LENGTH, 0)

    def test_max_message_preview_length(self):
        self.assertIsInstance(MAX_MESSAGE_PREVIEW_LENGTH, int)
        self.assertGreater(MAX_MESSAGE_PREVIEW_LENGTH, 0)


class TestDocumentProcessingConstants(TestCase):
    """Tests for document processing pipeline constants."""

    def test_default_document_path_prefix(self):
        self.assertIsInstance(DEFAULT_DOCUMENT_PATH_PREFIX, str)
        self.assertTrue(DEFAULT_DOCUMENT_PATH_PREFIX.startswith("/"))

    def test_embedding_batch_size(self):
        self.assertIsInstance(EMBEDDING_BATCH_SIZE, int)
        self.assertGreater(EMBEDDING_BATCH_SIZE, 0)

    def test_max_reembed_tasks_per_run(self):
        self.assertIsInstance(MAX_REEMBED_TASKS_PER_RUN, int)
        self.assertGreater(MAX_REEMBED_TASKS_PER_RUN, 0)

    def test_max_filename_length(self):
        self.assertIsInstance(MAX_FILENAME_LENGTH, int)
        self.assertGreater(MAX_FILENAME_LENGTH, 0)

    def test_personal_corpus_defaults(self):
        self.assertIsInstance(PERSONAL_CORPUS_TITLE, str)
        self.assertTrue(len(PERSONAL_CORPUS_TITLE) > 0)
        self.assertIsInstance(PERSONAL_CORPUS_DESCRIPTION, str)
        self.assertTrue(len(PERSONAL_CORPUS_DESCRIPTION) > 0)

    def test_error_length_limits_ordering(self):
        # Display length should be shorter than storage length
        self.assertLess(
            MAX_PROCESSING_ERROR_DISPLAY_LENGTH, MAX_PROCESSING_ERROR_LENGTH
        )
        self.assertLess(MAX_PROCESSING_ERROR_LENGTH, MAX_PROCESSING_TRACEBACK_LENGTH)

    def test_upload_error_message_length(self):
        self.assertIsInstance(MAX_UPLOAD_ERROR_MESSAGE_LENGTH, int)
        self.assertGreater(MAX_UPLOAD_ERROR_MESSAGE_LENGTH, 0)

    def test_chunked_processing_defaults(self):
        self.assertIsInstance(DEFAULT_MAX_PAGES_PER_CHUNK, int)
        self.assertGreater(DEFAULT_MAX_PAGES_PER_CHUNK, 0)
        self.assertIsInstance(DEFAULT_MIN_PAGES_FOR_CHUNKING, int)
        self.assertGreater(DEFAULT_MIN_PAGES_FOR_CHUNKING, DEFAULT_MAX_PAGES_PER_CHUNK)
        self.assertIsInstance(DEFAULT_MAX_CONCURRENT_CHUNKS, int)
        self.assertGreater(DEFAULT_MAX_CONCURRENT_CHUNKS, 0)
        self.assertIsInstance(DEFAULT_CHUNK_RETRY_LIMIT, int)
        self.assertGreaterEqual(DEFAULT_CHUNK_RETRY_LIMIT, 0)
        self.assertIsInstance(MAX_CHUNK_RETRY_BACKOFF_SECONDS, int)
        self.assertGreater(MAX_CHUNK_RETRY_BACKOFF_SECONDS, 0)


class TestModerationConstants(TestCase):
    """Tests for moderation system constants."""

    def test_hourly_rate_threshold(self):
        self.assertIsInstance(MODERATION_HOURLY_RATE_THRESHOLD, int)
        self.assertGreater(MODERATION_HOURLY_RATE_THRESHOLD, 0)

    def test_untrusted_content_size_warning(self):
        self.assertIsInstance(UNTRUSTED_CONTENT_SIZE_WARNING_THRESHOLD, int)
        self.assertGreater(UNTRUSTED_CONTENT_SIZE_WARNING_THRESHOLD, 0)


class TestZipImportConstants(TestCase):
    """Tests for ZIP import security constants."""

    def test_all_positive(self):
        from opencontractserver.constants.zip_import import (
            get_zip_document_batch_size,
            get_zip_max_compression_ratio,
            get_zip_max_file_count,
            get_zip_max_folder_count,
            get_zip_max_folder_depth,
            get_zip_max_path_component_length,
            get_zip_max_path_length,
            get_zip_max_single_file_size_bytes,
            get_zip_max_total_size_bytes,
        )

        self.assertGreater(get_zip_max_file_count(), 0)
        self.assertGreater(get_zip_max_total_size_bytes(), 0)
        self.assertGreater(get_zip_max_single_file_size_bytes(), 0)
        self.assertGreater(get_zip_max_compression_ratio(), 0)
        self.assertGreater(get_zip_max_folder_depth(), 0)
        self.assertGreater(get_zip_max_folder_count(), 0)
        self.assertGreater(get_zip_max_path_component_length(), 0)
        self.assertGreater(get_zip_max_path_length(), 0)
        self.assertGreater(get_zip_document_batch_size(), 0)

    def test_single_file_less_than_total(self):
        from opencontractserver.constants.zip_import import (
            get_zip_max_single_file_size_bytes,
            get_zip_max_total_size_bytes,
        )

        self.assertLess(
            get_zip_max_single_file_size_bytes(), get_zip_max_total_size_bytes()
        )

    def test_accessors_fall_back_to_defaults_when_unset(self):
        """With no setting override, each accessor returns its DEFAULT_*."""
        from opencontractserver.constants import zip_import as zi

        self.assertEqual(zi.get_zip_max_file_count(), zi.DEFAULT_ZIP_MAX_FILE_COUNT)
        self.assertEqual(
            zi.get_zip_max_total_size_bytes(), zi.DEFAULT_ZIP_MAX_TOTAL_SIZE_BYTES
        )
        self.assertEqual(
            zi.get_bulk_upload_owner_cache_ttl_seconds(),
            zi.DEFAULT_BULK_UPLOAD_OWNER_CACHE_TTL_SECONDS,
        )

    @override_settings(
        ZIP_MAX_FILE_COUNT=4242,
        ZIP_MAX_TOTAL_SIZE_BYTES=123,
        ZIP_MAX_SIDECAR_SIZE_BYTES=456,
        ZIP_DOCUMENT_BATCH_SIZE=7,
        BULK_UPLOAD_OWNER_CACHE_TTL_SECONDS=99,
    )
    def test_accessors_reflect_settings_overrides(self):
        """Regression for the import-time freeze bug (see zip_import.py).

        The limits must be read lazily at call time, so a settings override
        (env/ConfigMap in production, ``@override_settings`` in tests) is
        honoured — never frozen to the default at import.
        """
        from opencontractserver.constants.zip_import import (
            get_bulk_upload_owner_cache_ttl_seconds,
            get_zip_document_batch_size,
            get_zip_max_file_count,
            get_zip_max_sidecar_size_bytes,
            get_zip_max_total_size_bytes,
        )

        self.assertEqual(get_zip_max_file_count(), 4242)
        self.assertEqual(get_zip_max_total_size_bytes(), 123)
        self.assertEqual(get_zip_max_sidecar_size_bytes(), 456)
        self.assertEqual(get_zip_document_batch_size(), 7)
        self.assertEqual(get_bulk_upload_owner_cache_ttl_seconds(), 99)


class TestConstantsBarrelImport(TestCase):
    """Tests that the __init__.py barrel import exposes all constants."""

    def test_auth_constants_accessible(self):
        from opencontractserver.constants import (
            ADMIN_CLAIMS_CACHE_TTL,
            TOKEN_LOG_PREFIX_LENGTH,
        )

        self.assertIsNotNone(TOKEN_LOG_PREFIX_LENGTH)
        self.assertIsNotNone(ADMIN_CLAIMS_CACHE_TTL)

    def test_moderation_constants_accessible(self):
        from opencontractserver.constants import (
            MODERATION_HOURLY_RATE_THRESHOLD,
            UNTRUSTED_CONTENT_SIZE_WARNING_THRESHOLD,
        )

        self.assertIsNotNone(MODERATION_HOURLY_RATE_THRESHOLD)
        self.assertIsNotNone(UNTRUSTED_CONTENT_SIZE_WARNING_THRESHOLD)

    def test_context_guardrails_accessible(self):
        from opencontractserver.constants import (
            DEFAULT_CONTEXT_WINDOW,
            MODEL_CONTEXT_WINDOWS,
        )

        self.assertIsNotNone(MODEL_CONTEXT_WINDOWS)
        self.assertIsNotNone(DEFAULT_CONTEXT_WINDOW)
