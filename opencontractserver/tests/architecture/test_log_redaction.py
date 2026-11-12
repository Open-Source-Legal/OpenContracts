"""Log calls must not format raw kwargs / settings mappings — test enforcement.

The scanner, its scope and its known limits live in
``opencontractserver/shared/log_redaction_audit.py``; this module pins its
behaviour and runs it over the tree. Written as ``SimpleTestCase`` classes so
both ``pytest`` (CI) and ``manage.py test`` collect them. There is no Django
system check for this invariant — see the audit module's docstring.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from unittest import mock

from django.test import SimpleTestCase

from opencontractserver.pipeline.base.settings_schema import (
    PipelineSetting,
    SettingType,
    get_pipeline_setting,
)
from opencontractserver.shared.log_redaction_audit import (
    SAFE_MARKER,
    audit_log_calls,
    format_violation,
    may_contain_hit,
    scan_log_calls,
)

EMBEDDER_MODULE = "opencontractserver.pipeline.embedders.sent_transformer_microservice"

# (snippet, offending name) — each must produce exactly one hit on line 1.
FLAGGED = {
    "f-string": ('logger.debug(f"kwargs: {all_kwargs}")', "all_kwargs"),
    "percent-positional": ('logger.info("kwargs: %s", all_kwargs)', "all_kwargs"),
    "percent-operator": (
        'logger.info("a %s b %s" % (x, merged_kwargs))',
        "merged_kwargs",
    ),
    "percent-dict": ('logger.info("%(k)s" % {"k": all_kwargs})', "all_kwargs"),
    "str.format": (
        'logger.info("s: {}".format(component_settings))',
        "component_settings",
    ),
    "str.format-keyword": (
        'logger.info("s: {s}".format(s=component_settings))',
        "component_settings",
    ),
    "method-call": (
        'logger.info(f"s: {self.get_component_settings()}")',
        "get_component_settings",
    ),
    "attribute": ('logger.warning(f"s: {self._settings}")', "_settings"),
    "message-is-mapping": ("logger.debug(all_kwargs)", "all_kwargs"),
    "message-is-str-mapping": ("logger.debug(str(all_kwargs))", "all_kwargs"),
    "concatenation": ('logger.info("kwargs: " + str(all_kwargs))', "all_kwargs"),
    "repr-concatenation": ('logger.info("s: " + repr(self._settings))', "_settings"),
    "dict-unpack": ('logger.info(f"{ {**all_kwargs} }")', "all_kwargs"),
    "dict-double-star": ('logger.info(f"{dict(**all_kwargs)}")', "all_kwargs"),
    "keyword-msg": ('logger.info(msg=f"{all_kwargs}")', "all_kwargs"),
    "extra-dict": ('logger.info("x", extra={"kwargs": all_kwargs})', "all_kwargs"),
    "uppercase-constant": ('logger.info("%s", DEFAULT_KWARGS)', "DEFAULT_KWARGS"),
    "space-before-paren": ('logger.info ("%s", all_kwargs)', "all_kwargs"),
    "str-wrapped": ('logger.info("s: %s", str(all_kwargs))', "all_kwargs"),
    "json.dumps-wrapped": ('logger.info(f"s: {json.dumps(all_kwargs)}")', "all_kwargs"),
    "asdict-wrapped": ('logger.info(f"{asdict(self.settings)}")', "settings"),
    "vars-wrapped": ('logger.info("%s", vars(self.settings))', "settings"),
    "logger.log": ('logger.log(logging.INFO, "k: %s", all_kwargs)', "all_kwargs"),
    "nested-f-string": ('logger.info(" ".join([f"{all_kwargs}"]))', "all_kwargs"),
}

ALLOWED = {
    "redacted-f-string": 'logger.debug(f"kwargs: {redact_sensitive_kwargs(all_kwargs)}")',
    "redacted-percent": 'logger.info("k: %s", redact_sensitive_kwargs(all_kwargs))',
    "redacted-dataclass": 'logger.info("%s", redact_sensitive_kwargs(self.settings))',
    "redacted-then-dumped": (
        'logger.info("%s", json.dumps(redact_sensitive_kwargs(all_kwargs)))'
    ),
    "scalar-lookup": """logger.info(f"h: {all_kwargs.get('height')}")""",
    "subscript": """logger.info(f"h: {all_kwargs['height']}")""",
    "keys-only": 'logger.info(f"h: {list(all_kwargs.keys())}")',
    "sorted-keys": 'logger.info(f"h: {sorted(all_kwargs)}")',
    "length": 'logger.info("n=%d", len(all_kwargs))',
    "settings-attribute": 'logger.info(f"url: {self.settings.api_url}")',
    "django-settings-attr": 'logger.info(f"x: {settings.DEBUG}")',
    "exception-variable": 'logger.debug(f"Could not load settings: {e}")',
    "not-a-log-call": "print(all_kwargs)",
}


class LogRedactionInvariantTests(SimpleTestCase):
    def test_no_backend_log_call_formats_raw_kwargs_or_settings(self) -> None:
        offenders = [format_violation(*hit) for hit in audit_log_calls()]
        self.assertEqual(
            offenders, [], "Raw mappings in log calls:\n  " + "\n  ".join(offenders)
        )


class LogRedactionScannerTests(SimpleTestCase):
    def test_flags_raw_mapping(self) -> None:
        for key, (snippet, name) in FLAGGED.items():
            with self.subTest(key):
                self.assertEqual(scan_log_calls(snippet), [(1, name)])

    def test_allows_safe_formatting(self) -> None:
        for key, snippet in ALLOWED.items():
            with self.subTest(key):
                self.assertEqual(scan_log_calls(snippet), [])

    def test_prefilter_keeps_every_flagged_snippet(self) -> None:
        """The text pre-filter must never skip a file the AST scan would flag."""
        for key, (snippet, _) in FLAGGED.items():
            with self.subTest(key):
                self.assertTrue(may_contain_hit(snippet))

    def test_redactor_import_alias_is_recognised(self) -> None:
        source = (
            "from opencontractserver.utils.logging import "
            "redact_sensitive_kwargs as redact\n"
            'logger.info("k: %s", redact(all_kwargs))\n'
        )
        self.assertEqual(scan_log_calls(source), [])

    def test_safe_marker_accepts_only_the_marked_call(self) -> None:
        call = 'logger.info("k: %s", public_settings(self.settings))'
        self.assertEqual(scan_log_calls(call), [(1, "public_settings")])
        marked = f"{call}  # {SAFE_MARKER}: returns the non-secret subset"
        self.assertEqual(scan_log_calls(marked), [])
        # The marker covers one call, not the file.
        self.assertEqual(scan_log_calls(f"{marked}\n{call}"), [(2, "public_settings")])


def _secret_field(**setting_kwargs: object) -> object:
    """A SECRET setting declared the plain way — without ``repr=False``."""
    return field(
        default="",
        metadata={
            "pipeline_setting": PipelineSetting(
                setting_type=SettingType.SECRET, **setting_kwargs  # type: ignore[arg-type]
            )
        },
    )


class SecretSettingsReprTests(SimpleTestCase):
    """``SECRET`` settings never appear in a Settings repr, however declared."""

    def test_pipeline_component_hides_secret_from_repr(self) -> None:
        from opencontractserver.pipeline.base.base_component import (
            PipelineComponentBase,
        )

        class Component(PipelineComponentBase):
            @dataclass
            class Settings:
                api_key: str = _secret_field(description="k")  # type: ignore[assignment]
                timeout: int = 30

        instance = Component.Settings(api_key="sk-live-123", timeout=5)
        # Same shape as the generated dataclass repr (qualname + fields),
        # minus the secret.
        self.assertTrue(repr(instance).endswith(".Settings(timeout=5)"), repr(instance))
        self.assertEqual(instance.api_key, "sk-live-123")
        self.assertFalse(dataclasses.fields(instance)[0].repr)

    def test_tool_hides_secret_from_repr(self) -> None:
        from opencontractserver.llms.tools.base_tool import BaseTool

        class Tool(BaseTool):
            tool_key = "repr_probe"

            @dataclass
            class Settings:
                api_key: str = _secret_field(required=True)  # type: ignore[assignment]
                provider: str = "brave"

        self.assertNotIn("sk-live-123", repr(Tool.Settings(api_key="sk-live-123")))

    def test_hand_written_repr_is_left_alone(self) -> None:
        from opencontractserver.pipeline.base.base_component import (
            PipelineComponentBase,
        )

        class Component(PipelineComponentBase):
            @dataclass(repr=False)
            class Settings:
                api_key: str = _secret_field()  # type: ignore[assignment]

                def __repr__(self) -> str:
                    return "custom"

        self.assertEqual(repr(Component.Settings(api_key="x")), "custom")

    def test_every_registered_component_hides_its_secrets(self) -> None:
        from opencontractserver.llms.tools.web_search_tools import WebSearchTool
        from opencontractserver.pipeline.registry import get_all_components_cached

        classes = [WebSearchTool] + [
            definition.component_class
            for definitions in get_all_components_cached().values()
            for definition in definitions
            if definition.component_class is not None
        ]
        checked = 0
        for cls in classes:
            settings_cls = getattr(cls, "Settings", None)
            if not dataclasses.is_dataclass(settings_cls):
                continue
            for field_obj in dataclasses.fields(settings_cls):
                setting = get_pipeline_setting(field_obj)
                if setting is None or setting.setting_type is not SettingType.SECRET:
                    continue
                checked += 1
                with self.subTest(component=cls.__name__, field=field_obj.name):
                    self.assertFalse(field_obj.repr)
        self.assertGreater(checked, 0, "no SECRET settings found — discovery broke")


class ComponentLogOutputTests(SimpleTestCase):
    def test_microservice_embedder_does_not_log_api_key(self) -> None:
        from opencontractserver.pipeline.embedders.sent_transformer_microservice import (  # noqa: E501
            MicroserviceEmbedder,
        )

        secret = "test-secret-value-1234567890"
        service_settings = {
            "embeddings_microservice_url": "http://embedder.invalid",
            "vector_embedder_api_key": secret,
        }
        # Explicit component_settings is the documented no-database construction
        # path; without it the constructor only stays off the DB because
        # get_component_settings() swallows the test runner's access error.
        embedder = MicroserviceEmbedder(component_settings=service_settings)
        with mock.patch(
            f"{EMBEDDER_MODULE}._get_session",
            side_effect=RuntimeError("no network in tests"),
        ), self.assertLogs(EMBEDDER_MODULE, level="DEBUG") as captured:
            embedder._embed_text_impl("hello", **service_settings)

        joined = "\n".join(captured.output)
        self.assertIn("Effective kwargs", joined)
        self.assertNotIn(secret, joined)
        self.assertNotIn(secret, repr(embedder.settings))

    def test_agent_config_repr_hides_api_key(self) -> None:
        """Defence in depth: the config is no longer logged whole, but
        ``get_default_config`` still populates the key, so keep it out of repr."""
        from opencontractserver.llms.agents.core_agents import AgentConfig

        secret = "sk-test-1234567890"
        config = AgentConfig(api_key=secret)
        self.assertEqual(config.api_key, secret)
        self.assertNotIn(secret, repr(config))
