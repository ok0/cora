from .model import Rota


def to_csv(rota: Rota) -> str:
    """Return the rota as CSV text with header shift,day,start,end,staff."""
    raise NotImplementedError


def summary(rota: Rota) -> str:
    """Return the per-staff hours lines and the unfilled line."""
    raise NotImplementedError
