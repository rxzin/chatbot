"""Primary key default, chosen by the ID_STRATEGY setting."""

from sqlalchemy import TextClause, text

from core.config import getSettings

ID_DEFAULT_SQL = {"uuidv7": "uuidv7()", "random": "gen_random_uuid()"}


def id_server_default() -> TextClause:
    """The server default for id columns, read from settings when called."""
    return text(ID_DEFAULT_SQL[getSettings().ID_STRATEGY])
