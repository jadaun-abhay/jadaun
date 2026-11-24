from typing import Any

import yaml


class ConfigParser:
    config_file = "jadaun.config.yaml"

    def __init__(self, config_file: str | None = None) -> None:
        if config_file is not None:
            self.config_file = config_file

    def load_config(self) -> None:
        with open(file=self.config_file, encoding="utf-8") as config_file:
            config: dict[str, Any] = yaml.safe_load(config_file)
            self.config = config
