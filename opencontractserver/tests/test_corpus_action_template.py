from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusActionTemplate,
    CorpusActionTrigger,
)
from opencontractserver.corpuses.template_seeds import (
    _CAML_ARTICLE_SYSTEM_INSTRUCTIONS,
)
from opencontractserver.corpuses.template_seeds import (
    create_default_action_templates as _create_default_action_templates,
)

# Shared across test classes that verify default template seeding
DEFAULT_TEMPLATE_NAMES = [
    "Document Description Updater",
    "Corpus Description Updater",
    "Document Summary Generator",
    "Key Terms Annotator",
    "Document Notes Generator",
    "CAML Article Writer",
]

User = get_user_model()


class CorpusActionTemplateModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="templateuser", password="testpass"
        )
        self.agent_config = AgentConfiguration.objects.create(
            name="Template Agent",
            description="Agent for template tests",
            system_instructions="You are a test agent.",
            available_tools=["load_document_text", "update_document_description"],
            is_active=True,
            creator=self.user,
        )

    def test_create_template_with_agent_config(self):
        template = CorpusActionTemplate.objects.create(
            name="Test Template",
            description="A test template",
            agent_config=self.agent_config,
            task_instructions="Do something useful.",
            pre_authorized_tools=["load_document_text"],
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )
        self.assertIsNotNone(template.pk)
        self.assertEqual(template.trigger, CorpusActionTrigger.ADD_DOCUMENT)
        self.assertTrue(template.is_active)
        self.assertFalse(template.disabled_on_clone)

    def test_create_lightweight_template_no_agent_config(self):
        template = CorpusActionTemplate.objects.create(
            name="Lightweight Template",
            task_instructions="Just do it.",
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )
        self.assertIsNotNone(template.pk)
        self.assertIsNone(template.agent_config)

    def test_empty_task_instructions_raises(self):
        """clean() rejects empty task_instructions; DB constraint is the final guard."""
        t = CorpusActionTemplate(
            name="Bad Template",
            task_instructions="",
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )
        with self.assertRaises(ValidationError):
            t.full_clean()

    def test_str_representation(self):
        template = CorpusActionTemplate.objects.create(
            name="Desc Updater",
            task_instructions="Update description.",
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )
        self.assertIn("Desc Updater", str(template))
        self.assertIn("Add Document", str(template))

    def test_clone_to_corpus(self):
        template = CorpusActionTemplate.objects.create(
            name="Clone Test",
            agent_config=self.agent_config,
            task_instructions="Clone me.",
            pre_authorized_tools=["load_document_text"],
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            disabled_on_clone=True,
            creator=self.user,
        )
        corpus = Corpus.objects.create(title="Clone Target", creator=self.user)

        action = template.clone_to_corpus(corpus)
        self.assertEqual(action.name, "Clone Test")
        self.assertEqual(action.corpus, corpus)
        self.assertEqual(action.agent_config, self.agent_config)
        self.assertEqual(action.task_instructions, "Clone me.")
        self.assertEqual(action.pre_authorized_tools, ["load_document_text"])
        self.assertEqual(action.trigger, CorpusActionTrigger.ADD_DOCUMENT)
        self.assertTrue(action.disabled)
        self.assertEqual(action.creator, self.user)

    def test_clone_to_corpus_sets_source_template(self):
        template = CorpusActionTemplate.objects.create(
            name="Source Test",
            agent_config=self.agent_config,
            task_instructions="Test source tracking.",
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )
        corpus = Corpus.objects.create(title="Source Target", creator=self.user)

        action = template.clone_to_corpus(corpus)
        self.assertEqual(action.source_template, template)

    def test_source_template_survives_template_deletion(self):
        template = CorpusActionTemplate.objects.create(
            name="Delete Test",
            agent_config=self.agent_config,
            task_instructions="Test SET_NULL.",
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )
        corpus = Corpus.objects.create(title="Delete Target", creator=self.user)

        action = template.clone_to_corpus(corpus)
        action_pk = action.pk
        template.delete()

        action.refresh_from_db()
        self.assertEqual(action.pk, action_pk)
        self.assertIsNone(action.source_template)

    def test_ordering_by_sort_order(self):
        t1 = CorpusActionTemplate.objects.create(
            name="Second",
            task_instructions="B",
            sort_order=2,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )
        t2 = CorpusActionTemplate.objects.create(
            name="First",
            task_instructions="A",
            sort_order=1,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )
        templates = list(
            CorpusActionTemplate.objects.filter(name__in=["First", "Second"]).order_by(
                "sort_order"
            )
        )
        self.assertEqual(templates[0].pk, t2.pk)
        self.assertEqual(templates[1].pk, t1.pk)

    def test_to_action_kwargs_raises_without_creator(self):
        """to_action_kwargs raises ValueError if no creator is available."""
        from unittest.mock import PropertyMock, patch

        template = CorpusActionTemplate.objects.create(
            name="No Creator Test",
            task_instructions="Test no creator.",
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )
        corpus = Corpus.objects.create(title="No Creator Corpus", creator=self.user)

        # Corpus.creator is NOT NULL at the DB level, so we mock the
        # descriptor to return None to exercise the defensive ValueError.
        with patch.object(type(corpus), "creator", new_callable=PropertyMock) as mock_c:
            mock_c.return_value = None
            with self.assertRaises(ValueError) as ctx:
                template.to_action_kwargs(corpus)

        self.assertIn("no creator provided", str(ctx.exception))


