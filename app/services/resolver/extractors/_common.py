from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def duration_seconds_parse(value: Any) -> int | None:
    """Shared duration parsing for all extractors."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if isinstance(value, str):
        try:
            return max(0, int(float(value.strip())))
        except ValueError:
            return None
    return None


def normalize_upload_date(info: dict[str, Any]) -> str | None:
    """Parse upload_date (YYYYMMDD) or timestamp (Unix seconds) from yt-dlp info to ISO date YYYY-MM-DD."""
    # Prefer timestamp for precision; convert to date in UTC
    ts = info.get("timestamp") or info.get("upload_date_timestamp")
    if ts is not None and isinstance(ts, (int, float)):
        try:
            dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, OSError):
            pass
    # Fallback: upload_date as YYYYMMDD string
    ud = info.get("upload_date")
    if isinstance(ud, str) and len(ud) == 8 and ud.isdigit():
        try:
            y, m, d = int(ud[:4]), int(ud[4:6]), int(ud[6:8])
            if 1 <= m <= 12 and 1 <= d <= 31:
                return f"{y:04d}-{m:02d}-{d:02d}"
        except (ValueError, TypeError):
            pass
    return None
