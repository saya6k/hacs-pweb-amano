"""Exceptions for the PWEB Amano integration."""


class PwebAmanoError(Exception):
    """Base exception for PWEB Amano."""


class PwebAmanoAuthError(PwebAmanoError):
    """Login was rejected by the portal."""


class PwebAmanoConnectionError(PwebAmanoError):
    """The portal could not be reached."""


class PwebAmanoRegistrationError(PwebAmanoError):
    """A discount registration request was rejected or the vehicle wasn't found."""
