"""VAT rate per region code."""

VAT_RATES = {"DE": "0.19", "FR": "0.20", "NL": "0.21", "US": "0.00"}


def rate_for(region: str) -> str:
    """Return the VAT rate of a region code; unknown regions get zero rate."""
    return VAT_RATES.get(region.upper(), "0.00")
