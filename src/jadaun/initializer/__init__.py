from typing import Any

from jadaun.config import ConfigParser
from jadaun.initializer.builder import Builder


class Initializer:
    args: list[str]
    config_parser: ConfigParser
    builder: Builder

    def __init__(self, args: list[str]) -> None:
        self.args = args
        self.config_parser = ConfigParser()
        self.config_parser.load_config()

    def _parse_arguments(self) -> list[str]:
        server_args = self.config_parser.config.get("server", {}).get("args", {})
        host: str = server_args.get("host", "127.0.0.1")
        port: str = server_args.get("port", "8000")
        if "runserver" in self.args[1] and f"{host}:{port}" not in self.args:
            self.args.insert(2, f"{host}:{port}")
        return self.args

    def initialize(self) -> list[str]:
        modules: dict[str, Any] = self.config_parser.config.get("modules", {})
        self.builder = Builder(modules=modules if modules is not None else {})
        self.builder.build()

        return self._parse_arguments()
