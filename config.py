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
