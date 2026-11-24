from typing import TypeVar

from django.core.exceptions import ImproperlyConfigured
from django.urls import URLPattern, URLResolver
from django.views.generic.base import View

from .types import DynamicRoute, Route

R = TypeVar("R", bound=tuple[Route | DynamicRoute, ...])
V = TypeVar("V", bound=type[View])


class BaseRouter[R, V]:
    routes: R

    def __init__(self) -> None:
        self.registry: list[tuple[str, V, str]] = []

    def register(self, prefix: str, view_cls: V, basename: str | None = None) -> None:
        if basename is None:
            basename = self.get_default_basename(view_cls)

        if self.is_already_registered(basename):
            msg = (
                f'Router with basename "{basename}" is already registered. '
                f'Please provide a unique basename for view "{view_cls.__class__.__name__}"'
            )
            raise ImproperlyConfigured(msg)

        self.registry.append((prefix, view_cls, basename))

        # invalidate the urls cache on new entry registeration
        if hasattr(self, "_urls"):
            del self._urls

    def is_already_registered(self, new_basename) -> bool:
        """
        Check if `basename` is already registered
        """
        return any(
            basename == new_basename for _prefix, _view_cls, basename in self.registry
        )

    def get_default_basename(self, view_cls: V) -> str:
        """
        If `basename` is not specified, attempt to automatically determine
        it from the view_cls.
        """
        raise NotImplementedError("get_default_basename must be overridden")

    def get_urls(self) -> list[URLResolver | URLPattern]:
        """
        Return a list of URL patterns, given the registered view_cls.
        """
        raise NotImplementedError("get_urls must be overridden")

    @property
    def urls(self):
        if not hasattr(self, "_urls"):
            self._urls = self.get_urls()
        return self._urls
