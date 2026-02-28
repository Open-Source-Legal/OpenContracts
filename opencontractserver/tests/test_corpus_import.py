import base64
import pathlib
import uuid

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction

from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.corpuses.models import Corpus, TemporaryFileHandle
from opencontractserver.documents.models import Document
from opencontractserver.tasks import import_corpus
from opencontractserver.tasks.utils import package_zip_into_base64
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class ImportCorpusTestCase:

    fixtures_path = pathlib.Path(__file__).parent / "fixtures"

    def setUp(self):
        self.user = User.objects.create_user(username="bob", password="12345678")

    def test_import(self):

        export_zip_base64_file_string = package_zip_into_base64(
            self.fixtures_path / "Test_Corpus_EXPORT.zip"
        )
        # print("\t\tLOADED")

        # print("2)\tCreate seed corpus to import data into...")
        corpus_obj = Corpus.objects.create(
            title="New Import", creator=self.user, backend_lock=False
        )
        set_permissions_for_obj_to_user(self.user, corpus_obj, [PermissionTypes.ALL])
        # print("\t\tCREATED")

        # print("3)\tBuild celery task to import")
        base64_img_bytes = export_zip_base64_file_string.encode("utf-8")
        decoded_file_data = base64.decodebytes(base64_img_bytes)

        with transaction.atomic():
            temporary_file = TemporaryFileHandle.objects.create()
            temporary_file.file.save(
                ContentFile(decoded_file_data, name=f"corpus_import_{uuid.uuid4()}.pdf")
            )
        import_task = import_corpus.s(temporary_file.id, self.user.id, corpus_obj.id)
        # print("\t\tBUILT")

        # print("4)\tRun the celery task...")
        import_results = import_task.apply().get()
        assert isinstance(import_results, str)
        # print("\t\tCOMPLETED")

        labels = AnnotationLabel.objects.all()
        assert labels.count() == 2

        corpuses = Corpus.objects.all()
        assert corpuses.count() == 1

        annotations = Annotation.objects.all()
        assert annotations.count() == 2

        documents = Document.objects.all()
        assert documents.count() == 2
        # NOTE(deferred): Only object counts are checked. Field-level integrity
        # of the imported corpus (labels, annotations, relationships) is not
        # validated — worth expanding for round-trip import/export coverage.
