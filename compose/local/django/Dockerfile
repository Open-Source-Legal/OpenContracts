# Pin to a specific patch (not the floating 3.12 alias) so rebuilds on
# different dates do not silently pick up a new CPython point release.
# Keep this in sync with compose/production/django/Dockerfile.
#
# 3.12 unlocks ``sys.monitoring``-backed coverage (``COVERAGE_CORE=sysmon``),
# which is ~5-10x cheaper than the C-trace path required on 3.11. With the
# test suite running ``--cov`` on every push, that's the biggest single
# wall-time lever in CI.
ARG PYTHON_VERSION=3.12.7-slim-bookworm

# ---------------------------------------------------------------------------- #
# Build stage: full toolchain for compiling wheels (psycopg2, opencv, etc.)    #
# ---------------------------------------------------------------------------- #
FROM python:${PYTHON_VERSION} AS python-build-stage

ARG BUILD_ENVIRONMENT=local
ARG GITHUB_ACTIONS

# Harden pip against transient network failures during large wheel downloads.
# PIP_RESUME_RETRIES (pip 24.1+) resumes broken downloads; the others bump
# connection retry count and socket timeout. Without these, a mid-stream SSL
# drop while fetching a large wheel (e.g. opencv-python-headless) aborts the
# entire build.
ENV PIP_RETRIES=10 \
    PIP_TIMEOUT=60 \
    PIP_RESUME_RETRIES=5 \
    PIP_NO_CACHE_DIR=1

RUN echo "GITHUB_ACTIONS: $GITHUB_ACTIONS"

# Build-only system dependencies.
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

# Copy the entire requirements directory
COPY ./requirements ./requirements

RUN pip install --upgrade pip

# Build wheels for local requirements + pluggable pipeline extras.
# Excludes docs.txt and production.txt which are not needed for local/test
# builds and would add unnecessary packages that slow or break pip dependency
# resolution.
RUN pip wheel --wheel-dir /usr/src/app/wheels \
      -r ./requirements/local.txt \
      $(find ./requirements -mindepth 2 -type f -name "*.txt" -print | sed 's/^/-r /')

# ---------------------------------------------------------------------------- #
# Runtime stage: slim base, runtime libs only.                                 #
# ---------------------------------------------------------------------------- #
FROM python:${PYTHON_VERSION} AS python-run-stage

ARG BUILD_ENVIRONMENT=local
ARG APP_HOME=/app
ARG GITHUB_ACTIONS

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BUILD_ENV=${BUILD_ENVIRONMENT} \
    PIP_RETRIES=10 \
    PIP_TIMEOUT=60 \
    PIP_RESUME_RETRIES=5 \
    PIP_NO_CACHE_DIR=1

WORKDIR ${APP_HOME}

# Runtime system dependencies. Mirror production with the addition of `wget`
# (used below to fetch the large spaCy wheel with retry semantics). See the
# production Dockerfile for the rationale on each opencv-python-headless dep.
RUN apt-get update && apt-get install --no-install-recommends -y \
      libpq5 \
      gettext \
      git \
      wget \
      poppler-utils \
      tesseract-ocr \
      tesseract-ocr-eng \
      libgl1 \
      libglib2.0-0 \
      libgomp1 \
      libsm6 \
      libxext6 \
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies from prebuilt wheels.
COPY --from=python-build-stage /usr/src/app/wheels /wheels/
RUN pip install --upgrade pip \
    && pip install --no-index --find-links=/wheels/ /wheels/* \
    && rm -rf /wheels/

# Smoke test: `import cv2` must succeed (see production Dockerfile for context).
RUN python -c "import cv2; print(f'cv2 {cv2.__version__} import OK')"

# Download spacy models with retry logic and SHA-256 verification.
# Hashes are for the pinned 3.8.0 release wheels from the explosion/spacy-models
# GitHub releases page. Update hashes when bumping the model version.
RUN wget --retry-connrefused --waitretry=1 --read-timeout=20 --timeout=15 -t 5 \
      -O /tmp/en_core_web_sm-3.8.0-py3-none-any.whl \
      https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl \
    && echo "1932429db727d4bff3deed6b34cfc05df17794f4a52eeb26cf8928f7c1a0fb85  /tmp/en_core_web_sm-3.8.0-py3-none-any.whl" | sha256sum -c - \
    && pip install /tmp/en_core_web_sm-3.8.0-py3-none-any.whl \
    && rm /tmp/en_core_web_sm-3.8.0-py3-none-any.whl \
    && python -c "import spacy; spacy.load('en_core_web_sm')"

# For the large model, use wget with retry to ensure the download completes.
RUN wget --retry-connrefused --waitretry=1 --read-timeout=20 --timeout=15 -t 5 \
      -O /tmp/en_core_web_lg-3.8.0-py3-none-any.whl \
      https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.8.0/en_core_web_lg-3.8.0-py3-none-any.whl \
    && echo "293e9547a655b25499198ab15a525b05b9407a75f10255e405e8c3854329ab63  /tmp/en_core_web_lg-3.8.0-py3-none-any.whl" | sha256sum -c - \
    && pip install /tmp/en_core_web_lg-3.8.0-py3-none-any.whl \
    && rm /tmp/en_core_web_lg-3.8.0-py3-none-any.whl \
    && python -c "import spacy; spacy.load('en_core_web_lg')"

COPY ./compose/production/django/entrypoint /entrypoint
RUN sed -i 's/\r$//g' /entrypoint && chmod +x /entrypoint

COPY ./compose/local/django/run-migrations /run-migrations
RUN sed -i 's/\r$//g' /run-migrations && chmod +x /run-migrations

COPY ./compose/local/django/start /start
RUN sed -i 's/\r$//g' /start && chmod +x /start

COPY ./compose/local/django/start-with-coverage /start-with-coverage
RUN sed -i 's/\r$//g' /start-with-coverage && chmod +x /start-with-coverage

COPY ./compose/local/django/celery/worker/start /start-celeryworker
RUN sed -i 's/\r$//g' /start-celeryworker && chmod +x /start-celeryworker

COPY ./compose/local/django/celery/beat/start /start-celerybeat
RUN sed -i 's/\r$//g' /start-celerybeat && chmod +x /start-celerybeat

COPY ./compose/local/django/celery/flower/start /start-flower
RUN sed -i 's/\r$//g' /start-flower && chmod +x /start-flower

COPY ./setup_codecov.sh .
RUN echo "RUN STAGE GITHUB_ACTIONS: $GITHUB_ACTIONS" \
    && sed -i 's/\r$//' ./setup_codecov.sh \
    && if [ "$GITHUB_ACTIONS" = "true" ] ; then \
         echo "GITHUB ACTION MODE" \
         && apt-get update \
         && apt-get install -y curl \
         && chmod u+x setup_codecov.sh \
         && bash ./setup_codecov.sh \
         && ls -la /bin/codecov \
         && apt-get remove -y curl \
         && apt-get autoremove -y \
         && rm -rf /var/lib/apt/lists/* ; \
       else \
         echo "NOT GITHUB ACTION. DO NOT INSTALL CODECOV" ; \
       fi

# copy application code to WORKDIR
COPY . ${APP_HOME}

ENTRYPOINT ["/entrypoint"]
