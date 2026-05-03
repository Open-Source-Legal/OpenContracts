ARG PYTHON_VERSION=3.11-slim-bookworm

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
#   gettext            : Django translations (compilemessages)
#   poppler-utils      : pdf2image (pdftoppm/pdftocairo)
#   tesseract-ocr*     : pytesseract OCR runtime
#   libgl1, libsm6,    : opencv-python-headless transitive runtime deps
#   libxext6,            (libGL, libSM, libXext, gthread-2.0, libgomp).
#   libglib2.0-0,        On slim-bookworm none of these are present in the
#   libgomp1             base; without them `import cv2` raises ImportError.
RUN apt-get update && apt-get install --no-install-recommends -y \
      libpq5 \
      gettext \
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

# Spacy models used by TxtParser sentence chunker.
RUN python -m spacy download en_core_web_sm \
    && python -m spacy download en_core_web_lg

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
