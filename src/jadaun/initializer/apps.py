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

    def populate(self, DEFAULT_APPS_DIR: str | None = None) -> None:
        """Discover and register every configured app.

        Idempotent: once populated, further calls are no-ops, so callers
        don't need to guard against re-triggering imports/filesystem checks.

        Every key read here (`DEFAULT_APPS_DIR`, `DEFAULT_DJANGO_APPS`,
        `THIRD_PARTY_APPS`, `DEV_APPS`, `PROD_APPS`) is read from the host
        project's Django settings via `getattr`, with safe defaults, so this
        package never has to own or ship its own settings module.
        """
        if self._populated:
            return

        DEFAULT_APPS_DIR = DEFAULT_APPS_DIR or getattr(
            settings, "DEFAULT_APPS_DIR", _DEFAULT_APPS_DIR
        )

        for app_key in APP_KEYS:
            match app_key:
                case "DEFAULT_DJANGO_APPS":
                    self.installed_apps.update(
                        {
                            app: None
                            for app in getattr(
                                settings, "DEFAULT_DJANGO_APPS", _DEFAULT_DJANGO_APPS
                            )
                        }
                    )
                case "THIRD_PARTY_APPS":
                    self.installed_apps.update(
                        {
                            app: None
                            for app in getattr(
                                settings, "THIRD_PARTY_APPS", _THIRD_PARTY_APPS
                            )
                        }
                    )
                case "DEV_APPS":
                    if settings.DEBUG:
                        self.installed_apps.update(
                            {
                                app: None
                                for app in getattr(settings, "DEV_APPS", _DEV_APPS)
                            }
                        )
                case "PROD_APPS":
                    if not settings.DEBUG:
                        self.installed_apps.update(
                            {
                                app: None
                                for app in getattr(settings, "PROD_APPS", _PROD_APPS)
                            }
                        )

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

        assert DEFAULT_APPS_DIR is not None, "Mention the `DEFAULT_APPS_DIR`."
        _register(self.parsed_apps, module_path=DEFAULT_APPS_DIR)
        self._populated = True
