class ReportNotFoundError(Exception):
    """No Report exists for this id within the caller's tenant/evaluation scope."""


class InvalidReportFormatError(Exception):
    """The requested (report_type, format) pair is not in VALID_FORMATS_BY_TYPE."""


class ReportNotReadyError(Exception):
    """The evaluation/decision is not yet in a state this report_type can be
    generated from (readiness precondition failed) - carries a human-readable
    reason."""


class ReportNotSucceededError(Exception):
    """A download URL was requested for a Report whose status is not yet
    "succeeded" (still queued/running, or it failed)."""


class RequirementsImportError(Exception):
    """The uploaded file could not be parsed as a valid Excel/CSV requirements
    import (wrong extension, empty file, unreadable content, or a mapping
    that does not resolve every required column)."""
