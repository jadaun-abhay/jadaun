from django.urls import path, re_path
from rest_framework.views import APIView

from .base import BaseRouter
from .types import Route


class APIViewRouter(BaseRouter[tuple[Route, ...], type[APIView]]):
    routes: tuple[Route, ...] = (
        Route(
            url=r"^{prefix}{trailing_slash}",
            mapping={"get": "list", "post": "create"},
            name=r"{basename}-list-or-create",
            detail=False,
            initkwargs={},
        ),
        Route(
            url=r"^{prefix}/{lookup}{trailing_slash}$",
            mapping={
                "get": "retrieve",
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            },
            name=r"{basename}-detail",
            detail=True,
            initkwargs={},
        ),
    )

    def __init__(self, trailing_slash=True, use_regex_path=True):
        self.trailing_slash = "/" if trailing_slash else ""
        self._use_regex = use_regex_path
        if use_regex_path:
            self._base_pattern = "(?P<{lookup_prefix}{lookup_url_kwarg}>{lookup_value})"
            self._default_value_pattern = "[^/.]+"
            self._url_conf = re_path
        else:
            self._base_pattern = r"<{lookup_value}:{lookup_prefix}{lookup_url_kwarg}>"
            self._default_value_pattern = "str"
            self._url_conf = path
            # removing regex characters from routes
            _routes: list[Route] = []
            for route in self.routes:
                url_param = route.url
                url_param = url_param[
                    slice(
                        1 if url_param[0] == "^" else 0,
                        -1 if url_param[-1] == "$" else len(url_param),
                    )
                ]
                _routes.append(route._replace(url=url_param))
            self.routes = tuple(_routes)

        super().__init__()

    def get_default_basename(self, view_cls: type[APIView]):
        """
        If `basename` is not specified, attempt to automatically determine
        it from the view cls.

        It frames the basename with the help of the model the APIView is dedicated to.
        """
        model_cls = getattr(view_cls, "model", None)

        assert model_cls is not None, (
            "`basename` argument not specified, and could "
            "not automatically determine the name from the view_cls, as "
            "it does not have a `model` attribute."
        )

        return model_cls._meta.object_name.lower()

    def get_lookup_regex(self, view_cls: type[APIView], lookup_prefix="") -> str:
        """
        Given a view_cls, return the portion of URL regex that is used
        to match against a single instance.

        Note that lookup_prefix is not used directly inside REST rest_framework
        itself, but is required in order to nicely support nested router
        implementations, such as drf-nested-routers.

        https://github.com/alanjds/drf-nested-routers
        """
        lookup_field = getattr(view_cls, "lookup_field", "pk")
        lookup_url_kwarg = getattr(view_cls, "lookup_url_kwarg", None) or lookup_field
        lookup_value = None
        if not self._use_regex:
            lookup_value = getattr(view_cls, "lookup_value_converter", None)
        if lookup_value is None:
            lookup_value = getattr(
                view_cls, "lookup_value_regex", self._default_value_pattern
            )
        return self._base_pattern.format(
            lookup_prefix=lookup_prefix,
            lookup_url_kwarg=lookup_url_kwarg,
            lookup_value=lookup_value,
        )

    def get_method_map(
        self, view_cls: type[APIView], method_map: dict[str, str]
    ) -> dict[str, str]:
        """
        Given a view_cls, and a mapping of http methods to actions,
        return a new mapping which only includes any mappings that
        are actually implemented by the view_cls.
        """
        bound_methods: dict[str, str] = {}
        for method, action in method_map.items():
            if hasattr(view_cls, method):
                bound_methods[method] = action
        return bound_methods

    def get_urls(self):
        """
        Use the registered views to generate a list of URL patterns.
        """
        ret = []

        for prefix, view_cls, basename in self.registry:
            lookup = self.get_lookup_regex(view_cls)
            routes = self.routes

            for route in routes:
                # Only actions which actually exist on the view_cls will be bound
                mapping = self.get_method_map(view_cls, route.mapping)
                if not mapping:
                    continue

                # Build the url pattern
                regex = route.url.format(
                    prefix=prefix, lookup=lookup, trailing_slash=self.trailing_slash
                )

                # If there is no prefix, the first part of the url is probably
                # controlled by project's urls.py and the router is in an app,
                # so a slash in the beginning will (A) cause Django to give
                # warnings and (B) generate URLS that will require using '//'.
                if not prefix:
                    if self._url_conf is path:
                        if regex[0] == "/":
                            regex = regex[1:]
                    elif regex[:2] == "^/":
                        regex = "^" + regex[2:]

                initkwargs = route.initkwargs.copy()
                initkwargs.update(
                    {
                        "basename": basename,
                        "detail": route.detail,
                    }
                )

                view = view_cls.as_view(**initkwargs)
                name = route.name.format(basename=basename)
                ret.append(self._url_conf(regex, view, name=name))
        return ret
