import logging
from unittest.mock import Mock, patch

from django.contrib.auth.models import Group
from django.db.models import Model
from django.test import Client, TestCase
from django.urls import reverse

from opencontractserver.corpuses.admin import CorpusAdmin
from opencontractserver.corpuses.models import Corpus
from opencontractserver.users.models import User

logger = logging.getLogger(__name__)


def get_admin_change_view_url(obj: Model) -> str:
    return reverse(
        f"admin:{obj._meta.app_label}_{type(obj).__name__.lower()}_change",
        args=(obj.pk,),
    )


def get_admin_changelist_view_url(obj: Model) -> str:
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
        self.corpus_admin = CorpusAdmin(Corpus, None)  # type: ignore[arg-type]

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
        self.corpus_admin.message_user = Mock()  # type: ignore[method-assign]

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
