from django.urls import path

from opencontractserver.discovery.views import (
    llms_full_txt,
    llms_txt,
    robots_txt,
    search_api,
    sitemap_xml,
    well_known_mcp,
)

app_name = "discovery"

urlpatterns = [
    path("robots.txt", robots_txt, name="robots_txt"),
    path("llms.txt", llms_txt, name="llms_txt"),
    path("llms-full.txt", llms_full_txt, name="llms_full_txt"),
    path("sitemap.xml", sitemap_xml, name="sitemap_xml"),
    path(".well-known/mcp.json", well_known_mcp, name="well_known_mcp"),
    path("api/search/", search_api, name="search_api"),
]
