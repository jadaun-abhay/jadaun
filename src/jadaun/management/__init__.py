import functools
import os
from collections.abc import Sequence

from django.apps import apps
from django.conf import settings
from django.core import management as core_management
from django.core.management import find_commands

from jadaun.initializer.apps import AppConfig


@functools.cache
def get_commands_with_base() -> dict[str, str]:
    """Generates a mapping of command name along side the app name that command belongs to

    Returns:
        dict[str, str]: Mapping of command_name and app_name
    """

    commands: dict[str, str] = {
        name: "django.core" for name in find_commands(core_management.__path__[0])
    }

    if not settings.configured:
        return commands

    commands.update({name: "jadaun" for name in find_commands(__path__[0])})

    app_configs: Sequence[AppConfig] = apps.get_app_configs()
    for app_config in reversed(app_configs):
        app_managemnet_dir_path: str = os.path.join(app_config.path, "management")
        commands.update(
            {name: app_config.name for name in find_commands(app_managemnet_dir_path)}
        )

    return commands
