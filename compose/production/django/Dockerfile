# Pin to a specific patch (not the floating 3.11 alias) so rebuilds on
# different dates do not silently pick up a new CPython point release that
# could change runtime behaviour. Bump deliberately when upstream ships a
# CVE/feature release and CI is green against the new patch.
ARG PYTHON_VERSION=3.11.15-slim-bookworm

# ---------------------------------------------------------------------------- #
# Build stage: full toolchain for compiling wheels (psycopg2, opencv, etc.)    #
# ---------------------------------------------------------------------------- #
FROM python:${PYTHON_VERSION} AS python-build-stage

ARG BUILD_ENVIRONMENT=production

# Harden pip against transient network failures during large wheel downloads.
# PIP_RESUME_RETRIES (pip 24.1+) resumes broken downloads; the others bump
# connection retry count and socket timeout. Without these, a mid-stream SSL
# drop while fetching a large wheel (e.g. opencv-python-headless) aborts the
# entire build.
ENV PIP_RETRIES=10 \
    PIP_TIMEOUT=60 \
    PIP_RESUME_RETRIES=5 \
    PIP_NO_CACHE_DIR=1

# Build-only system dependencies. None of these end up in the runtime image.
# `wget` is needed to fetch the large spaCy model wheel with explicit retry
# semantics (pip's retry can fall short on a multi-hundred-MB wheel over a
# transient SSL drop).
RUN apt-get update && apt-get install --no-install-recommends -y \
      build-essential \
      cmake \
      automake \
      pkg-config \
      libfreetype6-dev \
      libfontconfig-dev \
      libjpeg-dev \
      libopenjp2-7-dev \
      libcairo2-dev \
      libtiff5-dev \
      libtesseract-dev \
      libpq-dev \
      git \
      wget \
    && rm -rf /var/lib/apt/lists/*

# Copy the entire requirements directory for recursive building
COPY ./requirements ./requirements

RUN pip install --upgrade pip

# Build wheels for production requirements plus pluggable pipeline extras.
RUN (find ./requirements -mindepth 2 -type f -name "*.txt" -print; \
     printf '%s\n' ./requirements/production.txt) \
    | sort -u \
    | sed 's/^/-r /' \
    | xargs -r pip wheel --wheel-dir /usr/src/app/wheels

# Fetch pinned spaCy model wheels into the same wheel cache so the runtime
# stage installs them via the existing `pip install --no-index` step and
# `wget` never reaches the runtime image. Pinning the exact wheel URL is
# more reproducible than `python -m spacy download`, which resolves the
# wheel URL at build time and could silently drift to a different patch.
# `wget` retry args mirror compose/local/django/Dockerfile so the two paths
# behave the same on flaky networks.
RUN wget --retry-connrefused --waitretry=1 --read-timeout=20 --timeout=15 -t 5 \
      -P /usr/src/app/wheels \
      https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl \
    && echo "1932429db727d4bff3deed6b34cfc05df17794f4a52eeb26cf8928f7c1a0fb85  /usr/src/app/wheels/en_core_web_sm-3.8.0-py3-none-any.whl" | sha256sum -c - \
    && wget --retry-connrefused --waitretry=1 --read-timeout=20 --timeout=15 -t 5 \
      -P /usr/src/app/wheels \
      https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.8.0/en_core_web_lg-3.8.0-py3-none-any.whl \
    && echo "293e9547a655b25499198ab15a525b05b9407a75f10255e405e8c3854329ab63  /usr/src/app/wheels/en_core_web_lg-3.8.0-py3-none-any.whl" | sha256sum -c -

# ---------------------------------------------------------------------------- #
# Runtime stage: slim base, runtime libs only.                                 #
# ---------------------------------------------------------------------------- #
FROM python:${PYTHON_VERSION} AS python-run-stage

ARG BUILD_ENVIRONMENT=production
ARG APP_HOME=/app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BUILD_ENV=${BUILD_ENVIRONMENT} \
    PIP_RETRIES=10 \
    PIP_TIMEOUT=60 \
    PIP_RESUME_RETRIES=5 \
    PIP_NO_CACHE_DIR=1

WORKDIR ${APP_HOME}

RUN groupadd --system django \
    && useradd --system --gid django --no-log-init --create-home --home-dir /home/django django

# Runtime system dependencies. Keep this list minimal — every package shows
# up in the final image.
#   libpq5             : psycopg2 (binary protocol to Postgres)
#   gettext            : retained as a build hook for `manage.py
#                        compilemessages`. No `.po`/`.mo` files ship today
#                        (`locale/` is in `.dockerignore`), so this is dead
#                        weight at runtime — kept so future i18n work does
#                        not need a Dockerfile change. Drop if image size
#                        ever needs the ~5 MB.
#   poppler-utils      : pdf2image (pdftoppm/pdftocairo)
#   libgl1, libsm6,    : opencv-python-headless transitive runtime deps
#   libxext6,            (libGL, libSM, libXext, gthread-2.0, libgomp).
#   libglib2.0-0,        On slim-bookworm none of these are present in the
#   libgomp1             base; without them `import cv2` raises ImportError.
RUN apt-get update && apt-get install --no-install-recommends -y \
      libpq5 \
      gettext \
      poppler-utils \
      libgl1 \
      libglib2.0-0 \
      libgomp1 \
      libsm6 \
      libxext6 \
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies from prebuilt wheels only — no source builds at
# runtime, no pip cache retained.
COPY --from=python-build-stage /usr/src/app/wheels /wheels/
RUN pip install --upgrade pip \
    && pip install --no-index --find-links=/wheels/ /wheels/* \
    && rm -rf /wheels/

# Smoke test: `import cv2` must succeed inside the runtime image. Catches
# regressions where opencv-python-headless picks up a new shared-library
# dependency that we forgot to install above (the failure mode is silent at
# build time but immediate at first request).
RUN python -c "import cv2; print(f'cv2 {cv2.__version__} import OK')"

# Smoke test: spaCy models load. The wheels were installed alongside other
# dependencies via the build-stage wheel cache (see the pinned-URL `wget`
# block above). `spacy.load(...)` exercises the same code path used by
# `TxtParser`'s sentence chunker so a missing-or-corrupt model fails the
# build immediately rather than at first request.
RUN python -c "import spacy; spacy.load('en_core_web_sm'); spacy.load('en_core_web_lg'); print('spaCy models load OK')"

COPY --chown=django:django ./compose/production/django/entrypoint /entrypoint
RUN sed -i 's/\r$//g' /entrypoint && chmod +x /entrypoint

COPY --chown=django:django ./compose/production/django/start /start
RUN sed -i 's/\r$//g' /start && chmod +x /start

COPY --chown=django:django ./compose/production/django/celery/worker/start /start-celeryworker
RUN sed -i 's/\r$//g' /start-celeryworker && chmod +x /start-celeryworker

COPY --chown=django:django ./compose/production/django/celery/beat/start /start-celerybeat
RUN sed -i 's/\r$//g' /start-celerybeat && chmod +x /start-celerybeat

COPY ./compose/production/django/celery/flower/start /start-flower
RUN sed -i 's/\r$//g' /start-flower && chmod +x /start-flower

# Copy the full application code
COPY --chown=django:django . ${APP_HOME}

RUN chown django:django ${APP_HOME}

USER django

ENTRYPOINT ["/entrypoint"]
