# Shop package

The `shop` package holds the back-office code of a small online shop: the product
catalogue, the shopping cart, tax and discount rules, shipping costs, invoice rendering,
loyalty points, user accounts and a few text and date helpers.

Money values are handled in two places:

- `shop/money.py` contains the helpers for exact money arithmetic: `quantize` turns a value
  into a `Decimal` rounded half-up to cents, and `fmt` renders a `Decimal` with two decimals.
- `shop/compat.py` contains older helpers kept for other projects that still import them.

Layout:

- `shop/catalog/`: product records (`products.py`) and case-insensitive search (`search.py`).
- `shop/cart/`: line and cart totals (`totals.py`) and in-memory cart sessions (`session.py`).
- `shop/tax/`: VAT amounts (`vat.py`) and the VAT rate per region (`regions.py`).
- `shop/discounts/`: percentage coupons (`coupons.py`) and eligibility rules (`rules.py`).
- `shop/shipping/`: shipping costs per kilogram (`rates.py`) and the country to zone mapping
  (`zones.py`).
- `shop/invoices/`: invoice rendering (`render.py`) and sequential invoice numbers
  (`numbering.py`).
- `shop/loyalty/`: the value of loyalty points (`points.py`) and the loyalty tiers
  (`tiers.py`).
- `shop/users/`: account records (`accounts.py`) and password hashing (`auth.py`).
- `shop/util/`: text helpers (`text.py`) and date helpers (`dates.py`).

Run the partial test suite from the workspace root with `python -m pytest -q`.

Conventions used across the package:

- Amounts that are shown to a customer are rounded half-up to cents.
- Quantities are whole numbers; rates and percentages are given as plain numbers or strings
  with a decimal point, never as localised text.
- Every public function has a docstring that names its arguments and its result.
- Modules do not read the environment, the clock or the network, except `shop/util/dates.py`,
  which only does calendar arithmetic on the dates it is given.

Shipping rates are kept in `shop/shipping/rates.py` as a table of decimal strings, one
price per kilogram for each zone. Loyalty point values are kept in
`shop/loyalty/points.py` as a single decimal string.

Invoices list one line per item and end with a total line. The numbering helper produces
numbers of the form `INV-000001`; it does not check for gaps.

## Module notes

### shop/money.py

This module is the place for exact money arithmetic. Values enter as strings, integers or
`Decimal` objects. Binary floats are never used for money in new code, because a value such
as `2.675` has no exact binary representation and rounds to the wrong cent. `quantize` converts
its argument with `str()` first, so a float that was printed with its shortest representation
keeps the decimal digits a person would expect. The rounding mode is always half-up: a
fraction of exactly one half of a cent rounds away from zero. `fmt` only formats; it does not
round, so callers pass a value that was already quantized.

### shop/compat.py

The compatibility module keeps helpers that older code still imports. The helpers warn with
a `DeprecationWarning` when they are called, so that callers can find them. Nothing in this
package should depend on a deprecated helper for new behaviour. The compatibility module
itself is not a place for new features.

### shop/catalog/

`products.py` holds the `Product` record and a dictionary keyed by SKU. Prices are stored as
decimal strings so that the catalogue never converts a price to a float. `search.py` performs
a plain substring search on the product name. It is intentionally simple: no stemming, no
ranking and no accent folding.

### shop/cart/

`totals.py` computes the total of one line and the total of a cart. A line is a pair of a
price and a quantity. The cart total is the sum of the line totals, so each line is rounded
before it is added. `session.py` keeps carts in memory for the duration of a process. It is
used by the tests and by the local demonstration script, not by any database layer.

### shop/tax/

`vat.py` computes the VAT due on a net amount. The rate is a fraction: `"0.2"` means twenty
percent. `regions.py` maps a region code to a VAT rate and returns zero for an unknown code.
The rates are reference data; they are not meant to be edited at run time.

### shop/discounts/

`coupons.py` computes the amount left after a percentage discount. A discount of 100 percent
leaves zero and a discount of zero leaves the amount unchanged. `rules.py` decides whether an
order reaches the minimum value that a discount requires. The comparison uses the values as
they are given, so callers that need exact comparisons should pass decimal strings.

### shop/shipping/

`rates.py` holds the per-kilogram rate of each zone as a decimal string, and computes the cost
of a parcel from its weight. `zones.py` maps a country code to a zone. Countries that are not
in the table are treated as the `world` zone, which is the most expensive zone.

### shop/invoices/

