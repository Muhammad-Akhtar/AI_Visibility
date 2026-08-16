"""Cross-platform server entrypoint.

Gunicorn imports the Unix-only `fcntl` module, so it cannot start on Windows.
This script uses Waitress on Windows and Gunicorn on Linux/macOS (and Docker).
"""

from __future__ import annotations

import os
import sys


def main() -> None:
    os.environ.setdefault("FLASK_APP", "app")

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))

    print(f"Serving AI Visibility API on http://{host}:{port}")
    if os.name == "nt":
        from waitress import serve

        from wsgi import app

        serve(app, host=host, port=port, channel_timeout=120)
        return

    os.execvp(
        "gunicorn",
        [
            "gunicorn",
            "-b",
            f"{host}:{port}",
            "--timeout",
            "120",
            "--workers",
            "2",
            "wsgi:app",
        ],
    )


if __name__ == "__main__":
    main()
