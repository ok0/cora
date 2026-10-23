"""Mapping of country codes to shipping zones."""

ZONE_BY_COUNTRY = {"DE": "eu", "FR": "eu", "NL": "eu", "KR": "world", "US": "world"}


def zone_for(country: str) -> str:
    """Return the shipping zone of a country code; unknown countries are 'world'."""
    return ZONE_BY_COUNTRY.get(country.upper(), "world")
