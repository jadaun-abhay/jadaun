from __future__ import annotations

from pathlib import Path

from django.apps import AppConfig as OGAppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from jadaun.initializer.constants import APP_KEYS
from jadaun.initializer.types import ModuleConfigDescriptionType

# Host-project overridable via Django settings; these are the defaults when
# the host doesn't set them.
_DEFAULT_APPS_DIR = "apps"
_DEFAULT_DJANGO_APPS: list[str] = []
_THIRD_PARTY_APPS: list[str] = []
_DEV_APPS: list[str] = []
_PROD_APPS: list[str] = []


class AppConfig(OGAppConfig):
    name: str
    path: str

    @classmethod
    def create(cls, entry: str) -> AppConfig:
        return super().create(entry)  # pyright: ignore[reportReturnType]


class AppRegistry:
    def __init__(self, parsed_config_apps: dict[str, ModuleConfigDescriptionType]):
        self.installed_apps: dict[
            AppConfig | str, ModuleConfigDescriptionType | None
        ] = {}
        self.parsed_apps = parsed_config_apps
        self._populated = False

    def populate(
        self,
        DEFAULT_APPS_DIR: str | None = None,
        *,
        DEBUG: bool | None = None,
        DEFAULT_DJANGO_APPS: list[str] | None = None,
        THIRD_PARTY_APPS: list[str] | None = None,
        DEV_APPS: list[str] | None = None,
        PROD_APPS: list[str] | None = None,
    ) -> None:
        """Discover and register every configured app.

        Idempotent: once populated, further calls are no-ops, so callers
        don't need to guard against re-triggering imports/filesystem checks.

        Every key here (`DEFAULT_APPS_DIR`, `DEBUG`, `DEFAULT_DJANGO_APPS`,
        `THIRD_PARTY_APPS`, `DEV_APPS`, `PROD_APPS`) can be passed explicitly;
        any left as `None` are read from the host project's Django settings
        via `getattr`, with safe defaults - so this package never has to own
        or ship its own settings module.

        Callers that run this *during* Django settings-module import (as
        `jadaun.autowire` does) must pass every value explicitly instead of
        relying on the `django.conf.settings` fallback: touching
        `django.conf.settings` mid-import would trigger Django's lazy setup
        using a half-initialized settings module, silently dropping whatever
        is defined after that point in the file.
        """
        if self._populated:
            return

        # Resolved into freshly, explicitly non-Optional-typed locals - a
        # plain `if X is None: X = getattr(...)` reassignment doesn't narrow
        # `X: list[str] | None` to `list[str]` for the type checker, since
        # `getattr(settings, ..., default)` is typed `Any` (no django-stubs)
        # and assigning `Any` back onto an Optional-declared parameter keeps
        # the Optional in its narrowed type.
        apps_dir: str = DEFAULT_APPS_DIR or getattr(
            settings, "DEFAULT_APPS_DIR", _DEFAULT_APPS_DIR
        )
        debug: bool = settings.DEBUG if DEBUG is None else DEBUG
        default_django_apps: list[str] = (
            DEFAULT_DJANGO_APPS
            if DEFAULT_DJANGO_APPS is not None
            else getattr(settings, "DEFAULT_DJANGO_APPS", _DEFAULT_DJANGO_APPS)
        )
        third_party_apps: list[str] = (
            THIRD_PARTY_APPS
            if THIRD_PARTY_APPS is not None
            else getattr(settings, "THIRD_PARTY_APPS", _THIRD_PARTY_APPS)
        )
        dev_apps: list[str] = (
            DEV_APPS if DEV_APPS is not None else getattr(settings, "DEV_APPS", _DEV_APPS)
        )
        prod_apps: list[str] = (
            PROD_APPS
            if PROD_APPS is not None
            else getattr(settings, "PROD_APPS", _PROD_APPS)
        )

        for app_key in APP_KEYS:
            match app_key:
                case "DEFAULT_DJANGO_APPS":
                    self.installed_apps.update({app: None for app in default_django_apps})
                case "THIRD_PARTY_APPS":
                    self.installed_apps.update({app: None for app in third_party_apps})
                case "DEV_APPS":
                    if debug:
                        self.installed_apps.update({app: None for app in dev_apps})
                case "PROD_APPS":
                    if not debug:
                        self.installed_apps.update({app: None for app in prod_apps})

        def _register(
            parsed_apps: dict[str, ModuleConfigDescriptionType],
            module_path: str,
        ) -> None:
            for module, config in parsed_apps.items():
                current_path = f"{module_path}.{module}"
                app_path = Path(*current_path.split("."))

                if config.submodules:
                    # A node with submodules is a pure namespace package: it
                    # needs to exist and be importable, but it isn't itself a
                    # Django app, so no apps.py is required and it never gets
                    # registered as an installed app.
                    if not (app_path.is_dir() and (app_path / "__init__.py").is_file()):
                        raise ImproperlyConfigured(
                            f"App {current_path} - declared in the config file is not found."
                            f" Please check the {app_path} directory."
                        )
                    _register(config.submodules, module_path=current_path)
                    continue

                if not (
                    app_path.is_dir()
                    and (app_path / "__init__.py").is_file()
                    and (app_path / "apps.py").is_file()
                ):
                    raise ImproperlyConfigured(
                        f"App {current_path} - declared in the config file is not found."
                        f" Please check the {app_path} directory."
                    )
                app_config: AppConfig = AppConfig.create(current_path)
                self.installed_apps[app_config] = config

        _register(self.parsed_apps, module_path=apps_dir)
        self._populated = True
