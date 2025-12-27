"""
ASGI config for OpenContracts project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/dev/howto/deployment/asgi/

"""

import os  # noqa: E402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

import django  # noqa: E402

django.setup()

import logging  # noqa: E402
import sys  # noqa: E402
import uuid  # noqa: E402
from pathlib import Path  # noqa: E402

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from django.conf import settings  # noqa: E402
from django.core.asgi import get_asgi_application  # noqa: E402
from django.urls import re_path  # noqa: E402

from config.websocket.consumers.corpus_conversation import (  # noqa: E402
    CorpusQueryConsumer,
)
from config.websocket.consumers.document_conversation import (  # noqa: E402
    DocumentQueryConsumer,
)
from config.websocket.consumers.standalone_document_conversation import (  # noqa: E402
    StandaloneDocumentQueryConsumer,
)
from config.websocket.consumers.thread_updates import (  # noqa: E402
    ThreadUpdatesConsumer,
)
from config.websocket.consumers.unified_agent_conversation import (  # noqa: E402
    UnifiedAgentConsumer,
)
from config.websocket.middlewares.ratelimit_middleware import (  # noqa: E402
    RateLimitMiddleware,
)
from opencontractserver.mcp.server import mcp_asgi_app  # noqa: E402

logger = logging.getLogger(__name__)

# This allows easy placement of apps within the interior
# delphic directory.
BASE_DIR = Path(__file__).resolve(strict=True).parent.parent
sys.path.append(str(BASE_DIR / "delphic"))

# This application object is used by any ASGI server configured to use this file.
django_application = get_asgi_application()


def create_http_router(django_app, mcp_app):
    """
    Create an HTTP router that dispatches to MCP or Django based on path.

    Routes /mcp and /mcp/* to the MCP ASGI app, everything else to Django.
    The MCP server uses Streamable HTTP transport in stateless mode.
    """

    async def router(scope, receive, send):
        path = scope.get("path", "")
        # Match /mcp exactly or /mcp/* paths
        if path == "/mcp" or path.startswith("/mcp/"):
            await mcp_app(scope, receive, send)
        else:
            await django_app(scope, receive, send)

    return router


http_application = create_http_router(django_application, mcp_asgi_app)

document_query_pattern = re_path(
    r"ws/document/(?P<document_id>[-a-zA-Z0-9_=]+)/query/(?:corpus/(?P<corpus_id>[-a-zA-Z0-9_=]+)/)?$",
    DocumentQueryConsumer.as_asgi(),
)

corpus_query_pattern = re_path(
    r"ws/corpus/(?P<corpus_id>[-a-zA-Z0-9_=]+)/query/$",
    CorpusQueryConsumer.as_asgi(),
)

# NEW - stand-alone document chat (no corpus_id in URL)
standalone_document_query_pattern = re_path(
    r"ws/standalone/document/(?P<document_id>[-a-zA-Z0-9_=]+)/query/$",
    StandaloneDocumentQueryConsumer.as_asgi(),
)

# NEW - unified agent consumer (query params for context)
# Supports: ?corpus_id=X, ?document_id=X, ?agent_id=X, ?conversation_id=X
unified_agent_query_pattern = re_path(
    r"ws/agent-chat/$",
    UnifiedAgentConsumer.as_asgi(),
)

# NEW - thread updates consumer for agent mention responses
# Supports: ?conversation_id=X (required)
thread_updates_pattern = re_path(
    r"ws/thread-updates/$",
    ThreadUpdatesConsumer.as_asgi(),
)

websocket_urlpatterns = [
    # NEW: Unified agent consumer (preferred for new integrations)
    unified_agent_query_pattern,
    # NEW: Thread updates consumer for agent mention streaming
    thread_updates_pattern,
    # Legacy routes (kept for backwards compatibility)
    document_query_pattern,
    corpus_query_pattern,
    standalone_document_query_pattern,
]

# Log all registered websocket patterns
for pattern in websocket_urlpatterns:
    logger.info(f"Registered WebSocket URL pattern: {pattern.pattern}")

# Choose the appropriate middleware based on USE_AUTH0
if settings.USE_AUTH0:
    logger.info("USE_AUTH0 set to True, using WebsocketAuth0TokenMiddleware")
    from config.websocket.middlewares.websocket_auth0_middleware import (
        WebsocketAuth0TokenMiddleware,  # type: ignore
    )

    websocket_auth_middleware = WebsocketAuth0TokenMiddleware
else:
    logger.info("USE_AUTH0 set to False, using GraphQLJWTTokenAuthMiddleware")
    from config.websocket.middleware import GraphQLJWTTokenAuthMiddleware

    websocket_auth_middleware = GraphQLJWTTokenAuthMiddleware


# Create the ASGI application with proper middleware order
# 1. Protocol routing
# 2. Auth middleware (determined above)
# 3. Rate limit middleware (checks connection rate limits)
# 4. URL routing
application = ProtocolTypeRouter(
    {
        "http": http_application,  # Routes /mcp/* to MCP, rest to Django
        "websocket": websocket_auth_middleware(
            RateLimitMiddleware(URLRouter(websocket_urlpatterns))
        ),
    }
)

logger.info("ASGI application configured with WebSocket support")

unique_id = uuid.uuid4()
logger.info(f"ASGI.py loaded (unique_id={unique_id})")
