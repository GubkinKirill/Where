class ServiceError(Exception):
    """Domain error with a message meant to be shown to the user as is."""


class MoveError(ServiceError):
    pass


class DirectoryError(ServiceError):
    pass


class LocationWriteError(RuntimeError):
    """Raised when item placement is changed outside of the movement service.

    Not a user-facing error: it means the code bypassed the movement log.
    """
