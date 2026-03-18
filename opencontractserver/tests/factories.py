from collections.abc import Sequence
from typing import Any

from django.contrib.auth import get_user_model
from factory import Faker, LazyAttribute, post_generation
from factory.django import DjangoModelFactory

from opencontractserver.annotations.models import TOKEN_LABEL, Annotation
from opencontractserver.documents.models import Document


class UserFactory(DjangoModelFactory):

    username = Faker("user_name")
    email = Faker("email")
    name = Faker("name")

    @post_generation
    def password(self, create: bool, extracted: Sequence[Any], **kwargs):
        password = (
            extracted
            if extracted
            else Faker(
                "password",
                length=42,
                special_chars=True,
                digits=True,
                upper_case=True,
                lower_case=True,
            ).evaluate(None, None, extra={"locale": None})
        )
        self.set_password(password)

    class Meta:
        model = get_user_model()
        django_get_or_create = ["username"]


class DocumentFactory(DjangoModelFactory):
    """Factory for creating realistic `Document` instances for tests.

    This intentionally keeps file-related fields empty to avoid filesystem I/O
    in most unit tests. When needed, tests should set these explicitly or rely
    on `BaseFixtureTestCase` which copies fixture files into `MEDIA_ROOT`.
    """

    title = Faker("sentence", nb_words=3)
    description = Faker("paragraph", nb_sentences=2)
    file_type = "application/pdf"
    page_count = 3
    creator = LazyAttribute(lambda o: UserFactory())
    is_public = False

    class Meta:
        model = Document


class AnnotationFactory(DjangoModelFactory):
    """Factory for creating realistic `Annotation` instances.

    Defaults to a token-level annotation on page 1 with minimal geometry and
    JSON payload. A `document` is required; if not provided, a fresh
    `Document` with a new `creator` will be created.
    """

    page = 1
    raw_text = Faker("sentence")
    json = {"v": 2, "p": {"1": {"b": [0.1, 0.1, 0.9, 0.2], "t": ""}}}
    annotation_type = TOKEN_LABEL
    annotation_label = None
    document = LazyAttribute(lambda o: DocumentFactory())
    corpus = None
    structural = False
    creator = LazyAttribute(lambda o: o.document.creator)

    class Meta:
        model = Annotation
