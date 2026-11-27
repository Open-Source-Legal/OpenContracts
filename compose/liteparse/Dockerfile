# OpenContracts LiteParse service: LiteParse (Apache-2.0) with LlamaIndex's
# OCRia-nano OCR/layout models. Optional; built locally behind the "liteparse"
# compose profile and never published, because the model weights carry their
# own licence (OCRIA_NANO_LICENSE_NOTICE.txt). See docs/pipelines/liteparse_parser.md.
#
#   docker build --build-arg OCRIA_NANO_ACCEPT_LICENSE=yes -t opencontractserver_local_liteparse compose/liteparse
FROM python:3.12-slim

ARG OCRIA_NANO_ACCEPT_LICENSE=""

# LITEPARSE_MODEL_DIR pins where `models.pull` installs and where LiteParse
# looks at runtime, independent of $HOME / the runtime user.
ENV LITEPARSE_MODEL_DIR=/opt/liteparse/models \
    OCRIA_NANO_MODEL_VERSION=1.0.0 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY requirements.txt OCRIA_NANO_LICENSE_NOTICE.txt /opt/liteparse/

# Licence gate: runs before the weights are downloaded.
RUN if [ "${OCRIA_NANO_ACCEPT_LICENSE}" != "yes" ]; then \
      cat /opt/liteparse/OCRIA_NANO_LICENSE_NOTICE.txt >&2; \
      echo "Build refused: OCRIA_NANO_ACCEPT_LICENSE is not 'yes'." >&2; \
      exit 1; \
    fi

RUN pip install -r /opt/liteparse/requirements.txt

RUN python -c "import os; from liteparse import models; models.pull('ocria-nano@' + os.environ['OCRIA_NANO_MODEL_VERSION'])" \
    && chmod -R a+rX /opt/liteparse

COPY liteparse_service/ /srv/liteparse_service/

RUN useradd --system --uid 10001 --no-create-home liteparse
USER liteparse

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
  CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=4).status == 200 else 1)"]

CMD ["uvicorn", "--factory", "liteparse_service.app:build_app", "--host", "0.0.0.0", "--port", "8000"]
