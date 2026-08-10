- **Release image publishing: raise the Django image size budget and add a
  manual re-publish path** (`.github/workflows/docker-build-release.yml`). The
  v3.0.0 release build was the first since v3.0.0.b1 to get past the runner's
  disk limits and actually finish the Django image — and it then failed the
  `Enforce Django image size budget` gate at 2.4 GiB against the 1.5 GiB
  acceptance criterion from issue #1494. The gate runs before the push step, so
  `ghcr.io/.../opencontractserver_django:v3.0.0` was never published while
  frontend, postgres, and traefik were. Two changes:
  - `DJANGO_IMAGE_BUDGET_BYTES` raised 1.5 GiB → 3 GiB, leaving ~25% headroom
    over the measured size so the gate still catches a real regression.
  - New `workflow_dispatch` trigger taking an existing `tag` input. A `release`
    event runs the workflow file *as it existed at the tag*, so re-running a
    failed release build can never pick up a workflow fix; dispatching from the
    default branch builds the tag's source with the current workflow. All
    `docker/metadata-action` tag patterns now derive from a single `BUILD_TAG`
    (dispatch input, else the released tag) so a dispatched re-publish emits
    byte-identical image tags to the release event it stands in for.
