"""Production entrypoint for SentinelIQ.

Usage:
    python run.py

The CV engine is a process-global singleton (stream thread + Telegram polling),
so the server MUST run as a single uvicorn worker. Front it with a reverse proxy
(NGINX/Caddy) for TLS and set TRUSTED_PROXY=1 - do not scale workers.
"""

import uvicorn

import config

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=config.HOST,
        port=config.PORT,
        log_level=config.LOG_LEVEL,
        workers=1,
        proxy_headers=config.TRUSTED_PROXY,
        forwarded_allow_ips="*" if config.TRUSTED_PROXY else None,
    )