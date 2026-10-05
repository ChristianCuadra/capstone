"""Cliente (tenant) activo en el contexto de ejecución actual."""

from contextvars import ContextVar, Token

_current_client_id: ContextVar[int | None] = ContextVar("current_client_id", default=None)


# Clientes a los que el usuario de la petición puede acceder. None = sin restricción
# (administradora, shell, comandos de gestión). Un conjunto vacío = no ve ningún cliente.
_allowed_client_ids: ContextVar["frozenset[int] | None"] = ContextVar("allowed_client_ids", default=None)


def get_allowed_client_ids() -> "frozenset[int] | None":
    return _allowed_client_ids.get()


def set_allowed_client_ids(ids) -> Token:
    return _allowed_client_ids.set(None if ids is None else frozenset(ids))


def reset_allowed_client_ids(token: Token) -> None:
    _allowed_client_ids.reset(token)


def get_current_client_id() -> int | None:
    return _current_client_id.get()


def set_current_client_id(client_id: int | None) -> Token:
    return _current_client_id.set(client_id)


def reset_current_client_id(token: Token) -> None:
    _current_client_id.reset(token)
