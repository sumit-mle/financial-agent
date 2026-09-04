"""
Structured logging setup using structlog.
Outputs JSON in production, pretty console output in development.
"""
import logging
import sys

import structlog
from structlog.types import EventDict, Processor

from app.core.config import settings


def _add_app_context(
    logger: logging.Logger, method: str, event_dict: EventDict
) -> EventDict:
    """Inject app-level metadata into every log record."""
    event_dict["app"] = settings.app_name
    event_dict["env"] = settings.app_env
    return event_dict


def configure_logging() -> None:
    """Configure structlog — call once at application startup."""
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_app_context,
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.is_production:
        # JSON output for log aggregation (Datadog, CloudWatch, etc.)
        processors: list[Processor] = [
            *shared_processors,
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Pretty console output for development
        processors = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging to route through structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=settings.log_level.upper(),
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a named structured logger."""
    return structlog.get_logger(name)
