"""Explicit public codes for domain exceptions exposed by APIs."""


class PublicError(ValueError):
    """Keep exception details internal while exposing an allowlisted code."""

    public_codes: frozenset[str] = frozenset()
    default_code = "invalid_request"

    @property
    def public_code(self) -> str:
        message = str(self)
        for code in self.public_codes:
            if message == code:
                # Return the trusted constant, never the exception text itself.
                return code
        return self.default_code
