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

It also ships a friendlier `startapp` management command that understands
nested namespace apps and both routing styles.

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
server:
  args:
    host: 0.0.0.0
    port: 8000

modules:
  widgets:
    allowed: ["v1"]
    default: "v1"
```

**2. Wire it into `manage.py`**, before Django starts up:

```python
import os
import sys

def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    from django.conf import settings
    from django.core import management

    from jadaun.initializer import Initializer

    initializer = Initializer(sys.argv)
    args = initializer.initialize()
    settings.INITIALIZER = initializer

    management.execute_from_command_line(args)

if __name__ == "__main__":
    main()
```

`Initializer.initialize()` parses the YAML config, discovers every
configured app (`AppRegistry`), sets `settings.INSTALLED_APPS`, and builds
the full `urlpatterns` tree (`Builder`) — all before Django's app registry
loads.

**3. Include the generated urls** in your root `urls.py`:

```python
from django.conf import settings
from django.urls import include, path

urlpatterns = [
    path("api/", include(settings.INITIALIZER.builder.build())),
]
```

**4. Write a view.** For `widgets` above, `jadaun` imports
`apps.widgets.api.v1.views` and turns whatever it finds there into routes
under `api/widgets/v1/...`.

## Settings

`jadaun` doesn't ship its own settings module — it reads plain Django
settings via `getattr(settings, "...", default)`, so it never conflicts with
however you manage configuration (`pydantic-settings`, `django-environ`,
plain `.py` files, …).

| Setting              | Default   | Meaning                                                             |
| --------------------- | --------- | -------------------------------------------------------------------- |
| `DEFAULT_APPS_DIR`    | `"apps"`  | Directory new/discovered apps live under.                            |
| `DEFAULT_DJANGO_APPS` | `[]`      | Always-installed Django apps (admin, auth, …).                       |
| `THIRD_PARTY_APPS`    | `[]`      | Always-installed third-party apps.                                   |
| `DEV_APPS`            | `[]`      | Installed only when `settings.DEBUG` is `True`.                      |
| `PROD_APPS`           | `[]`      | Installed only when `settings.DEBUG` is `False`.                     |

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

## Project layout

```
src/jadaun/
├── config.py                  # ConfigParser - loads the YAML config
├── initializer/
│   ├── __init__.py            # Initializer - entry point from manage.py
│   ├── apps.py                # AppConfig, AppRegistry - app discovery
│   ├── builder.py             # Builder - urlpatterns generation
│   ├── functions.py           # view discovery (recursive + folder-based)
│   └── types.py                # ModuleConfigDescriptionType (pydantic)
├── router/
│   ├── base.py                 # BaseRouter - generic DRF-style router base
│   └── view.py                 # APIViewRouter - router for BaseAPIView
├── views/
│   ├── view.py                 # BaseAPIView, LookupFieldMixin, ViewError
│   └── viewset.py              # BaseAPIViewSet
└── management/commands/startapp.py
```
