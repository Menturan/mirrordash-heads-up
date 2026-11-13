import asyncio
import logging

logger = logging.getLogger("mirrordash.modules.mirrordash_heads_up")
RESTART_AFTER = 30  # seconds


async def keep_going(name: str, make_loop):
    """Runs a source's loop for as long as the module runs. A source that fails is logged and started again, so it
    never takes the card down with it; the mirror stopping the module cancels this (CancelledError isn't an Exception)."""
    while True:
        try:
            await make_loop()
        except Exception:
            logger.exception("The %s source failed; starting it again in %s s", name, RESTART_AFTER)
            await asyncio.sleep(RESTART_AFTER)
