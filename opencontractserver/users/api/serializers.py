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

    .. warning::
       **For anyone adding a ``UserViewSet``**: this serializer's
       ``lookup_field`` only controls how *hyperlinked URL values* are
       generated. Route resolution requires the corresponding
       ``UserViewSet`` to also set ``lookup_field = "slug"`` (and the
       router registration to match) — otherwise generated URLs will
       silently 404. The viewset deliberately does not exist yet; this
       serializer is unwired in production routes. If/when you wire it,
       the matching viewset MUST look like::

           class UserViewSet(RetrieveModelMixin, GenericViewSet):
               # Must match UserSerializer.Meta extra_kwargs[url][lookup_field].
               lookup_field = "slug"
               # CAUTION: do NOT add ``ListModelMixin`` here without also
               # overriding ``get_queryset`` to filter via
               # ``User.objects.visible_to_user(self.request.user)``. A bare
               # ``ListModelMixin`` would expose a paginated authenticated-
               # users list, which bypasses the slug-only privacy gate that
               # already governs the GraphQL surface.
               queryset = User.objects.all()
               serializer_class = UserSerializer

       Search the repo for ``UserViewSet`` before wiring to surface this
       contract.
    """

    class Meta:
        model = User
        fields = ["slug", "url"]

        # Must stay in sync with UserViewSet.lookup_field — see class docstring.
        extra_kwargs = {"url": {"view_name": "api:user-detail", "lookup_field": "slug"}}
