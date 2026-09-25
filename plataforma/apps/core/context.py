"""Cliente (tenant) activo en el contexto de ejecución actual."""

from contextvars import ContextVar, Token

_current_client_id: ContextVar[int | None] = ContextVar("current_client_id", default=None)


def get_current_client_id() -> int | None:
    return _current_client_id.get()


def set_current_client_id(client_id: int | None) -> Token:
    return _current_client_id.set(client_id)


def reset_current_client_id(token: Token) -> None:
    _current_client_id.reset(token)
