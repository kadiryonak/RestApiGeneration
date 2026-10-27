"""Exception hierarchy. Every error raised on purpose by restgen derives from RestgenError."""


class RestgenError(Exception):
    """Base class for all restgen errors."""


class ConfigError(RestgenError):
    """The configuration or a manifest is missing, malformed or inconsistent."""


class BenchmarkError(RestgenError):
    """A benchmark suite or service cannot be fetched, installed, started or verified."""


class SpecError(RestgenError):
    """An OpenAPI document cannot be loaded or interpreted."""


class MeasurementError(RestgenError):
    """A measurement artefact (coverage, traffic, test report) is missing or unreadable."""


class ToolError(RestgenError):
    """A comparison tool could not be set up or run."""


class UnresolvedReferenceError(RestgenError):
    """A value refers to a response, or a field in it, that does not exist."""