class DefaultTemplatesMigrationTest(TestCase):
    """Verify the data migration created the expected default templates.

    The data migration (agents/0010) requires a superuser to run. In test
    databases that start empty we call the migration function directly to
    exercise the same code path.
    """

    EXPECTED_NAMES = DEFAULT_TEMPLATE_NAMES

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Ensure a superuser exists so the migration function can run,
        # then invoke the migration logic if templates are missing.
        # Guard with existence check for --keepdb compatibility.
        from django.apps import apps

        cls._superuser, _ = User.objects.get_or_create(
            username="migration_admin",
            defaults={
                "password": "testpass",
                "email": "admin@test.com",
                "is_superuser": True,
                "is_staff": True,
            },
        )
        _create_default_action_templates(apps, None)

    def test_default_templates_exist(self):
        """All default templates should exist after migration."""
        for name in self.EXPECTED_NAMES:
            self.assertTrue(
                CorpusActionTemplate.objects.filter(name=name).exists(),
                f"Default template '{name}' not found",
            )

    def test_default_templates_have_agent_configs(self):
        """Each default template should have a linked AgentConfiguration."""
        for template in CorpusActionTemplate.objects.filter(
            name__in=self.EXPECTED_NAMES
        ):
            self.assertIsNotNone(
                template.agent_config,
                f"Template '{template.name}' has no agent_config",
            )
            self.assertTrue(
                template.agent_config.is_active,
                f"Agent config for '{template.name}' is not active",
            )

    def test_default_templates_are_active_and_enabled_on_clone(self):
        """Default templates should be active (used for new corpuses)
        and cloned actions should start enabled, except opt-out templates."""
        DISABLED_ON_CLONE = {"CAML Article Writer"}
        for template in CorpusActionTemplate.objects.filter(
            name__in=self.EXPECTED_NAMES
        ):
            self.assertTrue(template.is_active)
            if template.name in DISABLED_ON_CLONE:
                self.assertTrue(
                    template.disabled_on_clone,
                    f"'{template.name}' should be disabled on clone",
                )
            else:
                self.assertFalse(
                    template.disabled_on_clone,
                    f"'{template.name}' should be enabled on clone",
                )

    def test_default_templates_all_add_document_trigger(self):
        """All default templates should trigger on ADD_DOCUMENT."""
        for template in CorpusActionTemplate.objects.filter(
            name__in=self.EXPECTED_NAMES
        ):
            self.assertEqual(template.trigger, CorpusActionTrigger.ADD_DOCUMENT)

    def test_default_templates_have_pre_authorized_tools(self):
        """Each template should have pre-authorized tools matching its config."""
        for template in CorpusActionTemplate.objects.filter(
            name__in=self.EXPECTED_NAMES
        ):
            self.assertTrue(
                len(template.pre_authorized_tools) > 0,
                f"Template '{template.name}' has no pre-authorized tools",
            )

    def test_caml_article_writer_uses_custom_system_instructions(self):
        """CAML Article Writer agent config must use the dedicated CAML prompt."""
        template = CorpusActionTemplate.objects.get(name="CAML Article Writer")
        self.assertEqual(
            template.agent_config.system_instructions,
            _CAML_ARTICLE_SYSTEM_INSTRUCTIONS,
        )

    def test_seeded_agent_configs_have_non_null_slugs(self):
        """Every agent_config seeded by ``create_default_action_templates``
        MUST have a non-empty slug.

        Why this test exists: the seeder is invoked from migrations with
        ``apps.get_model()``, which returns a historical model class that
        lacks the ``save()`` override that auto-generates slugs. A previous
        regression left these agents with ``slug=NULL`` and crashed the
        @mention picker (``a.slug.toLowerCase()`` on null). The seeder now
        sets ``slug`` explicitly; this test pins that contract.
        """
        for template in CorpusActionTemplate.objects.filter(
            name__in=self.EXPECTED_NAMES
        ):
            agent_config = template.agent_config
            self.assertIsNotNone(
                agent_config.slug,
                f"Seeded agent for '{template.name}' has NULL slug",
            )
            self.assertNotEqual(
                agent_config.slug,
                "",
                f"Seeded agent for '{template.name}' has empty slug",
            )

    def test_seeding_is_idempotent(self):
        """Calling create_default_action_templates twice doesn't duplicate records."""
        from django.apps import apps

        from opencontractserver.corpuses.template_seeds import TEMPLATES

        # First call already happened in setUpClass; call again
        _create_default_action_templates(apps, None)

        # Verify count is still exactly len(TEMPLATES)
        for tmpl_def in TEMPLATES:
            self.assertEqual(
                CorpusActionTemplate.objects.filter(name=tmpl_def["name"]).count(),
                1,
                f"Template '{tmpl_def['name']}' was duplicated",
            )
            self.assertEqual(
                AgentConfiguration.objects.filter(
                    name=f"{tmpl_def['name']} Agent"
                ).count(),
                1,
                f"AgentConfig for '{tmpl_def['name']}' was duplicated",
            )