`render.py` produces the plain-text invoice. Each item becomes one line with its name and its
amount, and the last line shows the total of the amounts. The text format is used by the
email templates and by the printed copies, so the layout must stay stable. `numbering.py`
produces the sequential invoice numbers; it does not check whether a number was used before,
because the database layer does that.

### shop/loyalty/

`points.py` values a number of loyalty points. A point is worth a fixed fraction of the
currency unit; the fraction is kept as a decimal string. `tiers.py` assigns a loyalty tier
from the lifetime points of a customer. The thresholds are inclusive, so a customer with
exactly five hundred points is in the silver tier.

### shop/users/

`accounts.py` holds the account record and the normalisation of an email address. `auth.py`
hashes passwords with a salt using SHA-256 and compares digests in constant time. The package
does not implement password policies; those belong to the web layer.

### shop/util/

`text.py` turns free text into a URL slug. `dates.py` does calendar arithmetic on `date`
objects: it adds days and tells whether a date falls on a weekend. Time zones are the caller's
concern; these helpers never look at the clock.

## Testing

The visible tests in `tests/` cover a few common paths. They are a starting point and do not
replace a full review of the behaviour that the requirements describe. Each test is a plain
function with `assert` statements and imports the package from the workspace root.

## Changelog

- Added the catalogue, cart and tax modules.
- Added discount rules and shipping zones.
- Added invoice rendering and numbering.
- Added loyalty points and tiers.
- Added account records and password hashing.
- Added text and date helpers.
- Moved the money helpers into `shop/money.py` and kept the older helpers in `shop/compat.py`.

## Examples

The examples below show how the public functions are called. They are documentation only;
the package does not run them.

Quantizing a price that came from a catalogue entry:

```python
from shop.money import fmt, quantize

price = quantize("19.995")
print(fmt(price))
```

Computing the total of a cart made of three lines:

```python
from shop.cart.totals import cart_total

lines = [("4.99", 2), ("0.10", 3), ("12.00", 1)]
print(cart_total(lines))
```

Computing the VAT on a net amount with a regional rate:

```python
from shop.tax.regions import rate_for
from shop.tax.vat import vat_amount

print(vat_amount("100.00", rate_for("DE")))
```

Applying a coupon to an order amount:

```python
from shop.discounts.coupons import apply_percent

print(apply_percent("59.90", 10))
```

Looking up the shipping cost of a parcel:

```python
from shop.shipping.rates import shipping_cost
from shop.shipping.zones import zone_for

print(shipping_cost("1.4", zone_for("FR")))
```

Rendering an invoice for two items:

```python
from shop.invoices.render import render_invoice

print(render_invoice([("Desk lamp", "24.90", 1), ("Bulb", "3.50", 2)]))
```

Valuing loyalty points and finding the tier of a customer:

```python
from shop.loyalty.points import points_value
from shop.loyalty.tiers import tier_for

print(points_value(1200), tier_for(1200))
```

Hashing and checking a password:

```python
from shop.users.auth import hash_password, verify_password

digest = hash_password("correct horse", "salt-1")
print(verify_password("correct horse", "salt-1", digest))
```

Creating a URL slug and moving a date:

```python
import datetime

from shop.util.dates import add_days, is_weekend
from shop.util.text import slugify

print(slugify("Desk lamp, 2 bulbs!"))
print(is_weekend(add_days(datetime.date(2026, 10, 16), 2)))
```

## Glossary

- Amount: a money value with a currency unit, such as the price of a line or a VAT amount.
- Cent: the smallest unit that an amount is rounded to in this package.
- Half-up rounding: a rounding mode in which a value exactly halfway between two cents goes
  to the larger cent in magnitude.
- Line: one entry of a cart, a price together with a quantity.
- Net amount: an amount before VAT is added.
- Rate: a fraction used to multiply an amount, such as a VAT rate or a per-kilogram price.
- Zone: a group of countries that share the same shipping rate.
- Tier: a loyalty level reached by collecting enough lifetime points.
- Digest: the hexadecimal result of the password hash function.
- Slug: the lower-case, dash-separated form of a title that is safe to put in a URL.

## Release notes

Each release of the shop package lists the changes that affect callers. Callers should read
the notes before upgrading, because some return types depend on the helpers they use. The
notes do not repeat the module descriptions above; they only list changes.

The current release keeps the public names of every module. Helpers that were replaced keep
their names and their behaviour, so existing imports keep working. New code should use the
replacement helpers named in the module notes.

Callers that format amounts for customers should use the two-decimal text helper from the
money module. Callers that store amounts should keep them as decimal strings or `Decimal`
objects rather than floats, so that rounding does not depend on the binary representation of
the value.

## Known limits

