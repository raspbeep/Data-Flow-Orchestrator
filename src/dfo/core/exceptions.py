"""Custom exception hierarchy for DFO."""


class DFOError(Exception):
    """Base exception for all DFO errors."""


class ValidationError(DFOError):
    """Raised when configuration is invalid."""


class ExecutionError(DFOError):
    """Raised during flow execution."""


class PluginError(DFOError):
    """Raised when a plugin fails."""


class CycleError(ValidationError):
    """Raised when a dependency graph contains a cycle."""


"""Custom interpolation exceptions"""


class InterpolationError(ValueError):
    """Base class for all interpolation failures."""


class UnknownReferenceError(InterpolationError):
    """A placeholder points to a path that does not exist."""


class InterpolationCycleError(InterpolationError):
    """Two or more references depend on each other cyclically."""


class InterpolationSyntaxError(InterpolationError):
    """A string contains malformed interpolation syntax."""


class InterpolationTypeError(InterpolationError):
    """A referenced value cannot be embedded into a larger string."""
