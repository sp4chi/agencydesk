"""Errors that services raise. Services know nothing about HTTP; main.py
maps each class to a status code in one place.

Messages must be safe to show the caller: never echo another tenant's data.
"""


class ServiceError(Exception):
    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class Invalid(ServiceError):
    """The request is well-formed but breaks a business rule."""
    status_code = 422


class NotAuthenticated(ServiceError):
    status_code = 401


class Forbidden(ServiceError):
    """The caller can see the thing but their role may not do this."""
    status_code = 403


class NotFound(ServiceError):
    """Doesn't exist, or the caller can't see it. Same answer for both."""
    status_code = 404

    def __init__(self, message: str = "Not found") -> None:
        super().__init__(message)


class Conflict(ServiceError):
    status_code = 409


# Postgres error codes services translate into the errors above.
FOREIGN_KEY_VIOLATION = "23503"
UNIQUE_VIOLATION = "23505"


def sqlstate(exc: Exception) -> str | None:
    """The Postgres error code behind a SQLAlchemy DBAPIError, if any."""
    return getattr(getattr(exc, "orig", None), "sqlstate", None)
