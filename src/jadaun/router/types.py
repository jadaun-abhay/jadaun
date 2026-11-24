from typing import Any, NamedTuple


class Route(NamedTuple):
    url: str
    mapping: dict[str, str]
    name: str
    detail: bool
    initkwargs: dict[str, Any]


class DynamicRoute(NamedTuple):
    url: str
    name: str
    detail: bool
    initkwargs: dict[str, Any]
