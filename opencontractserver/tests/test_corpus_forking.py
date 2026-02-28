import base64
import pathlib
import uuid

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TransactionTestCase

from opencontractserver.corpuses.models import Corpus, TemporaryFileHandle
from opencontractserver.tasks import import_corpus
from opencontractserver.tasks.utils import package_zip_into_base64
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.corpus_forking import build_fork_corpus_task
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class CorpusForkTestCase(TransactionTestCase):

    fixtures_path = pathlib.Path(__file__).parent / "fixtures"

    def setUp(self):
        self.user = User.objects.create_user(username="bob", password="12345678")

    def test_corpus_forking(self):
        """
        Test that we can fork an imported corpus
        """

        export_zip_base64_file_string = package_zip_into_base64(
            self.fixtures_path / "Test_Corpus_EXPORT.zip"
        )
        original_corpus_obj = Corpus.objects.create(
            title="New Import", creator=self.user, backend_lock=False
        )
        set_permissions_for_obj_to_user(
            self.user, original_corpus_obj, [PermissionTypes.ALL]
        )

        base64_img_bytes = export_zip_base64_file_string.encode("utf-8")
        decoded_file_data = base64.decodebytes(base64_img_bytes)

        with transaction.atomic():
            temporary_file = TemporaryFileHandle.objects.create()
            temporary_file.file.save(
                f"corpus_import_{uuid.uuid4()}.pdf", ContentFile(decoded_file_data)
            )

        import_task = import_corpus.s(
            temporary_file.id, self.user.id, original_corpus_obj.id
        )

        import_task.apply().get()
        # Refresh from DB to get imported data (label_set, etc.)
        original_corpus_obj.refresh_from_db()
        fork_task = build_fork_corpus_task(
            corpus_pk_to_fork=original_corpus_obj.id, user=self.user
        )
        task_results = fork_task.apply().get()

        forked_corpus = Corpus.objects.get(id=task_results)
        # Ensure we have the latest data from the DB
        forked_corpus.refresh_from_db()

        assert isinstance(forked_corpus, Corpus)
        assert isinstance(forked_corpus.parent, Corpus)

        from opencontractserver.annotations.models import Annotation

        forked_annotation_count = Annotation.objects.filter(
            corpus=forked_corpus, analysis__isnull=True
        ).count()
        original_annotation_count = Annotation.objects.filter(
            corpus=original_corpus_obj, analysis__isnull=True
        ).count()
        assert forked_annotation_count == original_annotation_count

        assert (
            forked_corpus.get_documents().count()
            == original_corpus_obj.get_documents().count()
        )

        original_labelset_labels = original_corpus_obj.label_set.annotation_labels.all()
        forked_labelset_labels = forked_corpus.label_set.annotation_labels.all()
        assert forked_labelset_labels.count() == original_labelset_labels.count()
        # NOTE(deferred): Only counts are compared — field-level data integrity
        # of cloned annotations, relationships, and label properties is not yet
        # validated. Worth expanding when fork-related bugs surface.
