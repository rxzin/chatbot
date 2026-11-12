"""Shared test setup. The first lines must run before anything from the app is imported."""

import os
from pathlib import Path

# The app reads its settings when modules are first imported. Pointing it at test.env
# here keeps every test away from backend/app/.env, which holds real keys.
os.environ.setdefault("APP_ENV_FILE", str(Path(__file__).parent / "test.env"))
