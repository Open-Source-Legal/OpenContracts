ARG PYTORCH_VERSION=2.7.1-cuda12.6-cudnn9-runtime

# define an alias for the specific pytorch version used in this file.
FROM pytorch/pytorch:${PYTORCH_VERSION} as python

# Python build stage
FROM python as python-build-stage

ARG BUILD_ENVIRONMENT=local
ARG GITHUB_ACTIONS

# Debugging line for build args
RUN echo "GITHUB_ACTIONS: $GITHUB_ACTIONS"

# Install apt packages
RUN apt-get update && apt-get install --no-install-recommends -y \
  # dependencies for building Python packages
  apt-utils \
  wget \
  build-essential \
  cmake \
  automake \
  libfreetype6-dev \
  pkg-config \
  libfontconfig-dev \
  libjpeg-dev \
  libopenjp2-7-dev \
  libcairo2-dev \
  libtiff5-dev \
  tesseract-ocr \
  libtesseract-dev \
  git \
  # psycopg2 dependencies
  libpq-dev

# Copy the entire requirements directory
COPY ./requirements ./requirements

RUN pip install --upgrade pip

# Build wheels for local requirements + pluggable pipeline extras.
# Excludes docs.txt and production.txt which are not needed for local/test builds
# and would add unnecessary packages that slow or break pip dependency resolution.
RUN pip wheel --wheel-dir /usr/src/app/wheels \
  -r ./requirements/local.txt \
  $(find ./requirements -mindepth 2 -type f -name "*.txt" -print | sed 's/^/-r /')

# Python 'run' stage
FROM python as python-run-stage

ARG BUILD_ENVIRONMENT=local
ARG APP_HOME=/app
ARG GITHUB_ACTIONS

ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1
ENV BUILD_ENV ${BUILD_ENVIRONMENT}

# CUDA-specific environment variables for optimal performance
ENV CUDA_MODULE_LOADING=LAZY
ENV TORCH_CUDA_ARCH_LIST="6.0;6.1;7.0;7.5;8.0;8.6;8.9;9.0"
ENV CUDA_VISIBLE_DEVICES=0
ENV PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512

WORKDIR ${APP_HOME}

# Install required system dependencies
RUN apt-get update && apt-get install --no-install-recommends -y \
  # psycopg2 dependencies
  libpq-dev \
  # Translations dependencies
  gettext \
  git \
  wget \
  poppler-utils \
  tesseract-ocr \
  libtesseract-dev  \
  ffmpeg \
  libsm6 \
  libxext6 \
  tesseract-ocr-eng \
  # cleaning up unused files
  && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
  && rm -rf /var/lib/apt/lists/*

# All absolute dir copies ignore workdir instruction. All relative dir copies are wrt to the workdir instruction
# copy python dependency wheels from python-build-stage
COPY --from=python-build-stage /usr/src/app/wheels  /wheels/

RUN pip install --upgrade pip

# use wheels to install python dependencies first
RUN pip install --no-cache-dir --no-index --find-links=/wheels/ /wheels/* \
	&& rm -rf /wheels/

# Download spacy models with retry logic and direct pip installation
# Using pip directly is more reliable than spacy download command in Docker
RUN pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl && \
    python -c "import spacy; spacy.load('en_core_web_sm')"

# For the large model, we'll use wget with retry to ensure download completes
RUN wget --retry-connrefused --waitretry=1 --read-timeout=20 --timeout=15 -t 5 \
    https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.8.0/en_core_web_lg-3.8.0-py3-none-any.whl && \
    pip install en_core_web_lg-3.8.0-py3-none-any.whl && \
    rm en_core_web_lg-3.8.0-py3-none-any.whl && \
    python -c "import spacy; spacy.load('en_core_web_lg')"

COPY ./compose/production/django/entrypoint /entrypoint
RUN sed -i 's/\r$//g' /entrypoint
RUN chmod +x /entrypoint

COPY ./compose/local/django/start /start
RUN sed -i 's/\r$//g' /start
RUN chmod +x /start

COPY ./compose/local/django/celery/worker/start /start-celeryworker
RUN sed -i 's/\r$//g' /start-celeryworker
RUN chmod +x /start-celeryworker

COPY ./compose/local/django/celery/beat/start /start-celerybeat
RUN sed -i 's/\r$//g' /start-celerybeat
RUN chmod +x /start-celerybeat

COPY ./compose/local/django/celery/flower/start /start-flower
RUN sed -i 's/\r$//g' /start-flower
RUN chmod +x /start-flower

# Update the environment variable check, after all stages
COPY ./setup_codecov.sh .
RUN echo "RUN STAGE GITHUB_ACTIONS: $GITHUB_ACTIONS" && \
    sed -i 's/\r$//' ./setup_codecov.sh && \
    if [ "$GITHUB_ACTIONS" = "true" ] ; then \
        echo "GITHUB ACTION MODE" && \
        apt-get update && \
        apt-get install -y curl && \
        chmod u+x setup_codecov.sh && \
        bash ./setup_codecov.sh && \
        ls -la /bin/codecov && \
        apt-get remove -y curl && \
        apt-get autoremove -y && \
        rm -rf /var/lib/apt/lists/* ; \
    else \
        echo "NOT GITHUB ACTION. DO NOT INSTALL CODECOV" ; \
    fi

# copy application code to WORKDIR
COPY . ${APP_HOME}

# Clean up pip cache
RUN pip cache purge

ENTRYPOINT ["/entrypoint"]
