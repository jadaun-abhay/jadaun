import importlib
from pathlib import Path
from types import ModuleType
from typing import Any

from django.conf import settings
from django.urls import URLPattern, URLResolver, include, path
from rest_framework.routers import DefaultRouter

from jadaun.initializer.functions import build_folder_urls, build_recursive_urls
from jadaun.router import APIViewRouter
from jadaun.views import BaseAPIView, BaseAPIViewSet

from .apps import AppConfig, AppRegistry
from .types import ModuleConfigDescriptionType


class Builder:
    apps: AppRegistry
    urlpatterns: list[URLPattern | URLResolver]

    def _parse(self, modules: dict[str, Any]) -> dict[str, ModuleConfigDescriptionType]:
        parsed_modules: dict[str, ModuleConfigDescriptionType] = {}
        for module_name, module_config in modules.items():
            parsed_modules[module_name] = ModuleConfigDescriptionType(**module_config)
        return parsed_modules

    def __init__(self, modules: dict[str, Any]):
        self.apps = AppRegistry(self._parse(modules))
        self._built = False

    def populate_apps(self, **populate_overrides: Any) -> None:
        """Discover apps and set `settings.INSTALLED_APPS` - nothing else.

        Unlike `build()`, this never imports a single app's own view
        modules (which may import models), so it's safe to call this
        *before* `django.setup()` - all it does is filesystem checks and
        `AppConfig.create()`, which only introspects a module path.

        `populate_overrides` (`DEFAULT_APPS_DIR`, `DEBUG`,
        `DEFAULT_DJANGO_APPS`, `THIRD_PARTY_APPS`, `DEV_APPS`, `PROD_APPS`)
        are forwarded to `AppRegistry.populate` as-is; see its docstring for
        why `jadaun.autowire` needs to pass all of them explicitly.
        """
        self.apps.populate(**populate_overrides)
        settings.INSTALLED_APPS = list(self.apps.installed_apps.keys())

    def build(self, **populate_overrides: Any) -> list[URLPattern | URLResolver]:
        """Run app discovery (if needed) and generate urlpatterns.

        Idempotent: the first call does the work; later calls just return
        the cached `self.urlpatterns`. Imports every discovered app's view
        modules, so only call this once the app registry is ready - i.e.
        after `django.setup()` - or let `jadaun.autowire` defer it for you.
        """
        if self._built:
            return self.urlpatterns

        self.populate_apps(**populate_overrides)
        self.urlpatterns = self._build_urls()
        self._built = True
        return self.urlpatterns

    def _build_urls(self) -> list[URLPattern | URLResolver]:
        urlpatterns: list[URLPattern | URLResolver] = []
        for app_config, app_description in self.apps.installed_apps.items():
            if not (
                isinstance(app_config, AppConfig)
                and isinstance(app_description, ModuleConfigDescriptionType)
            ):
                continue
            app_urls = self._build_app_urls(app_config, app_description)
            urlpatterns.append(path(f"{app_config.label}/", include(app_urls)))
        return urlpatterns

    def _build_app_urls(
        self, app_config: AppConfig, config: ModuleConfigDescriptionType
    ) -> list[URLPattern | URLResolver]:
        urlpatterns: list[URLPattern | URLResolver] = []
        for version in config.allowed:
            view_module = self._import_views_module(app_config, version)
            version_urlpatterns = self._build_version_urls(view_module)
            urlpatterns.append(path(f"{version}/", include(version_urlpatterns)))
        return urlpatterns

    def _import_views_module(self, app_config: AppConfig, version: str) -> ModuleType:
        app_module = app_config.module.__name__
        try:
            return importlib.import_module(f"{app_module}.api.{version}.views")
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                f"Module {app_module}.api.{version}.views not found. Please check the module configuration."
            ) from exc

    def _build_version_urls(self, view_module: ModuleType) -> list[URLPattern | URLResolver]:
        module_path = getattr(view_module, "__path__", None)

        if module_path is not None:
            # `views/` is a package: the folder structure *is* the route
            # structure (folder-based routing), so it's walked on disk
            # instead of being imported submodule by submodule - that also
            # lets folder names carry Django path-converter syntax (e.g.
            # `<str:identifier>`), which isn't a legal Python module name.
            return build_folder_urls(Path(module_path[0]))

        # `views.py` is a single flat module: no folder structure to
        # respect, so views/viewsets go through router-based registration.
        return self._build_router_urls(build_recursive_urls(view_module))

    def _build_router_urls(
        self, views_or_viewsets: list[type[BaseAPIView | BaseAPIViewSet]]
    ) -> list[URLPattern | URLResolver]:
        view_router = APIViewRouter()
        viewset_router = DefaultRouter()

        for view_cls in views_or_viewsets:
            if issubclass(view_cls, BaseAPIViewSet):
                basename = view_cls.view_url or view_cls.__name__.lower().removesuffix(
                    "viewset"
                )
                viewset_router.register(basename, view_cls, basename=basename)
                continue

            if issubclass(view_cls, BaseAPIView):
                prefix = view_cls.view_url or view_cls.__name__.lower().removesuffix(
                    "view"
                )
                view_router.register(prefix, view_cls)

        return [*view_router.urls, *viewset_router.urls]
