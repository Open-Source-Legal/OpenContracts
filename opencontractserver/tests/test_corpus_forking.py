import base64
import pathlib
import uuid

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction

from opencontractserver.corpuses.models import Corpus, TemporaryFileHandle
from opencontractserver.tasks import import_corpus
from opencontractserver.tasks.utils import package_zip_into_base64
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.corpus_forking import build_fork_corpus_task
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class CorpusForkTestCase:

    fixtures_path = pathlib.Path(__file__).parent / "fixtures"

    def setUp(self):
        self.user = User.objects.create_user(username="bob", password="12345678")

    def test_corpus_forking(self):
        """
        Test that we can fork an imported corpus
        """

        print(
            "# TEST CORPUS FORK PIPELINE #########################################################################"
        )

        print("1)\tCreate a test corpus to fork")
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
        print("\t\tCOMPLETED")

        print("2)\tBuild the import task...")
        fork_task = build_fork_corpus_task(
            corpus_pk_to_fork=original_corpus_obj.id, user=self.user
        )
        print("\t\tBUILT")

        print("3)\tRun the import task...")
        task_results = fork_task.apply().get()
        print("\t\tCOMPLETED")

        forked_corpus = Corpus.objects.get(id=task_results)

        print("4)\tMake sure we were able to get corpus obj...")
        assert isinstance(forked_corpus, Corpus)
        print("\t\tSUCCESS")

        print("5)\tMake sure the forked object has a parent...")
        assert isinstance(forked_corpus.parent, Corpus)
        print("\t\tSUCCESS")

        print("6)\tMake sure the forked corpus has same annotations")
        assert (
            forked_corpus.parent.annotation_set.all().count()
            == original_corpus_obj.annotation_set.all().count()
        )
        print("\t\tSUCCESS")

        print("7)\tMake sure the document count is the same")
        assert (
            forked_corpus.get_documents().count()
            == original_corpus_obj.get_documents().count()
        )
        print("\t\tSUCCESS")

        print("8)\tMake sure the labelset label counts are the same")
        original_labelset_labels = original_corpus_obj.label_set.annotation_labels.all()
        forked_labelset_labels = forked_corpus.label_set.annotation_labels.all()
        assert forked_labelset_labels.count() == original_labelset_labels.all()
        print("\t\tSUCCESS")

        # TODO - improve tests to actually check data integrity of cloned objs...
