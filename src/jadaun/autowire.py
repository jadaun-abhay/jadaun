from __future__ import annotations

import sys
from types import ModuleType
from typing import TYPE_CHECKING, Any

from django.urls import URLPattern, URLResolver, include, path

if TYPE_CHECKING:
    from jadaun.initializer.builder import Builder

_GENERATED_URLCONF = "jadaun._generated_urlconf"


def autowire(
    globalns: dict[str, Any],
    *,
    root_urlconf: str | None = None,
    config_file: str | None = None,
    api_prefix: str = "api/",
) -> Builder:
    """Wire jadaun into a Django settings module with a single call.

    Call this as the LAST statement in your settings module, after every
    other setting (`DEBUG`, `DATABASES`, `ROOT_URLCONF`, ...) is already
    defined:

        from jadaun import autowire

        DEBUG = True
        ROOT_URLCONF = "config.urls"
        ...
        autowire(globals())

    No changes are needed to `manage.py` or to your own `ROOT_URLCONF`
    module - this computes `INSTALLED_APPS` and mounts the generated urls
    for you.

    It must run last: it reads `DEFAULT_APPS_DIR`/`DEBUG`/
    `DEFAULT_DJANGO_APPS`/`THIRD_PARTY_APPS`/`DEV_APPS`/`PROD_APPS` straight
    out of `globalns` (your settings module's own namespace) rather than
    through `django.conf.settings`. Touching `django.conf.settings` while
    this module is still mid-import would make Django lazily load a
    half-initialized settings module on the spot, silently dropping
    whatever is defined *after* that point in the file - `globalns` sidesteps
    that entirely.

    `jadaun.initializer`/`jadaun.router`/`jadaun.views` (and, through them,
    `rest_framework`) are only imported once this function actually runs,
    not merely when `jadaun` itself is imported - DRF touches
    `django.conf.settings` at import time too, so importing it any earlier
    than this would hit the exact same hazard just from `from jadaun import
    autowire` appearing anywhere in the file.

    It discovers your apps and writes `INSTALLED_APPS` into `globalns`
    directly - this part runs eagerly, right now, but only touches the
    filesystem (no app's own view modules are imported yet, so this is safe
    even though `django.setup()` hasn't run).

    It also points `globalns["ROOT_URLCONF"]` at a small generated module
    that mounts the dynamic urls under `api_prefix` alongside your own
    `root_urlconf` (defaulting to `globalns["ROOT_URLCONF"]`) - built so
    that Django only imports either of them, and only builds the actual
    urlpatterns (which *does* import every discovered app's views), the
    first time a URL is resolved. That's always after `django.setup()` has
    finished, so views are free to reference models.

    Returns the `Builder` used, also stashed on `globalns["JADAUN_BUILDER"]`
    for introspection/debugging.
    """
    from jadaun.config import ConfigParser
    from jadaun.initializer.builder import Builder

    root_urlconf = root_urlconf or globalns.get("ROOT_URLCONF")
    if not root_urlconf:
        raise ValueError(
            "autowire() needs ROOT_URLCONF - set it before calling autowire(), "
            "or pass root_urlconf=... explicitly."
        )

    config_parser = ConfigParser(config_file) if config_file else ConfigParser()
    config_parser.load_config()
    modules: dict[str, Any] = config_parser.config.get("modules", {}) or {}

    third_party_apps = list(globalns.get("THIRD_PARTY_APPS", []))
    if "jadaun" not in third_party_apps:
        third_party_apps = ["jadaun", *third_party_apps]

    builder = Builder(modules=modules)
    builder.populate_apps(
        # Always pass a concrete value (never None) for every key, so
        # AppRegistry.populate() never falls back to reading
        # django.conf.settings itself - see its docstring for why that
        # matters here specifically.
        DEFAULT_APPS_DIR=globalns.get("DEFAULT_APPS_DIR", "apps"),
        DEBUG=globalns.get("DEBUG", False),
        DEFAULT_DJANGO_APPS=globalns.get("DEFAULT_DJANGO_APPS", []),
        THIRD_PARTY_APPS=third_party_apps,
        DEV_APPS=globalns.get("DEV_APPS", []),
        PROD_APPS=globalns.get("PROD_APPS", []),
    )

    globalns["INSTALLED_APPS"] = list(builder.apps.installed_apps.keys())
    globalns["JADAUN_BUILDER"] = builder
    globalns["ROOT_URLCONF"] = _mount_combined_urlconf(root_urlconf, builder, api_prefix)

    return builder


def _mount_combined_urlconf(root_urlconf: str, builder: Builder, api_prefix: str) -> str:
    """Register a urlconf module combining `root_urlconf` with the generated
    urls, without importing either eagerly.

    Django only imports `ROOT_URLCONF` - and reads its `urlpatterns` - the
    first time a URL actually needs resolving (normally the first request),
    well after `django.setup()` has finished. This module is built from
    inside settings.py, well *before* that, so its own `urlpatterns` is
    computed lazily too (via module-level `__getattr__`, PEP 562): neither
    `include(root_urlconf)` nor `builder.build()` (which imports every
    discovered app's view modules - possibly including models) run until
    something actually asks this module for its `urlpatterns`.
    """
    module = ModuleType(_GENERATED_URLCONF)

    def __getattr__(name: str) -> list[URLPattern | URLResolver]:
        if name != "urlpatterns":
            raise AttributeError(name)
        value = [
            path("", include(root_urlconf)),
            path(api_prefix, include(builder.build())),
        ]
        module.urlpatterns = value
        return value

    module.__getattr__ = __getattr__
    sys.modules[_GENERATED_URLCONF] = module
    return _GENERATED_URLCONF
