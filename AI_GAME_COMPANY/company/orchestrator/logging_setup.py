"""Logging with secret redaction (master prompt sections 3, 38).

Auth tokens must never reach a log file, so every record passes through
`redact()` before it is written.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from . import paths

# Anything that looks like a key/token value gets masked. Order matters:
# longer, more specific patterns first.
_REDACT_PATTERNS = [
    re.compile(r"(sk-[A-Za-z0-9_\-]{8,})"),
    re.compile(r"(gh[pousr]_[A-Za-z0-9]{8,})"),
    re.compile(r"(ya29\.[A-Za-z0-9_\-]{8,})"),
    re.compile(r"((?:api[_-]?key|token|secret|password|authorization)\s*[=:]\s*)([^\s,;\"']{6,})",
               re.IGNORECASE),
    re.compile(r"(\"access_token\"\s*:\s*\")([^\"]+)"),
]

_ENV_SECRET_HINT = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD)$", re.IGNORECASE)


def _env_secret_values() -> list[str]:
    out = []
    for name, value in os.environ.items():
        if _ENV_SECRET_HINT.search(name) and value and len(value) >= 8:
            out.append(value)
    return out


def redact(text: str) -> str:
    if not text:
        return text
    for value in _env_secret_values():
        text = text.replace(value, "***REDACTED_ENV***")
    for pattern in _REDACT_PATTERNS:
        if pattern.groups == 1:
            text = pattern.sub("***REDACTED***", text)
        else:
            text = pattern.sub(lambda m: m.group(1) + "***REDACTED***", text)
    return text


class _RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def log_dir_for_today() -> Path:
    d = paths.LOGS_DIR / datetime.now(timezone.utc).strftime("%Y-%m-%d")
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_logger(name: str, *, quiet: bool = False) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    fmt = _RedactingFormatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s")

    log_path = log_dir_for_today() / f"{name.replace('.', '_')}.log"
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    if not quiet:
        sh = logging.StreamHandler()
        sh.setLevel(logging.INFO)
        sh.setFormatter(fmt)
        logger.addHandler(sh)

    logger.propagate = False
    return logger


def write_log_file(name: str, content: str) -> Path:
    """Persist raw tool output (build logs, CLI output) with redaction."""
    stamp = datetime.now(timezone.utc).strftime("%H%M%S")
    path = log_dir_for_today() / f"{name}_{stamp}.log"
    path.write_text(redact(content), encoding="utf-8")
    return path
