from django.urls import path

from opencontractserver.discovery.views import (
    llms_full_txt,
    llms_txt,
    robots_txt,
    search_api,
    sitemap_xml,
    well_known_mcp,
    well_known_oauth_protected_resource,
)

app_name = "discovery"

urlpatterns = [
    path("robots.txt", robots_txt, name="robots_txt"),
    path("llms.txt", llms_txt, name="llms_txt"),
    path("llms-full.txt", llms_full_txt, name="llms_full_txt"),
    path("sitemap.xml", sitemap_xml, name="sitemap_xml"),
    path(".well-known/mcp.json", well_known_mcp, name="well_known_mcp"),
    path(
        ".well-known/oauth-protected-resource",
        well_known_oauth_protected_resource,
        name="well_known_oauth_protected_resource",
    ),
    # RFC 9728 §3.1 path-based metadata, e.g.
    # /.well-known/oauth-protected-resource/mcp/me
    path(
        ".well-known/oauth-protected-resource/<path:resource_path>",
        well_known_oauth_protected_resource,
        name="well_known_oauth_protected_resource_path",
    ),
    path("api/search/", search_api, name="search_api"),
]
