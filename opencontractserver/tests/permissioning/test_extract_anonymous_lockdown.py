"""Extracts are NEVER visible to anonymous users — at any layer.

2026-06 permissioning audit decision: the consolidated permissioning
guide's anonymous-access contract ("Extract — never") is the intended
semantic. ``ExtractService.get_visible_extracts`` previously exposed
``is_public`` extracts in public corpora to anonymous callers (drift
copied from the analysis service, reachable through the un-gated
``extracts`` GraphQL resolver); ``ExtractManager`` now denies anonymous
users on BOTH manager surfaces (``visible_to_user`` / ``user_can``) and
the service mirrors it.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.extracts.models import Extract, Fieldset
from opencontractserver.extracts.services import ExtractService
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class ExtractAnonymousLockdownTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="extract_anon_owner", email="eao@lock.test", password="x"
        )
        self.granted = User.objects.create_user(
            username="extract_anon_granted", email="eag@lock.test", password="x"
        )
        self.anon = AnonymousUser()

        self.public_corpus = Corpus.objects.create(
            title="Public Extract Corpus", creator=self.owner, is_public=True
        )
        self.fieldset = Fieldset.objects.create(
            name="Anon Lockdown Fieldset", creator=self.owner
        )
        # The worst case for the lockdown: a PUBLIC extract in a PUBLIC
        # corpus — previously anonymous-visible through the service.
        self.public_extract = Extract.objects.create(
            name="Public Extract",
            corpus=self.public_corpus,
            fieldset=self.fieldset,
            creator=self.owner,
            is_public=True,
        )

    # ---- service surface -------------------------------------------------

    def test_service_listing_is_empty_for_anonymous(self):
        qs = ExtractService.get_visible_extracts(self.anon)
        self.assertFalse(qs.exists())

    def test_service_listing_is_empty_for_anonymous_with_corpus_scope(self):
        qs = ExtractService.get_visible_extracts(
            self.anon, corpus_id=self.public_corpus.id
        )
        self.assertFalse(qs.exists())

    def test_check_extract_permission_denies_anonymous(self):
        has_perm, extract = ExtractService.check_extract_permission(
            self.anon, self.public_extract.id
        )
        self.assertFalse(has_perm)
        self.assertIsNone(extract)

    # ---- manager surfaces (filter/check parity) --------------------------

    def test_manager_visible_to_user_is_empty_for_anonymous(self):
        self.assertFalse(Extract.objects.visible_to_user(self.anon).exists())
        self.assertFalse(Extract.objects.visible_to_user(None).exists())

    def test_manager_user_can_denies_anonymous(self):
        self.assertFalse(
            Extract.objects.user_can(
                self.anon, self.public_extract, PermissionTypes.READ
            )
        )
        self.assertFalse(
            Extract.objects.user_can(None, self.public_extract, PermissionTypes.READ)
        )

    def test_anonymous_filter_check_parity(self):
        """``user_can(anon, x, READ)`` must equal membership in
        ``visible_to_user(anon)`` — both empty/False after the lockdown."""
        check = Extract.objects.user_can(
            self.anon, self.public_extract, PermissionTypes.READ
        )
        in_filter = (
            Extract.objects.visible_to_user(self.anon)
            .filter(pk=self.public_extract.pk)
            .exists()
        )
        self.assertEqual(check, in_filter)
        self.assertFalse(check)

    # ---- authenticated paths are unaffected -------------------------------

    def test_creator_still_sees_extract_everywhere(self):
        self.assertTrue(
            ExtractService.get_visible_extracts(self.owner)
            .filter(pk=self.public_extract.pk)
            .exists()
        )
        has_perm, extract = ExtractService.check_extract_permission(
            self.owner, self.public_extract.id
        )
        self.assertTrue(has_perm)
        assert extract is not None  # narrow Optional for mypy; asserted above
        self.assertEqual(extract.pk, self.public_extract.pk)
        self.assertTrue(
            Extract.objects.visible_to_user(self.owner)
            .filter(pk=self.public_extract.pk)
            .exists()
        )
        self.assertTrue(
            Extract.objects.user_can(
                self.owner, self.public_extract, PermissionTypes.READ
            )
        )

    def test_granted_user_still_sees_private_extract(self):
        private_extract = Extract.objects.create(
            name="Private Extract",
            corpus=self.public_corpus,
            fieldset=self.fieldset,
            creator=self.owner,
            is_public=False,
        )
        set_permissions_for_obj_to_user(
            self.granted, private_extract, [PermissionTypes.READ]
        )
        self.assertTrue(
            Extract.objects.visible_to_user(self.granted)
            .filter(pk=private_extract.pk)
            .exists()
        )
        self.assertTrue(
            ExtractService.get_visible_extracts(self.granted)
            .filter(pk=private_extract.pk)
            .exists()
        )
