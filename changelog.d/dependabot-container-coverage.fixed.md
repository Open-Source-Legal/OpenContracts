- Extended Dependabot coverage to every Dockerfile, shared Compose service
  images, frontend dependencies, and accelerated service Python requirements.
  Centralized service image references without changing existing Compose
  commands and pinned floating images to their current registry digests.
  Made Django Python base-image pins directly updateable and kept Python,
  PyTorch, and Docxodus updates within their compatibility constraints.
