import argparse
import os
import shutil
import sys
from typing import override

import django
from django.conf import settings
from django.core.management.base import CommandError
from django.core.management.templates import TemplateCommand
from django.core.management.utils import handle_extensions
from django.template import Context, Engine, Template
from django.utils.version import get_docs_version

# Friendly `--template` shorthands, in the order they're offered interactively.
TEMPLATE_CHOICES = {
    "package": (
        "package_based_template",
        "Package-based - views/ as a folder (folder-based routing)",
    ),
    "module": (
        "module_based_template",
        "Module-based - views.py as a single file",
    ),
}


class Command(TemplateCommand):
    help = (
        "Creates a Django app directory structure for the given app name, "
        "nested under extra leading namespace segments if given, e.g. "
        "`startapp generator core` creates app `core` inside a `generator` "
        "namespace package under the configured apps directory. Run with no "
        "arguments for an interactive prompt."
    )
    missing_args_message = "You must provide an application name."

    @override
    def add_arguments(self, parser):
        parser.add_argument(
            "name",
            nargs="*",
            help=(
                "Name of the app to create, e.g. `core` or `generator core` "
                "(or `generator/core`). Extra leading segments are treated "
                "as namespace folders it's nested under. Omit entirely to "
                "be prompted interactively."
            ),
        )
        parser.add_argument(
            "--template",
            help=(
                "Template to use: 'package' (folder-based views, default), "
                "'module' (single views.py), or a custom path/URL."
            ),
        )
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="Never prompt; fail instead of asking for missing info.",
        )
        parser.add_argument(
            "--extension",
            "-e",
            dest="extensions",
            action="append",
            default=["py"],
            help='The file extension(s) to render (default: "py"). '
            "Separate multiple extensions with commas, or use "
            "-e multiple times.",
        )
        parser.add_argument(
            "--name",
            "-n",
            dest="files",
            action="append",
            default=[],
            help="The file name(s) to render. Separate multiple file names "
            "with commas, or use -n multiple times.",
        )
        parser.add_argument(
            "--exclude",
            "-x",
            action="append",
            default=argparse.SUPPRESS,
            nargs="?",
            const="",
            help=(
                "The directory name(s) to exclude, in addition to .git and "
                "__pycache__. Can be used multiple times."
            ),
        )

    @override
    def validate_name(self, name: str, name_or_dir: str = "name") -> None:
        if name == "":
            raise CommandError(f"{name_or_dir.capitalize()} cannot be empty.")
        super().validate_name(name, name_or_dir)

    def _is_interactive(self, no_input: bool) -> bool:
        return not no_input and sys.stdin.isatty() and sys.stdout.isatty()

    def _style_func(self, role: str):
        """`getattr(self.style, role)`, without a static attribute lookup.

        Django's `Style` class (`django.core.management.color.Style`) is an
        empty class whose coloring methods (`WARNING`, `SUCCESS`,
        `MIGRATE_HEADING`, ...) are attached via `setattr` at runtime, so it
        has nothing for a type checker to see statically.
        """
        return getattr(self.style, role)

    def _styled(self, role: str, text: str) -> str:
        return self._style_func(role)(text)

    def _prompt_path(self) -> list[str]:
        self.stdout.write(self._styled("MIGRATE_HEADING", "New app"))
        while True:
            raw = input("  App name (e.g. core, or generator/core): ").strip()
            segments = [s for s in raw.replace("\\", "/").split("/") if s]
            if not segments:
                self.stdout.write(self._styled("WARNING", "  Name cannot be empty."))
                continue
            try:
                self.validate_name(name=segments[-1])
                for segment in segments[:-1]:
                    self.validate_name(name=segment, name_or_dir="directory")
            except CommandError as exc:
                self.stdout.write(self._styled("WARNING", f"  {exc}"))
                continue
            return segments

    def _prompt_template(self) -> str:
        choices = list(TEMPLATE_CHOICES.items())
        self.stdout.write(self._styled("MIGRATE_HEADING", "Template"))
        for index, (key, (_, description)) in enumerate(choices, start=1):
            marker = " (default)" if index == 1 else ""
            self.stdout.write(f"  {index}) {key} - {description}{marker}")
        while True:
            raw = input(f"  Select a template [1-{len(choices)}, default 1]: ").strip()
            if raw == "":
                return choices[0][0]
            if raw.isdigit() and 1 <= int(raw) <= len(choices):
                return choices[int(raw) - 1][0]
            if raw in TEMPLATE_CHOICES:
                return raw
            self.stdout.write(
                self._styled("WARNING", "  Please enter a valid number or template name.")
            )

    def _resolve_template(self, template: str | None, interactive: bool) -> tuple[str, str]:
        """Return (label, directory_or_url) for the chosen template."""
        if template is None:
            if interactive:
                template = self._prompt_template()
            else:
                template = next(iter(TEMPLATE_CHOICES))  # "package"

        if template in TEMPLATE_CHOICES:
            dirname, _ = TEMPLATE_CHOICES[template]
            template_dir = os.path.join(os.path.dirname(__file__), "..", "templates", dirname)
            return template, template_dir

        # Not a shorthand: treat as a raw path/URL, same as stock startapp.
        return template, template

    def _ensure_namespace_packages(self, apps_root: str, segments: list[str]) -> None:
        """Make sure every namespace folder a nested app lives under exists.

        Each is a plain importable package (just `__init__.py`), never a
        Django app - `AppRegistry.populate` treats any `submodules`-only
        config entry the same way, so these never need an `apps.py`.
        """
        current = apps_root
        for segment in segments:
            current = os.path.join(current, segment)
            os.makedirs(current, exist_ok=True)
            init_file = os.path.join(current, "__init__.py")
            if not os.path.exists(init_file):
                open(init_file, "w", encoding="utf-8").close()

    @override
    def handle(
        self,
        app_or_project: str = "app",
        name: list[str] | None = None,
        target=None,
        **options,
    ):
        self.app_or_project = app_or_project
        self.a_or_an = "an"
        self.paths_to_remove: list[str] = []
        self.verbosity: int = options.get("verbosity", 1)

        interactive = self._is_interactive(options.get("no_input", False))

        # Allow both `startapp generator core` and `startapp generator/core`.
        segments = [s for raw in (name or []) for s in raw.replace("\\", "/").split("/") if s]

        if not segments:
            if not interactive:
                raise CommandError(self.missing_args_message)
            segments = self._prompt_path()

        *namespace_segments, app_name = segments

        self.validate_name(name=app_name)
        for segment in namespace_segments:
            self.validate_name(name=segment, name_or_dir="directory")

        template_label, template = self._resolve_template(options.get("template"), interactive)

        # `DEFAULT_APPS_DIR` is read from the host project's Django settings
        # (with "apps" as the fallback), same as `AppRegistry.populate`.
        apps_root = os.path.join(os.getcwd(), getattr(settings, "DEFAULT_APPS_DIR", "apps"))
        top_dir = os.path.join(apps_root, *namespace_segments, app_name)

        if os.path.exists(top_dir):
            raise CommandError(f"{top_dir} already exists.")

        self._ensure_namespace_packages(apps_root, namespace_segments)

        try:
            os.makedirs(top_dir)
        except OSError as e:
            raise CommandError(e)

        extensions = tuple(handle_extensions(options["extensions"]))
        extra_files = []
        if self.verbosity >= 2:
            self.stdout.write(
                f"Rendering {app_or_project} template files with extensions: {', '.join(extensions)}"
            )
            self.stdout.write(
                f"Rendering {app_or_project} template files with filenames: {', '.join(extra_files)}"
            )

        context = Context(
            {
                **options,
                "app_name": app_name,
                "app_directory": top_dir,
                "camel_case_app_name": "".join(x for x in app_name.title() if x != "_"),
                "docs_version": get_docs_version(),
                "django_version": django.__version__,
            },
            autoescape=False,
        )

        # Setup a stub settings environment for template rendering
        if not settings.configured:
            settings.configure()
            django.setup()

        template_dir: str = self.handle_template(template, "app_template")
        prefix_length = len(template_dir) + 1

        for root, dirs, files in os.walk(template_dir):
            path_rest = root[prefix_length:]
            relative_dir = path_rest.replace("app_name", app_name)
            if relative_dir:
                target_dir = os.path.join(top_dir, relative_dir)
                os.makedirs(target_dir, exist_ok=True)

            for filename in files:
                old_path = os.path.join(root, filename)
                new_path = os.path.join(
                    top_dir, relative_dir, str.replace(filename, "app_name", app_name)
                )

                ((old_suffix, new_suffix),) = self.rewrite_template_suffixes
                if new_path.endswith(old_suffix):
                    new_path = new_path[: -len(old_suffix)] + new_suffix
                if os.path.exists(new_path):
                    raise CommandError(
                        f"{new_path} already exists. Overlaying {self.a_or_an} {app_or_project} into an existing "
                        "directory won't replace conflicting files."
                    )
                if new_path.endswith(extensions) or filename in extra_files:
                    with open(old_path, encoding="utf-8") as template_file:
                        content = template_file.read()
                    django_template: Template = Engine().from_string(content)
                    content: str = django_template.render(context)
                    with open(new_path, "w", encoding="utf-8") as new_file:
                        new_file.write(content)
                else:
                    shutil.copyfile(old_path, new_path)

                if self.verbosity >= 2:
                    self.stdout.write(f"Creating {new_path}")
                try:
                    self.apply_umask(old_path, new_path)
                    self.make_writeable(new_path)
                except OSError:
                    self.stderr.write(
                        f"Notice: Couldn't set permission bits on {new_path}. You're "
                        f"probably using an uncommon filesystem setup. No "
                        f"problem.",
                        self._style_func("NOTICE"),
                    )

        relative_top_dir = os.path.relpath(top_dir, os.getcwd())
        self.stdout.write(
            self._styled("SUCCESS", f"\nDone! Created app '{app_name}' at {relative_top_dir}/")
        )
        self.stdout.write(
            f"  Template: {template_label}\n"
            f"  Next: add '{'.'.join([*namespace_segments, app_name])}' under "
            "`modules` in your jadaun config file to wire up routing."
        )
