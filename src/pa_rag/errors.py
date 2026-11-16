class AuthenticationError(Exception):
    """The caller's identity could not be verified."""


class AccessViolation(Exception):
    """A forbidden item reached a place it must never reach.

    Raised by defense-in-depth checks. If this ever fires, the pre-filter has a bug:
    fail the request instead of handing the content to the model.
    """
