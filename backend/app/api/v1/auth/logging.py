import logging
import re

_SENSITIVE_QUERY_VALUE = re.compile(
    r"(?i)(?P<prefix>(?:^|[?&])(?:code|state|error|error_description)=)[^&\s]*"
)


class SensitiveQueryFilter(logging.Filter):
    """Redact callback secrets from Uvicorn-style access-log arguments."""

    def filter(self, record: logging.LogRecord) -> bool:
        arguments = record.args
        if isinstance(arguments, tuple) and len(arguments) >= 3:
            path = arguments[2]
            if isinstance(path, str):
                if path.startswith("/api/v1/auth/callback?"):
                    redacted = path.split("?", 1)[0]
                else:
                    redacted = _SENSITIVE_QUERY_VALUE.sub(
                        lambda match: f"{match.group('prefix')}REDACTED",
                        path,
                    )
                if redacted != path:
                    record.args = (*arguments[:2], redacted, *arguments[3:])
        return True


def install_sensitive_query_filter() -> None:
    logger = logging.getLogger("uvicorn.access")
    if any(isinstance(item, SensitiveQueryFilter) for item in logger.filters):
        return
    logger.addFilter(SensitiveQueryFilter())
