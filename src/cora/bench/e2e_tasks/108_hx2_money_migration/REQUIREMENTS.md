# Migrate off the deprecated rounding helper

`round_money` is deprecated. Migrate every use of it in the `shop` package to `quantize` from
the package's money module: compute with `Decimal` (inputs may be `str`, `int` or `Decimal`)
and return `Decimal` amounts rounded half-up to cents; text output uses two decimals. Keep
`round_money` itself (other projects still import it). After the change no module except the
one that defines `round_money` may reference it, and calling any public function of the
package must not emit `DeprecationWarning`.

`python -m pytest -q` runs a partial test suite; passing it is necessary but not sufficient.