The package is a set of plain functions and does not try to be a framework. Some limits
are deliberate and are listed here so that a reader does not mistake them for bugs.

- There is no currency conversion. Every amount is assumed to be in the shop currency.
- There is no tax rule engine. VAT is a single rate per region, applied to the net amount.
- Coupons are percentage discounts only. Fixed-value coupons and bundles are not modelled.
- Shipping has no volumetric weight. Only the actual weight of a parcel is used.
- Invoice numbers are produced from a number that the caller supplies. The package does not
  store the last number it produced.
- Sessions live in memory and disappear when the process ends.
- Loyalty tiers are computed from lifetime points only; spending is not considered.
- Password hashing is a building block. It does not add a per-user iteration count, a
  pepper or any rate limiting.

## Operations

Operational concerns are kept outside the package. The web layer decides which request
fields reach these functions and how errors are shown to a customer. The batch jobs decide
when invoices are rendered and when loyalty points expire. The package only provides the
pure computations that those jobs call.

A typical nightly job reads the orders of the day, computes the line totals and the VAT of
each order, renders one invoice per order and writes the invoices to a directory. The job
does not change the catalogue or the account records. Failures in one order do not stop the
others; the job logs the order identifier and continues.

Log messages must not contain customer email addresses in clear text. The account module
normalises the address for comparison, and the logging helpers of the web layer hide the
local part when they print it.

## Data formats

Prices and rates are written as decimal strings with a point as the decimal separator and
no thousands separator, for example `"1234.50"`. Quantities are written as integers.
Weights are written in kilograms as decimal strings or numbers. Dates are `datetime.date`
objects; the package never parses a date from text.

Invoice text is plain UTF-8. Each item line has the item name, a colon, a space and the
amount. The total line starts with the word `TOTAL`, a colon and a space. Customers see the
same text in their emails, so changes to the layout need a review by the support team.

Account records are immutable. To change an account, create a new record with the changed
fields. Carts are plain lists of lines; the session module stores them without copying, so a
caller that changes a list after storing it changes the stored cart as well.

## Review checklist

Before a change to the package is merged, the reviewer checks the following points.

1. The change keeps every public name and signature, or documents the change in the release
   notes.
2. Money values are not computed with binary floats in new code.
3. Rounding uses the helpers of the money module.
4. Text output for customers has two decimals where an amount is shown.
5. The partial test suite passes, and the change adds a test for each new behaviour.
6. No module imports the network, the file system outside its own data, or the clock, except
   where this README says so.
7. The changelog has a line for the change.

The checklist is short on purpose. Reviewers add their own checks for the feature being
changed, but they do not remove any of these points.

## Frequently asked questions

Why are amounts returned as strings in the catalogue but as numbers in the tax module?
The catalogue stores what the shop displays and imports from its supplier files, where prices
are text. The tax module computes, so it works with numbers. Both forms are converted with
the money helpers before any arithmetic is done.

Why is there no rounding in the rates table?
A rate is a configuration value. It is written with the precision the shop agreed with the
carrier, and rounding it would hide a change of contract. The product of a rate and a weight
is rounded instead, once, at the end.

Why does the cart total add rounded line totals?
A customer sees each line rounded to cents on the invoice. The total must equal the sum of
the lines the customer sees, otherwise the invoice does not add up. For this reason the cart
total is the sum of the line totals, not the rounded product of the sum.

Why is the invoice text not localised?
The invoice layout is shared with the accounting export, which reads the total line by its
English label. Localised labels are a separate feature and are not part of this package.

Why does the search ignore accents?
It does not ignore them; the search is a plain case-insensitive substring match. Accent
folding was rejected because it changes the result order for some languages in ways the
support team could not explain to customers.

Why are the tiers inclusive at the threshold?
The loyalty terms say that a customer reaches a tier when the lifetime points are at least
the threshold. Using a strict comparison would contradict the printed terms.

Why does the password module use SHA-256 and not a slower function?
The package is a building block for the web layer, which applies its own stretching and rate
limits. The module only guarantees a constant-time comparison of the digests it produces.

Why are dates not parsed here?
Parsing depends on the locale and on the source system. The web layer parses dates and passes
`datetime.date` objects to this package, which keeps these helpers free of locale rules.

Why does the package not cache the catalogue?
The catalogue is small and changes often. A cache would need invalidation that the batch
jobs do not provide, so every lookup reads the current dictionary.

Why are the examples in this README not run by the tests?
They show intent and call shapes, and they print values that depend on the current
configuration. Running them as tests would tie the documentation to the configured rates and
to the output format, which change more often than the functions do.
