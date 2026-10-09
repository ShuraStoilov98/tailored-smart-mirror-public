"""Errors safe for the HTTP layer to classify without leaking provider details."""


class InvalidImage(ValueError):
    """Invalid or oversized uploaded image."""


class InvalidReview(ValueError):
    """Provider output violates the review contract."""


class MirrorBusy(RuntimeError):
    """The single-device controller already has an active operation."""


class MirrorUnavailable(RuntimeError):
    """The mirror lacks configuration or has been shut down."""
