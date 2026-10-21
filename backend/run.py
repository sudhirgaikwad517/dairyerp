import os
import sys

import uvicorn

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

if __name__ == "__main__":
    # One worker only: the automatic dispatcher and the email sender run inside the server process.
    # DAIRY_DEV=1 turns on auto-reload while developing.
    uvicorn.run(
        "backend.app.main:app",
        host=os.environ.get("DAIRY_HOST", "0.0.0.0"),
        port=int(os.environ.get("DAIRY_PORT", "8000")),
        reload=os.environ.get("DAIRY_DEV") == "1",
        proxy_headers=True,
        forwarded_allow_ips=os.environ.get("DAIRY_TRUSTED_PROXIES", "127.0.0.1"),
    )
