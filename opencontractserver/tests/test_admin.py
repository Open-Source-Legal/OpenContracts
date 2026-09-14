import logging
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import Client, TestCase
from django.urls import reverse
from guardian import forms as guardian_forms
from guardian.shortcuts import assign_perm

from config.graphql.core.permissions import resolve_my_permissions
from opencontractserver.corpuses.admin import CorpusAdmin
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.shared.Managers import _apply_document_prefetches
from opencontractserver.types.enums import PermissionTypes

User = get_user_model()

logger = logging.getLogger(__name__)


def get_admin_change_view_url(obj: object) -> str:
    return reverse(
        f"admin:{obj._meta.app_label}_{type(obj).__name__.lower()}_change",
        args=(obj.pk,),
    )


def get_admin_changelist_view_url(obj: object) -> str:
    return reverse(
        "admin:{}_{}_changelist".format(
            obj._meta.app_label, type(obj).__name__.lower()
        ),
        args=(obj.pk,),
    )


class TestUserAdmin(TestCase):
    def setUp(self) -> None:

        User.objects.create_superuser(
            username="superuser", password="secret", email="admin@example.com"
        )

        self.admin_client = Client()
        self.admin_client.login(username="superuser", password="secret")

    def test_user_change_view(self):

        # create test data
        my_group = Group.objects.create(name="Test Group")

        # run test
        response = self.admin_client.get(get_admin_change_view_url(my_group))
        self.assertEqual(response.status_code, 200)

    def test_changelist(self):
        url = reverse("admin:users_user_changelist")
        response = self.admin_client.get(url)
        assert response.status_code == 200

    def test_search(self):
        url = reverse("admin:users_user_changelist")
        response = self.admin_client.get(url, data={"q": "test"})
        assert response.status_code == 200

    def test_add(self):
        url = reverse("admin:users_user_add")
        response = self.admin_client.get(url)
        assert response.status_code == 200

        response = self.admin_client.post(
            url,
            data={
                "username": "test",
                "password1": "My_R@ndom-P@ssw0rd",
                "password2": "My_R@ndom-P@ssw0rd",
            },
        )
        assert response.status_code == 302
        assert User.objects.filter(username="test").exists()

    def test_view_user(self):
        user = User.objects.get(username="superuser")
        url = reverse("admin:users_user_change", kwargs={"object_id": user.pk})
        response = self.admin_client.get(url)
        assert response.status_code == 200


