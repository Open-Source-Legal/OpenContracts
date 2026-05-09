from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Minimal public user serializer.

    Exposes only the case-sensitive ``slug`` (the user's public handle) and
    the URL of the API detail view. ``username``, ``name`` and other PII
    are deliberately omitted — see :class:`config.graphql.user_types.UserType`
    for the canonical privacy policy. Detail-view lookup uses ``slug`` so
    the URL itself never leaks the OAuth ``sub`` for social-login users.
    """

    class Meta:
        model = User
        fields = ["slug", "url"]

        extra_kwargs = {"url": {"view_name": "api:user-detail", "lookup_field": "slug"}}