class ReverseMigrationTest(TestCase):
    """Test the reverse_migration function deletes seeded templates and configs."""

    def test_reverse_migration_deletes_templates_and_configs(self):
        from django.apps import apps

        from opencontractserver.corpuses.template_seeds import (
            TEMPLATES,
            create_default_action_templates,
            reverse_migration,
        )

        # Ensure a superuser exists for seeding
        User.objects.create_user(
            username="reverse_admin",
            password="testpass",
            is_superuser=True,
            is_staff=True,
        )

        # Clean slate: remove any existing defaults
        reverse_migration(apps, None)

        # Seed templates
        create_default_action_templates(apps, None)

        # Verify templates and agent configs exist
        template_names = [t["name"] for t in TEMPLATES]
        agent_names = [f"{n} Agent" for n in template_names]
        self.assertEqual(
            CorpusActionTemplate.objects.filter(name__in=template_names).count(),
            len(TEMPLATES),
        )
        self.assertTrue(
            AgentConfiguration.objects.filter(name__in=agent_names).exists()
        )

        # Run reverse migration
        reverse_migration(apps, None)

        # Verify templates are deleted
        self.assertEqual(
            CorpusActionTemplate.objects.filter(name__in=template_names).count(),
            0,
        )
        # Verify agent configs are deleted
        self.assertFalse(
            AgentConfiguration.objects.filter(name__in=agent_names).exists()
        )


class NoSuperuserSeedingTest(TestCase):
    """Test that seeding gracefully skips when no superuser exists."""

    def test_no_superuser_skips_seeding(self):
        from django.apps import apps

        from opencontractserver.corpuses.template_seeds import (
            TEMPLATES,
            create_default_action_templates,
            reverse_migration,
        )

        # Clean slate
        reverse_migration(apps, None)

        # Ensure no superusers exist
        User.objects.filter(is_superuser=True).delete()

        # Seed should silently skip
        create_default_action_templates(apps, None)

        # Verify no templates were created
        template_names = [t["name"] for t in TEMPLATES]
        self.assertEqual(
            CorpusActionTemplate.objects.filter(name__in=template_names).count(),
            0,
        )
