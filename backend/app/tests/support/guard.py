"""
The check that runs before any test touches a database.

The suite runs TRUNCATE ... CASCADE and FLUSHDB between tests. This function is the
only thing between those statements and whatever the process happens to be pointed at:
a variable exported in the shell (POSTGRESQL_SERVER, REDIS_URL) beats tests/test.env.
"""

from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

DEV_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

LOCAL_HOSTS = {"127.0.0.1", "localhost"}
DEFAULT_POSTGRES_PORT = 5432
DEFAULT_REDIS_PORT = 6379


def assert_safe_test_target(settings, dev_env_file: Path | None = DEV_ENV_FILE) -> None:
    """
    Raise RuntimeError, naming the rule that failed, unless every rule holds.

    1. settings.POSTGRESQL_DATABASE ends with "_test".
    2. settings.POSTGRESQL_SERVER is 127.0.0.1 or localhost.
    3. settings.EXTERNAL_SERVICES == "fake".
    4. The port in settings.REDIS_URL is not 6379 (a URL with no port means 6379).
    5. If dev_env_file exists, the (host, port, database) under test differs from the
       one that file names. Read it with dotenv_values; treat localhost and 127.0.0.1
       as the same host; a file with no POSTGRESQL_PORT means 5432. Never put a value
       read from that file into an error message.

    `settings` only needs the five attributes above, so tests pass a SimpleNamespace.
    """
    if not settings.POSTGRESQL_DATABASE.endswith("_test"):
        _refuse("the database name must end with _test")
    if settings.POSTGRESQL_SERVER not in LOCAL_HOSTS:
        _refuse("the database host must be 127.0.0.1 or localhost")
    if settings.EXTERNAL_SERVICES != "fake":
        _refuse("EXTERNAL_SERVICES must be fake")
    if (urlsplit(settings.REDIS_URL).port or DEFAULT_REDIS_PORT) == DEFAULT_REDIS_PORT:
        _refuse("Redis must not be on port 6379, the development default")

    if dev_env_file is None or not dev_env_file.exists():
        return
    dev = dotenv_values(dev_env_file)
    dev_target = (
        _same_host(dev.get("POSTGRESQL_SERVER")),
        int(dev.get("POSTGRESQL_PORT") or DEFAULT_POSTGRES_PORT),
        dev.get("POSTGRESQL_DATABASE"),
    )
    test_target = (
        _same_host(settings.POSTGRESQL_SERVER),
        int(settings.POSTGRESQL_PORT),
        settings.POSTGRESQL_DATABASE,
    )
    if test_target == dev_target:
        _refuse(f"the test target is the database named in {dev_env_file.name}")


def _refuse(rule: str) -> None:
    raise RuntimeError(f"Refusing to run the tests: {rule}.")


def _same_host(name: str | None) -> str | None:
    """localhost and 127.0.0.1 are one machine."""
    return "127.0.0.1" if name in LOCAL_HOSTS else name