class TestAnalyzerAdmin(TestCase):
    def setUp(self) -> None:

        self.user = User.objects.create_superuser(
            username="superuser", password="secret", email="admin@example.com"
        )

        self.admin_client = Client()
        self.admin_client.login(username="superuser", password="secret")
        self.corpus_admin = CorpusAdmin(Corpus, None)

    def test_gremlin_changelist(self):
        url = reverse("admin:analyzer_gremlinengine_changelist")
        response = self.admin_client.get(url)
        assert response.status_code == 200

    def test_gremlin_add(self):

        user = User.objects.get(username="superuser")
        url = reverse("admin:analyzer_gremlinengine_add")
        response = self.admin_client.get(url)
        assert response.status_code == 200

        response = self.admin_client.post(
            url,
            data={
                "creator_id": user.id,
                "url": "www.myrandomurl.com",
            },
        )

        logger.info(f"test_add - response: {response}")

    def test_display_icon_with_icon(self):
        obj = Mock(icon=Mock(url="http://example.com/icon.png"))
        result = self.corpus_admin.display_icon(obj)
        self.assertIn('src="http://example.com/icon.png"', result)
        self.assertIn('width="50"', result)
        self.assertIn('height="50"', result)

    def test_display_icon_without_icon(self):
        obj = Mock(icon=None)
        result = self.corpus_admin.display_icon(obj)
        self.assertEqual(result, "No icon")

    @patch("opencontractserver.corpuses.admin.make_corpus_public_task")
    def test_make_public(self, mock_task):
        # Mock the si() method to return a mock with apply_async
        mock_signature = Mock()
        mock_signature.apply_async.return_value = None
        mock_task.si.return_value = mock_signature

        corpus1 = Corpus(
            title="Test", description="Some important stuff!", creator=self.user
        )
        corpus1.save()

        corpus2 = Corpus(
            title="Test2", description="Some important stuff!", creator=self.user
        )
        corpus2.save()

        request = Mock()
        self.corpus_admin.message_user = Mock()

        # Only pass the corpuses we created in this test
        test_corpuses = Corpus.objects.filter(id__in=[corpus1.pk, corpus2.pk])
        self.corpus_admin.make_public(request, test_corpuses)

        # Verify make_corpus_public_task.si() was called for each corpus
        mock_task.si.assert_any_call(corpus_id=corpus1.pk)
        mock_task.si.assert_any_call(corpus_id=corpus2.pk)
        self.assertEqual(mock_task.si.call_count, 2)

        # Verify the correct message was sent to the user
        self.corpus_admin.message_user.assert_called_once_with(
            request, "Started making 2 corpus(es) public."
        )

    def test_admin_permission_edits_expire_held_grants(self):
        reader = User.objects.create_user(username="admin-grant-reader")
        group = Group.objects.create(name="Admin grant readers")
        group.user_set.add(reader)
        for model in (Corpus, Document):
            read = f"read_{model._meta.model_name}"
            for target, kind in ((reader, "user"), (group, "group")):
                for allowed in (False, True):
                    with self.subTest(model=model, kind=kind, allowed=allowed):
                        row = model.objects.create(
                            creator=self.user, title="Admin grant"
                        )
                        if allowed:
                            assign_perm(read, target, row)
                        rows = model.objects.filter(pk=row.pk)
                        if model is Document:
                            rows = _apply_document_prefetches(
                                rows, reader, lightweight=True
                            )
                        held, cold = rows.get(), rows.get()
                        request = SimpleNamespace(user=reader)
                        self.assertEqual(
                            held.user_can(
                                reader, PermissionTypes.READ, request=request
                            ),
                            allowed,
                        )
                        url = reverse(
                            f"admin:{row._meta.app_label}_{row._meta.model_name}_permissions_manage_{kind}",
                            args=(row.pk, target.pk),
                        )
                        response = self.admin_client.post(
                            url,
                            {"permissions": [] if allowed else [read], "_save": "Save"},
                        )
                        self.assertRedirects(
                            response, url, fetch_redirect_response=False
                        )
                        for instance in (held, cold):
                            self.assertEqual(
                                instance.user_can(
                                    reader, PermissionTypes.READ, request=request
                                ),
                                not allowed,
                            )
                            self.assertEqual(
                                read
                                in resolve_my_permissions(
                                    instance, SimpleNamespace(context=request)
                                ),
                                not allowed,
                            )
                        with self.assertNumQueries(0):
                            self.assertEqual(
                                held.user_can(reader, PermissionTypes.READ), not allowed
                            )

    def test_admin_grant_failures_restore_previous_permissions(self):
        reader = User.objects.create_user(username="admin-grant-failure-reader")
        group = Group.objects.create(name="Admin grant failure readers")
        real_assign = guardian_forms.assign_perm
        for target, kind in ((reader, "user"), (group, "group")):
            with self.subTest(kind=kind):
                row = Corpus.objects.create(
                    creator=self.user, title="Failed admin grant"
                )
                assign_perm("read_corpus", target, row)
                url = reverse(
                    f"admin:corpuses_corpus_permissions_manage_{kind}",
                    args=(row.pk, target.pk),
                )

                def fail_after_assignment(*args, **kwargs):
                    real_assign(*args, **kwargs)
                    raise RuntimeError("assignment failed afterward")

                for patch_target, failure in (
                    ("guardian.forms.assign_perm", fail_after_assignment),
                    (
                        "opencontractserver.shared.grant_cache._GrantRevision.invalidate",
                        RuntimeError("invalidation failed"),
                    ),
                ):
                    with self.subTest(failure=patch_target):
                        with patch(
                            patch_target, side_effect=failure
                        ), self.assertRaises(RuntimeError):
                            self.admin_client.post(
                                url, {"permissions": ["update_corpus"]}
                            )
                        rows = getattr(row, f"corpus{kind}objectpermission_set")
                        self.assertEqual(
                            set(
                                rows.filter(**{kind: target}).values_list(
                                    "permission__codename", flat=True
                                )
                            ),
                            {"read_corpus"},
                        )

    def test_admin_grant_forms_keep_existing_change_authority_and_choices(self):
        staff = User.objects.create_user(username="grant-staff", is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename="change_document"))
        reader = User.objects.create_user(
            username="admin-grant-recipient", is_active=False
        )
        group = Group.objects.create(name="Admin grant recipients")
        self.admin_client.force_login(staff)
        row = Document.objects.create(creator=self.user, title="Admin grant authority")
        self.assertFalse(row.user_can(staff, PermissionTypes.READ))
        for target, kind in ((reader, "user"), (group, "group")):
            with self.subTest(kind=kind):
                url = reverse(
                    f"admin:documents_document_permissions_manage_{kind}",
                    args=(row.pk, target.pk),
                )
                response = self.admin_client.post(
                    url, {"permissions": ["view_document"]}
                )
                self.assertRedirects(response, url, fetch_redirect_response=False)
                response = self.admin_client.post(
                    url, {"permissions": ["not_a_permission"]}
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
                rows = getattr(row, f"document{kind}objectpermission_set")
                self.assertEqual(
                    set(
                        rows.filter(**{kind: target}).values_list(
                            "permission__codename", flat=True
                        )
                    ),
                    {"view_document"},
                )
