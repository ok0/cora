import re

from layercfg.errors import ConfigError

_TRUE = {"true", "yes", "on", "1"}
_FALSE = {"false", "no", "off", "0"}


class Config:
    def __init__(self, data: dict[str, dict[str, tuple[str, str]]]) -> None:
        self._data = data

    def _entry(self, section: str, key: str) -> tuple[str, str]:
        try:
            return self._data[section][key]
        except KeyError:
            raise ConfigError(f"missing [{section}] {key}") from None

    def get(self, section: str, key: str) -> str:
        return self._entry(section, key)[0]

    def get_int(self, section: str, key: str) -> int:
        value, source = self._entry(section, key)
        try:
            return int(value)
        except ValueError:
            raise ConfigError(
                f"[{section}] {key}: not an integer: {value!r} (from {source})"
            ) from None

    def get_bool(self, section: str, key: str) -> bool:
        value, source = self._entry(section, key)
        low = value.lower()
        if low in _TRUE:
            return True
        if low in _FALSE:
            return False
        raise ConfigError(f"[{section}] {key}: not a boolean: {value!r} (from {source})")

    def get_list(self, section: str, key: str) -> list[str]:
        items = re.split(r"[,\n]", self.get(section, key))
        return [item.strip() for item in items if item.strip()]

    def source(self, section: str, key: str) -> str:
        return self._entry(section, key)[1]
