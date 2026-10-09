"""Launch the single-process, loopback-only smart mirror."""
import os

from dotenv import load_dotenv

from smart_mirror import create_app
from smart_mirror.config import PROJECT_DIR


def main():
    os.umask(0o077)
    load_dotenv(PROJECT_DIR / "secrets" / ".env", override=False)
    app = create_app()
    try:
        app.run(host="127.0.0.1", port=8080, debug=False, use_reloader=False, threaded=True)
    finally:
        app.extensions["mirror_close"]()


if __name__ == "__main__":
    main()
