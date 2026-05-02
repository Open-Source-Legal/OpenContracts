import logging

from django.conf import settings
from django.test.signals import setting_changed
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)

DEFAULTS = {
    "AUTH0_TOKEN_ALGORITHM": "RS256",
    "AUTH0_DECODE_HANDLER": "config.graphql_auth0_auth.utils.jwt_auth0_decode",
    "AUTH0_GET_USER_FROM_TOKEN_HANDLER": "config.graphql_auth0_auth.utils.get_auth0_user_from_token",
    "AUTH0_CREATE_NEW_USERS": True,
    "AUTH0_CLIENT_ID": settings.AUTH0_CLIENT_ID,
    "AUTH0_API_AUDIENCE": settings.AUTH0_API_AUDIENCE,
    "AUTH0_DOMAIN": settings.AUTH0_DOMAIN,
    "AUTH0_M2M_MANAGEMENT_API_SECRET": settings.AUTH0_M2M_MANAGEMENT_API_SECRET,
    "AUTH0_M2M_MANAGEMENT_API_ID": settings.AUTH0_M2M_MANAGEMENT_API_ID,
    "AUTH0_M2M_MANAGEMENT_GRANT_TYPE": settings.AUTH0_M2M_MANAGEMENT_GRANT_TYPE,
}

logger.debug(
    "Auth0 settings initialized with domain: [REDACTED], client ID: [REDACTED]"
)
logger.debug(f"AUTH0_CREATE_NEW_USERS set to: {DEFAULTS['AUTH0_CREATE_NEW_USERS']}")
logger.debug("AUTH0_GET_USER_FROM_TOKEN_HANDLER configured")

IMPORT_STRINGS = (
    "AUTH0_DECODE_HANDLER",
    "AUTH0_PAYLOAD_HANDLER",
    "AUTH0_PAYLOAD_GET_USERNAME_HANDLER",
    "AUTH0_GET_USER_FROM_TOKEN_HANDLER",
    "AUTH0_GET_USER_FROM_TOKEN",
)


def perform_import(value, setting_name):
    logger.debug(f"perform_import() - Importing {value} for setting {setting_name}")
    if isinstance(value, str):
        result = import_from_string(value, setting_name)
        logger.debug(f"perform_import() - Imported {value} as {result}")
        return result
    if isinstance(value, (list, tuple)):
        logger.debug(f"perform_import() - Importing list of {len(value)} items")
        return [import_from_string(item, setting_name) for item in value]
    return value


def import_from_string(value, setting_name):
    logger.debug(f"import_from_string() - Importing {value} for {setting_name}")
    try:
        result = import_string(value)
        logger.debug(f"import_from_string() - Successfully imported {value}")
        return result
    except ImportError as e:
        msg = (
            f"Could not import `{value}` for JWT setting `{setting_name}`."
            f"{e.__class__.__name__}: {e}."
        )
        logger.error(f"import_from_string() - {msg}")
        raise ImportError(msg)


class Auth0JWTSettings:
    def __init__(self, defaults, import_strings):
        self.defaults = defaults
        self.import_strings = import_strings
        self._cached_attrs = set()
        logger.debug(
            f"Auth0JWTSettings initialized with {len(defaults)} defaults and {len(import_strings)} import_strings"
        )

    def __getattr__(self, attr):
        # Dunder / private names are probed by Python internals (deepcopy,
        # pickle, hasattr, IPython tab-completion, etc.).  Treat them as
        # ordinary missing attributes so we don't spam the error log.
        if attr.startswith("_"):
            raise AttributeError(attr)

        logger.debug(f"Auth0JWTSettings.__getattr__() - Accessing setting: {attr}")
        if attr not in self.defaults:
            logger.error(
                f"Auth0JWTSettings.__getattr__() - Invalid setting requested: {attr}"
            )
            raise AttributeError(f"Invalid setting: `{attr}`")

        value = self.user_settings.get(attr, self.defaults[attr])
        logger.debug(f"Auth0JWTSettings.__getattr__() - Value for {attr}: {value}")

        if attr in self.import_strings:
            logger.debug(
                f"Auth0JWTSettings.__getattr__() - Importing string for {attr}"
            )
            value = perform_import(value, attr)

        self._cached_attrs.add(attr)
        setattr(self, attr, value)
        return value

    @property
    def user_settings(self):
        if not hasattr(self, "_user_settings"):
            logger.debug(
                "Auth0JWTSettings.user_settings - Initializing user settings from Django settings"
            )
            self._user_settings = getattr(settings, "AUTH0_JWT", {})
            logger.debug(
                f"Auth0JWTSettings.user_settings - Retrieved {len(self._user_settings)} user settings"
            )
        return self._user_settings

    def reload(self):
        logger.debug(
            f"Auth0JWTSettings.reload() - Reloading {len(self._cached_attrs)} cached attributes"
        )
        for attr in self._cached_attrs:
            logger.debug(
                f"Auth0JWTSettings.reload() - Deleting cached attribute: {attr}"
            )
            delattr(self, attr)

        self._cached_attrs.clear()

        if hasattr(self, "_user_settings"):
            logger.debug("Auth0JWTSettings.reload() - Deleting cached user settings")
            delattr(self, "_user_settings")


def reload_settings(*args, **kwargs):
    setting = kwargs["setting"]
    logger.debug(f"reload_settings() - Setting changed: {setting}")

    if setting == "AUTH0_JWT":
        logger.debug("reload_settings() - Reloading auth0_settings")
        auth0_settings.reload()


setting_changed.connect(reload_settings)

auth0_settings = Auth0JWTSettings(DEFAULTS, IMPORT_STRINGS)
logger.debug("Auth0 settings module fully initialized")
