from __future__ import annotations

import asyncio

from fastapi.responses import StreamingResponse


class GracefulStreamingResponse(StreamingResponse):
    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        except asyncio.CancelledError:
            # A cancelled stream task is expected during client disconnect
            # or server shutdown.
            return
