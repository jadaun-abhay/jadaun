from __future__ import annotations

import importlib.util
import inspect
import pkgutil
import uuid
from importlib import import_module
from pathlib import Path
from types import ModuleType

from django.core.exceptions import ImproperlyConfigured
from django.urls import URLPattern, URLResolver, path

from jadaun.views import BaseAPIView, BaseAPIViewSet


def _is_view_class(obj: object, module: ModuleType) -> bool:
    return (
        inspect.isclass(obj)
        and obj.__module__ == module.__name__
        and (issubclass(obj, BaseAPIView) or issubclass(obj, BaseAPIViewSet))
        and obj not in (BaseAPIView, BaseAPIViewSet)
    )


def build_recursive_urls(
    module: ModuleType,
) -> list[type[BaseAPIView | BaseAPIViewSet]]:
    """Collect every `BaseAPIView`/`BaseAPIViewSet` subclass declared in `module`.

    If `module` is a package, every submodule is imported and walked too, so a
    views package can be split across multiple files (or further packages).

    Args:
        module (ModuleType): The `views` module (or package) to walk.

    Returns:
        list[type[BaseAPIView | BaseAPIViewSet]]: The view/viewset classes found.
    """
    views: list[type[BaseAPIView | BaseAPIViewSet]] = [
        cls
        for _, cls in inspect.getmembers(
            module, lambda obj: _is_view_class(obj, module)
        )
    ]

    module_path = getattr(module, "__path__", None)
    if module_path is None:
        return views

    for _, submodule_name, _ in pkgutil.iter_modules(module_path):
        submodule = import_module(f"{module.__name__}.{submodule_name}")
        views.extend(build_recursive_urls(submodule))

    return views


def _load_module_from_file(file_path: Path) -> ModuleType:
    # Loaded by file path (not dotted import) so folder names can contain
    # characters Python identifiers can't, e.g. `<str:identifier>`.
    spec = importlib.util.spec_from_file_location(
        f"_folder_view_{uuid.uuid4().hex}", file_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load view module at {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _single_view_in(module: ModuleType, file_path: Path) -> type[BaseAPIView] | None:
    found = [
        cls
        for _, cls in inspect.getmembers(
            module, lambda obj: _is_view_class(obj, module)
        )
    ]

    viewsets = [cls for cls in found if issubclass(cls, BaseAPIViewSet)]
    if viewsets:
        raise ImproperlyConfigured(
            f"{file_path}: viewsets are not supported in folder-based routing yet."
        )

    if len(found) > 1:
        names = ", ".join(cls.__name__ for cls in found)
        raise ImproperlyConfigured(
            f"{file_path} declares {len(found)} views ({names}); folder-based "
            "routing expects exactly one view per module."
        )

    return found[0] if found else None


def _bind_leaf(file_path: Path, url: str) -> URLResolver | URLPattern | None:
    view_cls = _single_view_in(_load_module_from_file(file_path), file_path)
    if view_cls is None:
        return None
    return path(url, view_cls.as_view(), name=view_cls.__name__.lower())


def build_folder_urls(
    root: Path, url_prefix: str = ""
) -> list[URLPattern | URLResolver]:
    """Recursively bind views to their folder/file path.

    A leaf doesn't have to be `__init__.py` - any `.py` file directly in a
    folder is a route too, named after the file, e.g. `auth/login.py`
    becomes the route `auth/login/` while `auth/__init__.py` (if present)
    binds to `auth/` itself.

    Folder/file names are used verbatim as URL path segments, so Django path
    converters can be embedded directly in a name, e.g.
    `views/user/<str:identifier>/__init__.py` becomes the route
    `user/<str:identifier>/`.

    Each module may declare at most one `BaseAPIView` subclass; one with
    none is treated as a pure namespace (a folder with no `__init__.py`
    view still has its subfolders/files walked; a `.py` file with no view
    is simply skipped).

    Args:
        root (Path): The folder to walk.
        url_prefix (str): The URL path accumulated from parent folders.

    Returns:
        list[URLPattern | URLResolver]: The generated urls.
    """
    urlpatterns: list[URLPattern | URLResolver] = []

    init_file = root / "__init__.py"
    if init_file.is_file():
        url_pattern = _bind_leaf(init_file, url_prefix)
        if url_pattern is not None:
            urlpatterns.append(url_pattern)

    for entry in sorted(root.iterdir()):
        if entry.is_dir() and (entry / "__init__.py").is_file():
            urlpatterns.extend(
                build_folder_urls(entry, url_prefix=f"{url_prefix}{entry.name}/")
            )
            continue

        if entry.is_file() and entry.suffix == ".py" and entry.name != "__init__.py":
            url_pattern = _bind_leaf(entry, f"{url_prefix}{entry.stem}/")
            if url_pattern is not None:
                urlpatterns.append(url_pattern)

    return urlpatterns
