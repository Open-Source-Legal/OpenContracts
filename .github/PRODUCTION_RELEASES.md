# Production image releases

`workflows/production-release.yml` builds images on main, waits for successful
repository CI on the same commit, and requests deployment through the
infrastructure-owned Cloud Build release pipeline. Production releases require
`PRODUCTION_RELEASES_ENABLED=true`; forks remain disabled by default. PR builds
validate images without authenticating to Google Cloud or publishing them.

Repository variables supplied by the infrastructure setup are
`PRODUCTION_PROJECT`, `PRODUCTION_IMAGE_REGISTRY`, `PRODUCTION_RELEASE_TOPIC`,
`PRODUCTION_WIF_PROVIDER`, and `PRODUCTION_PUBLISHER_ACCOUNT`. These are identifiers,
not secret keys. Authentication uses short-lived GitHub identity federation.

The final GitHub job reports that the release was queued. Cloud Build contains
the final rollout result and logs. Set `PRODUCTION_RELEASES_ENABLED=false` to
stop new requests; freeze/cancel Cloud Build releases too for an immediate stop.
Workflow/helper definitions are maintained by the infrastructure repository's
`releases/services.json` and `scripts/releases/render-workflow.py`.
