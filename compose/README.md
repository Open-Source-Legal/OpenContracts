# Container dependency updates

Dependabot checks the base images in all eight Dockerfiles, the frontend's
Yarn dependencies, the Django/pipeline requirements, and the accelerated
services' requirements every weekday. Configure coverage in
[`../.github/dependabot.yml`](../.github/dependabot.yml).

Third-party Compose images live in [`compose.images.yml`](compose.images.yml).
The local, production, test, CI and remote-worker stacks inherit individual
image references with `extends`. Existing `docker compose -f local.yml`,
`-f production.yml`, `-f test.yml` and remote-worker commands still work.
The shared file supplies only image references; running it alone would start
services without their configuration.

Keep third-party image versions in that shared file when adding services.
Dependabot's Compose updater discovers standard Compose filenames, so adding
an entry for a directory containing only `local.yml` or `remote_worker.yml`
does not cover those files. Untagged and `latest` images are pinned to their
current registry digests so Dependabot can propose updates when they are rebuilt.
Locally built `opencontractserver_*` and `oc-*` image names stay in the stack
and accelerator overlays.

Python base-image updates are grouped across local and production and limited
to patch releases. Update the Python minor deliberately alongside CI and
`mypy.ini`. Use literal versions in `FROM` instructions so Dependabot can
update both build and runtime stages.

Accelerated service Python pins live next to their Dockerfiles in
`requirements*.txt`. Install PyTorch separately using the index selected by
`ACCEL`, before the embedder's other requirements. PyTorch updates stay within
the 2.6 / torchvision 0.21 series; new series require coordinating the CUDA/ROCm
indexes in both Dockerfiles and validating the supported accelerators.

Update the frontend `docxodus` package and the Docxodus service image's
`docxodus...` suffix together: their character offsets must agree. Automatic
frontend version updates for this package are excluded so they can be reviewed
as a coordinated change.
