"""Analysis listing filter/check parity with ``check_analysis_permission``.

2026-06 audit, review round 20: ``AnalysisService.get_visible_analyses``
had the same drift its sibling ``ExtractService.get_visible_extracts``
carried before round 6 — user-table-only guardian ``Exists`` (any
codename) on the analysis leg and a ``codename__contains="read"``
substring match on the corpus leg, while the single-object
``check_analysis_permission`` resolves both through ``user_can`` (group
grants + exact read codename). Both legs now join the group
object-permission tables and match ``read_analysis`` / ``read_corpus``
exactly.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from guardian.shortcuts import assign_perm

from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.analyzer.services import AnalysisService
from opencontractserver.corpuses.models import Corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class AnalysisListingGrantParityTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="algp_owner", email="alo@parity.test", password="x"
        )
        self.group_user = User.objects.create_user(
            username="algp_group_user", email="alg@parity.test", password="x"
        )
        self.update_only = User.objects.create_user(
            username="algp_update_only", email="alu@parity.test", password="x"
        )
        self.group = Group.objects.create(name="analysis_listing_group")
        self.group_user.groups.add(self.group)

        self.private_corpus = Corpus.objects.create(
            title="ALGP Corpus", creator=self.owner, is_public=False
        )
        self.analyzer = Analyzer.objects.create(
            id="algp_analyzer",
            description="x",
            creator=self.owner,
            task_name="opencontractserver.tasks.noop",
        )
        self.private_analysis = Analysis.objects.create(
            analyzer=self.analyzer,
            analyzed_corpus=self.private_corpus,
            creator=self.owner,
            is_public=False,
        )

    def test_group_grants_on_analysis_and_corpus_unlock_listing(self):
        # Both legs via GROUP grants only.
        assign_perm("read_analysis", self.group, self.private_analysis)
        assign_perm("read_corpus", self.group, self.private_corpus)
        self.assertTrue(
            AnalysisService.get_visible_analyses(self.group_user)
            .filter(pk=self.private_analysis.pk)
            .exists(),
            "group-granted analysis READ + corpus READ must unlock the listing",
        )
        # And the single-object surface agrees.
        has_perm, _ = AnalysisService.check_analysis_permission(
            self.group_user, self.private_analysis.id
        )
        self.assertTrue(has_perm)

    def test_update_only_analysis_grant_does_not_unlock_listing(self):
        # UPDATE-only on the analysis (no READ); corpus READ granted directly.
        set_permissions_for_obj_to_user(
            self.update_only, self.private_analysis, [PermissionTypes.UPDATE]
        )
        set_permissions_for_obj_to_user(
            self.update_only, self.private_corpus, [PermissionTypes.READ]
        )
        self.assertFalse(
            AnalysisService.get_visible_analyses(self.update_only)
            .filter(pk=self.private_analysis.pk)
            .exists(),
            "listing must require the exact read_analysis codename "
            "(parity with check_analysis_permission's user_can READ)",
        )
