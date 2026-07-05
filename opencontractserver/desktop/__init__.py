"""Single-user desktop packaging for OpenContracts.

This package turns the docker-compose topology (django, postgres, redis,
celeryworker, celerybeat, the ML microservices and the frontend container) into
a single supervised Python process suitable for a cross-platform desktop app.

See ``docs/deployment/desktop_packaging.md`` for the architecture and the phased
delivery plan. Nothing here is imported by the server/compose deployment; it is
only loaded when ``DJANGO_SETTINGS_MODULE=config.settings.desktop`` (or the
``oc-desktop`` launcher) is used.
"""
