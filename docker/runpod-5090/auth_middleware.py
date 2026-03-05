import os
from starlette.responses import JSONResponse


class BearerAuthMiddleware:
    """Pure ASGI middleware — no response buffering, safe for StreamingResponse."""

    def __init__(self, app):
        self.app = app
        self.token = os.environ.get("AUTH_TOKEN", "")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self.token:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        auth = headers.get(b"authorization", b"").decode()

        if auth != f"Bearer {self.token}":
            response = JSONResponse(
                status_code=401, content={"error": "Unauthorized"}
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
