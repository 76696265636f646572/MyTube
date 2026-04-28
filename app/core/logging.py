import logging
import sys


# ANSI escape codes for coloring
_COLORS = {
    logging.DEBUG: "\033[36m",    # cyan
    logging.INFO: "\033[92m",     # bright green
    logging.WARNING: "\033[33m",  # yellow/orange
    logging.ERROR: "\033[91m",    # red
    logging.CRITICAL: "\033[91;1m",  # bright red
}
_RESET = "\033[0m"


class ColoredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        color = _COLORS.get(record.levelno, _RESET)
        record.levelname = f"{color}{record.levelname}{_RESET}"
        return super().format(record)


def configure_logging(level: str = "INFO") -> None:
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ColoredFormatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    root = logging.getLogger()
    root.setLevel(numeric_level)
    root.handlers.clear()
    root.addHandler(handler)

    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
    logging.getLogger("soco.services").setLevel(logging.WARNING)
    logging.getLogger("soco.zonegroupstate").setLevel(logging.WARNING)
    logging.getLogger("soco.discovery").setLevel(logging.WARNING)
    logging.getLogger("httpcore.http11").setLevel(logging.WARNING)