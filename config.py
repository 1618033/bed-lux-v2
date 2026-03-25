import ujson as json  # Use 'ujson' in MicroPython
import logging

from defs import *

log = logging.getLogger("[CFG]")

class JSONConfig:
    def __init__(self, path: str = 'cfg.json', default: Optional[Dict[str, Any]] = None) -> None:
        self.path: str = path
        self.data: Dict[str, Any] = default if default else {}

    def load(self) -> Dict[str, Any]:
        try:
            with open(self.path, 'r') as f:
                cfg_file = json.load(f)
                self.data.update(cfg_file)
        except OSError:
            log.exception("Config file '%s' not found. Using defaults." % self.path)
        except ValueError:
            log.exception("Failed to decode JSON in '%s'. Using defaults." % self.path)
        return self.data

    def save(self) -> None:
        try:
            with open(self.path, 'w') as f:
                json.dump(self.data, f)
            log.debug("Config saved to '%s'." % self.path)
        except Exception as e:
            log.exception("Failed to save config: %s" % e)

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def delete(self, key: str) -> None:
        if key in self.data:
            del self.data[key]

    def clear(self) -> None:
        self.data.clear()

    def json(self) -> str:
        try:
            return json.dumps(self.data)
        except OSError:
            log.exception("Config file '%s' not found. Using defaults." % self.path)
        except ValueError:
            log.exception("Failed to decode JSON in '%s'. Using defaults." % self.path)
        return "{}"


    def merge_config(self, patch: str) -> Dict[str, Any] | None:
        try:
            config_patch = json.loads(patch)
        except UnicodeDecodeError as e:
            log.exception("Invalid config payload encoding: %s" % e)
            return None
        except ValueError as e:
            log.exception("Invalid config JSON payload: %s" % e)
            return None

        if not isinstance(config_patch, dict):
            log.error("BLEC_CMD_SETCFG: payload must be a JSON object")
            return None

        try:
            merged_config = json.loads(self.json())
            if not isinstance(merged_config, dict):
                raise ValueError("Current config is not a JSON object")

            merged_config.update(config_patch)

            for key, value in merged_config.items():
                self.set(key, value)

            self.save()
            return merged_config
        except Exception as e:
            log.exception("Error saving config: %s" % e)
            return None
