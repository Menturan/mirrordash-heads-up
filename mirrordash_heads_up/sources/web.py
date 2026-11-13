import hmac
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException


def make_router(module) -> APIRouter:
    """POST <api_path>/show. Anyone on the home network can call it: with a Token set the call must carry it
    (header X-Token or query ?token=), with none set it is open."""
    router = APIRouter()

    @router.post("/show")
    async def show(body: dict | None = None, text: str = "", seconds: int | None = None, token: str = "",
                   x_token: Annotated[str, Header()] = ""):
        """{"text": "...", "seconds": 3-120 (optional)}, or ?text=...&seconds=...: the text goes in the queue."""
        if module.token and not hmac.compare_digest((x_token or token).encode(), module.token.encode()):
            raise HTTPException(status_code=403)
        body = body or {}
        body_text = body.get("text")
        text = text or (body_text if isinstance(body_text, str) else "")
        if not module.push(text, seconds if seconds is not None else body.get("seconds")):
            raise HTTPException(status_code=422, detail="text is required")
        return {"ok": True, "waiting": len(module.waiting)}

    return router
