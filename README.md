# jadaun

Dynamic app discovery and URL generation for Django + Django REST Framework.

Instead of hand-maintaining `INSTALLED_APPS` and a tree of `urls.py` files,
`jadaun` reads a small YAML config describing your apps and their allowed API
versions, discovers each app's views on disk, and generates the
`INSTALLED_APPS` list and `urlpatterns` for you — in one of two styles:

- **Folder-based routing** — a `views/` package's folder structure *is* the
  URL structure. No router, no manual `path()` calls.
- **Router-based routing** — a flat `views.py` module, with views and
  viewsets registered on routers automatically (list/detail generation for
  plain views, DRF's `DefaultRouter` for viewsets).

Wiring it up is a single call at the bottom of your settings module — no
edits to `manage.py`, no `include()` call to add to your root `urls.py`.

It also ships a friendlier `startapp` management command that understands
nested namespace apps and both routing styles, discovered automatically
once `jadaun` is in `INSTALLED_APPS` (which `autowire()` handles for you).

## Installation

Not published yet — add it as a local path or git dependency:

```bash
uv add jadaun --path ../jadaun        # local checkout
# or
uv add git+https://your-remote/jadaun.git
```

Add `"rest_framework"` and the apps `jadaun` discovers to your project as
usual; `jadaun` builds `INSTALLED_APPS` dynamically, so you generally don't
list your own apps by hand (see [Settings](#settings) below).

## Quick start

**1. Describe your apps in a YAML config** (`jadaun.config.yaml` by default):

```yaml
modules:
  widgets:
    allowed: ["v1"]
    default: "v1"
```

**2. Add one call to the bottom of your settings module.** Nothing else
changes — `manage.py` and your root `urls.py` stay exactly as Django
generated them:

```python
# config/settings.py
from jadaun import autowire

DEBUG = True
ROOT_URLCONF = "config.urls"      # your own urls.py - admin, static, whatever you want
DEFAULT_APPS_DIR = "apps"
# ... the rest of your settings ...

autowire(globals())               # must be the LAST statement - see below
```

`autowire()` discovers every app declared under `modules` and computes
`INSTALLED_APPS` for you, adding `"jadaun"` itself. That's the one thing it
*has* to do explicitly, and *before* `django.setup()` - Django reads the
whole `INSTALLED_APPS` list as the very first step of starting up, before
any app's own `ready()` can run, so there's no way to make this part happen
implicitly just because `jadaun` ends up installed.

Everything else follows automatically once `jadaun` is installed, with no
further calls:
- `startapp` (below) is discovered the same way Django discovers any
  app's management commands - no further wiring needed.
- `JadaunConfig.ready()` (jadaun's own `AppConfig`) mounts the discovered
  urls under `api/` *alongside* your own `config.urls`, by pointing
  `ROOT_URLCONF` at a small generated module - so your `urls.py` never
  needs an `include()` call for this at all. This happens automatically,
  after `django.setup()`'s app loading, since by then it's just reading
  `settings.ROOT_URLCONF` normally - no mid-import hazard to worry about.

**It has to be the last statement in the file.** It reads `DEBUG`,
`DEFAULT_APPS_DIR`, `DEFAULT_DJANGO_APPS`, `THIRD_PARTY_APPS`, `DEV_APPS`
and `PROD_APPS` straight out of `globals()` rather than through
`django.conf.settings`, specifically so it never triggers Django's lazy
settings loader while this very module is still mid-import — doing that
would make Django read a half-initialized settings module and silently
drop everything defined *after* that point in the file. Define every other
setting first, call `autowire(globals())` last.

**3. Write a view.** For `widgets` above, `jadaun` imports
`apps.widgets.api.v1.views` and turns whatever it finds there into routes
under `api/widgets/v1/...`.

### A note on timing

`autowire()` only touches the filesystem up front (to compute
`INSTALLED_APPS`) — it never imports your apps' own view modules at
settings-load time, so it's safe to run before `django.setup()`. The
*actual* urlpatterns (which does import every discovered app's views) are
only built the first time a URL is resolved, which is always after
`django.setup()` has finished — so your views are free to reference models
by then.

## Settings

`jadaun` doesn't ship its own settings module. In the `autowire()` flow
above, it reads straight out of your settings module's own namespace; used
manually (see [Advanced: manual wiring](#advanced-manual-wiring)), it falls
back to plain Django settings via `getattr(settings, "...", default)`.
Either way it never conflicts with how you manage configuration
(`pydantic-settings`, `django-environ`, plain `.py` files, …).

| Setting              | Default   | Meaning                                                             |
| --------------------- | --------- | -------------------------------------------------------------------- |
| `DEFAULT_APPS_DIR`    | `"apps"`  | Directory new/discovered apps live under.                            |
| `DEFAULT_DJANGO_APPS` | `[]`      | Always-installed Django apps (admin, auth, …).                       |
| `THIRD_PARTY_APPS`    | `[]`      | Always-installed third-party apps.                                   |
| `DEV_APPS`            | `[]`      | Installed only when `DEBUG` is `True`.                               |
| `PROD_APPS`           | `[]`      | Installed only when `DEBUG` is `False`.                              |

Apps declared under `modules` in the YAML config are discovered and
installed on top of these.

## The config file

```yaml
modules:
  core:
    allowed: ["v1", "v2"]
    default: "v1"
    deprecated: ["v1"]          # optional
    sunset_date:                # optional
      v1: "2026-12-31"
    submodules:                 # optional, for nested apps
      billing:
        allowed: ["v1"]
        default: "v1"
```

- A `modules` entry with no `submodules` is an app: `jadaun` expects
  `<DEFAULT_APPS_DIR>/core/` to exist with an `__init__.py` and `apps.py`,
  and imports `<DEFAULT_APPS_DIR>.core.api.<version>.views` for each
  `allowed` version.
- A `modules` entry **with** `submodules` is a pure namespace package — it
  needs an `__init__.py` but no `apps.py`, and is never installed as an app
  itself. Only its submodules are (e.g. `core.billing` above becomes the
  real, installed app, nested inside the `core` namespace folder).

## Routing styles

### Router-based (`views.py` as a single file)

```python
# apps/widgets/api/v1/views.py
from jadaun.views import BaseAPIView

class ItemView(BaseAPIView):
    model = Item          # required - used to derive the basename

    def get(self, request, *args, **kwargs):
        ...               # list
    def post(self, request, *args, **kwargs):
        ...               # create
    def retrieve(self, request, *args, **kwargs):
        ...               # single-instance GET, via .../<pk>/
```

One `BaseAPIView` subclass maps to *both* the list/create route and the
detail route for a resource — `jadaun`'s `APIViewRouter` (a from-scratch
router built the same way DRF's own routers work, but for plain views) binds
whichever HTTP methods you implement. `BaseAPIViewSet` subclasses in the
same file go through DRF's regular `DefaultRouter` instead.

### Folder-based (`views/` as a package)

```
apps/widgets/api/v1/views/
├── __init__.py            # namespace only -> no route
├── auth/
│   ├── login.py           # -> widgets/v1/auth/login/
│   └── logout.py          # -> widgets/v1/auth/logout/
└── item/
    ├── __init__.py        # -> widgets/v1/item/
    └── <str:identifier>/
        └── __init__.py    # -> widgets/v1/item/<str:identifier>/
```

When `views` is a package, the folder structure *is* the route structure:

- Every folder/file name becomes a URL path segment, used verbatim — so
  Django path converters can be embedded directly in a folder name
  (`<str:identifier>`).
- A leaf doesn't have to be `__init__.py` — any `.py` file directly in a
  folder is a route too, named after the file.
- Each module may declare **at most one** `BaseAPIView` subclass. A module
  with none is a pure namespace (its subfolders/files still get walked).
  Declaring more than one view, or a `BaseAPIViewSet`, in the same module
  raises `ImproperlyConfigured` at startup.

## Views

```python
from jadaun.views import BaseAPIView, BaseAPIViewSet

class ItemView(BaseAPIView):
    model = Item
    lookup_field = "pk"          # from LookupFieldMixin
    view_url = "items"           # optional, overrides the derived route/prefix

    def get_object(self):
        ...                      # provided by LookupFieldMixin

    def post(self, request, *args, **kwargs):
        if not request.data.get("name"):
            self.fail("name is required", status_code=400)
        ...
```

- `LookupFieldMixin` gives every view a `get_object()` built from
  `lookup_field` / `lookup_url_kwarg` / `model`.
- `fail(message, status_code=400)` raises a `ViewError` (a DRF
  `APIException`), which DRF's exception handler turns into
  `Response({"detail": message}, status=status_code)`.
- `view_url` overrides the route/prefix `jadaun` would otherwise derive from
  the class name.

`BaseAPIViewSet` is the equivalent base for DRF `GenericViewSet`-style
viewsets; it carries the same `LookupFieldMixin` and `view_url` override.

## `startapp`

```bash
python manage.py startapp core                 # apps/core
python manage.py startapp generator core        # apps/generator/core (generator/ is a namespace folder)
python manage.py startapp generator/core        # same as above
python manage.py startapp                       # interactive wizard
```

- Extra leading name segments become namespace folders (auto-created with
  just an `__init__.py`, never an `apps.py` — matching how `AppRegistry`
  treats `submodules` entries).
- `--template package` (default) scaffolds a folder-based `views/` package;
  `--template module` scaffolds a flat `views.py`.
- Run with no arguments (in a real terminal) for an interactive prompt for
  both the app name/path and the template.
- `--no-input` forces non-interactive behavior even in a terminal.

## Advanced: manual wiring

`autowire()` is a thin convenience layer over three lower-level pieces, all
still available directly if you want more control — e.g. `Initializer` also
inserts a default `host:port` into `runserver` from the config file's
`server.args`, which only works from `manage.py` (nothing running from
inside settings.py can reliably rewrite `sys.argv` before Django's command
dispatch reads it, which is exactly why `autowire()` doesn't attempt it):

```python
# manage.py
import os
import sys

def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    from django.conf import settings
    from django.core import management

    from jadaun.initializer import Initializer

    initializer = Initializer(sys.argv)
    args = initializer.initialize()       # parses config, builds INSTALLED_APPS + urlpatterns eagerly
    settings.INITIALIZER = initializer

    management.execute_from_command_line(args)

if __name__ == "__main__":
    main()
```

```python
# config/urls.py
from django.conf import settings
from django.urls import include, path

urlpatterns = [
    path("api/", include(settings.INITIALIZER.builder.build())),
]
```

Unlike `autowire()`, this path builds the full urlpatterns tree (importing
every discovered app's views) eagerly, in `manage.py`, before
`django.setup()` runs — so, same as `autowire()`, a view that references a
model directly in its own module body (rather than inside a method) will
raise `AppRegistryNotReady`. This is a property of discovering apps before
Django's app registry exists at all, not something either wiring style
fixes; keep model references inside methods/properties, not at class body
level, if you hit it.

`Initializer`/`ConfigParser`/`Builder`/`AppRegistry` are also usable
directly/individually if you want a completely custom wiring strategy.

## Project layout

```
src/jadaun/
├── autowire.py                 # autowire() - one-call settings.py wiring
├── config.py                   # ConfigParser - loads the YAML config
├── initializer/
│   ├── __init__.py             # Initializer - manual manage.py entry point
│   ├── apps.py                 # AppConfig, AppRegistry - app discovery
│   ├── builder.py              # Builder - urlpatterns generation
│   ├── functions.py            # view discovery (recursive + folder-based)
│   └── types.py                # ModuleConfigDescriptionType (pydantic)
├── router/
│   ├── base.py                 # BaseRouter - generic DRF-style router base
│   └── view.py                 # APIViewRouter - router for BaseAPIView
├── views/
│   ├── view.py                 # BaseAPIView, LookupFieldMixin, ViewError
│   └── viewset.py              # BaseAPIViewSet
└── management/commands/startapp.py
```
