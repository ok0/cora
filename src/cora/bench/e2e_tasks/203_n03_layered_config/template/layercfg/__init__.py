from layercfg.config import Config
from layercfg.errors import ConfigError
from layercfg.interp import resolve
from layercfg.layers import merge
from layercfg.parser import parse


def load(defaults: dict[str, dict[str, str]], text: str, env: dict[str, str]) -> Config:
    return Config(resolve(merge(defaults, parse(text), env)))


__all__ = ["Config", "ConfigError", "load"]
