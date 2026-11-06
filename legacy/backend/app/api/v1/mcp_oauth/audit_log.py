"""Keep the MCP OAuth INFO audit entries under `fastapi run` and `fastapi dev`.

Their log configuration covers only the uvicorn loggers and leaves the root
logger at WARNING without a handler, which would silently drop the client
registration and grant revocation entries that ADR-015 requires. A
configuration that also gives the root logger a handler prints these entries
twice, because they still propagate.
"""

import logging

MCP_OAUTH_LOGGER_NAME = "app.api.v1.mcp_oauth"
AUDIT_HANDLER = logging.StreamHandler()
AUDIT_HANDLER.setFormatter(
    logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
)


def install_mcp_oauth_audit_log() -> None:
    """Emit MCP OAuth entries at INFO to standard error; idempotent.

    The entries still propagate, so a root handler (such as pytest's log
    capture) receives them too.
    """
    logger = logging.getLogger(MCP_OAUTH_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    if AUDIT_HANDLER not in logger.handlers:
        logger.addHandler(AUDIT_HANDLER)
