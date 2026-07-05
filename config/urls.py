import logging

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import include, path
from django.views import defaults as default_views
from graphene_django.views import GraphQLView

from config.admin_auth.views import Auth0AdminLoginView, Auth0AdminLogoutView
from config.graphql.schema import validation_rules
from config.graphql.security import conditional_csrf_exempt
from opencontractserver.analyzer.views import AnalysisCallbackView
from opencontractserver.annotations.views import AnnotationImagesView

logger = logging.getLogger(__name__)


def home_redirect(request):
    scheme = "https" if request.is_secure() else "http"
    host = request.get_host().split(":")[0]

    # Validate the host against ALLOWED_HOSTS to prevent open-redirect
    # attacks via a crafted Host header.
    allowed = settings.ALLOWED_HOSTS
    host_valid = False
    for pattern in allowed:
        if pattern == "*":
            host_valid = True
            break
        if pattern.startswith("."):
            # Django treats ".example.com" as a suffix match
            if host == pattern[1:] or host.endswith(pattern):
                host_valid = True
                break
        elif host == pattern:
            host_valid = True
            break

    if not host_valid:
        return HttpResponseRedirect("/")

    new_url = f"{scheme}://{host}:3000"
    return HttpResponseRedirect(new_url)


urlpatterns = [
    # Discovery endpoints (robots.txt, llms.txt, sitemap.xml, .well-known/mcp.json)
    path("", include("opencontractserver.discovery.urls")),
    path("api/health/", lambda request: JsonResponse({"status": "ok"})),
    # Root URL redirect to the frontend dev server (:3000). Skipped on the
    # desktop build, where Daphne serves the SPA itself (see the SPA catch-all
    # appended below when OC_DESKTOP_SPA_ROOT is set).
    *(
        []
        if getattr(settings, "OC_DESKTOP_SPA_ROOT", "")
        else [path("", home_redirect, name="home_redirect")]
    ),
    # Custom admin login/logout views (must be before admin.site.urls to override defaults)
    path("admin/login/", Auth0AdminLoginView.as_view(), name="admin_auth0_login"),
    path("admin/logout/", Auth0AdminLogoutView.as_view(), name="admin_auth0_logout"),
    path(settings.ADMIN_URL, admin.site.urls),
    path(
        "graphql/",
        conditional_csrf_exempt(
            GraphQLView.as_view(
                graphiql=settings.DEBUG,
                validation_rules=validation_rules,
            )
        ),
    ),
    path(
        "api/annotations/<int:annotation_id>/images/",
        AnnotationImagesView.as_view(),
        name="annotation_images",
    ),
    path(
        "api/worker-uploads/",
        include("opencontractserver.worker_uploads.urls", namespace="worker_uploads"),
    ),
    path(
        "api/imports/",
        include(
            "opencontractserver.document_imports.urls",
            namespace="document_imports",
        ),
    ),
    *(
        []
        if not settings.USE_ANALYZER
        else [
            path("analysis/<int:analysis_id>/complete", AnalysisCallbackView.as_view())
        ]
    ),
    *(
        []
        if not settings.DEBUG
        else [
            *(
                []
                if not getattr(settings, "USE_SILK", False)
                else [path("silk/", include("silk.urls", namespace="silk"))]
            ),
            path(
                "400/",
                default_views.bad_request,
                kwargs={"exception": Exception("Bad Request!")},
            ),
            path(
                "403/",
                default_views.permission_denied,
                kwargs={"exception": Exception("Permission Denied")},
            ),
            path(
                "404/",
                default_views.page_not_found,
                kwargs={"exception": Exception("Page not Found")},
            ),
            path("500/", default_views.server_error),
        ]
    ),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# ``static()`` silently no-ops when DEBUG is False, which leaves the E2E/test
# environment (config.settings.test, DEBUG off, local file storage, no
# S3/GCS/nginx in front) with NO media serving at all — every
# ``/media/...`` fetch 404s, so flows that load file-backed content in the
# browser (e.g. the corpus Readme.CAML article body) can never succeed.
# ``SERVE_MEDIA_WITHOUT_DEBUG`` is set ONLY by the test settings; production
# serves media from object storage and never enables it.
if getattr(settings, "SERVE_MEDIA_WITHOUT_DEBUG", False) and not settings.DEBUG:
    from django.urls import re_path
    from django.views.static import serve as media_serve

    urlpatterns += [
        re_path(
            rf"^{settings.MEDIA_URL.lstrip('/')}(?P<path>.*)$",
            media_serve,
            {"document_root": settings.MEDIA_ROOT},
        ),
    ]

# Desktop build: serve the pre-built React SPA from Daphne. WhiteNoise serves the
# hashed assets before the request reaches Django; this catch-all returns
# index.html for any remaining (client-side route) path. Registered LAST so it
# never shadows /api/, /graphql/, /admin/, /mcp*, /ws/ or static/media routes,
# and only when the desktop profile points OC_DESKTOP_SPA_ROOT at a built dist/.
if getattr(settings, "OC_DESKTOP_SPA_ROOT", ""):
    from django.urls import re_path as _re_path

    from config.spa import spa_fallback

    urlpatterns += [
        _re_path(
            # Exclude the backend route prefixes by whole path segment (``/`` or
            # end-of-path) so a future SPA route like ``/mcp-guide`` still falls
            # through to index.html.
            r"^(?!(?:api|graphql|admin|mcp|sse|ws|static|media)(?:/|$))"
            r"(?P<resource_path>.*)$",
            spa_fallback,
            name="spa_fallback",
        ),
    ]
