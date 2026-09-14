"""One explicit Automation header scheme across GraphQL and import REST."""

from django.core.exceptions import ValidationError
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from opencontractserver.users.services.automation_credentials import (
    INVALID,
    authenticate_token,
)


class AutomationAuthentication(BaseAuthentication):
    keyword = "Automation"

    def authenticate(self, request):
        try:
            parts = get_authorization_header(request).split()
        except UnicodeError:
            raise AuthenticationFailed(INVALID) from None
        if not parts or parts[0].lower() != b"automation":
            return None
        if len(parts) != 2:
            raise AuthenticationFailed(INVALID)
        try:
            credential = authenticate_token(parts[1].decode("ascii"))
        except (UnicodeError, ValidationError):
            raise AuthenticationFailed(INVALID) from None
        return credential.user, credential

    def authenticate_header(self, request):
        return self.keyword
