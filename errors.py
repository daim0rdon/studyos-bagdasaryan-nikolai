"""User-friendly errors raised by the simulated operating system."""


class StudyOSError(Exception):
    """Base class for recoverable StudyOS errors."""


class AccessDenied(StudyOSError):
    """The current user is not allowed to perform the operation."""


class AlreadyExists(StudyOSError):
    """A file, directory, or user already exists."""


class NotFound(StudyOSError):
    """A requested object does not exist."""


class InvalidOperation(StudyOSError):
    """The supplied operation or its arguments are invalid."""


class InsufficientMemory(StudyOSError):
    """The simulated memory limit would be exceeded."""
