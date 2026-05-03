from typing import cast

import pytest

from opencontractserver.tests.factories import UserFactory
from opencontractserver.users.models import User


@pytest.fixture(autouse=True)
def media_storage(settings, tmpdir):
    settings.MEDIA_ROOT = tmpdir.strpath


@pytest.fixture
def user() -> User:
    return cast(User, UserFactory())
