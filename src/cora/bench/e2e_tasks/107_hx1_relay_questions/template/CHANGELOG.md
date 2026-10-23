# Changelog

## 0.4.2

- Settings are now read through one loader that merges defaults, the optional
  settings file and environment overrides.
- The retry decision lives in a single function so that every caller agrees on
  which failures are transient.
- Error types carry a `transient` flag instead of ad hoc checks in the sender.

## 0.4.1

- Added the metrics counters and timers used by the command line status view.
- Queue draining now respects the configured batch size.

## 0.4.0

- Storage writes spool files atomically through a temporary name and a rename.
- Routing moved into its own table so new endpoints do not touch handlers.
- Command line output helpers were split out of the main command module.

## 0.3.0

- First version with a retry schedule and exponential backoff.
- Message lookups over HTTP.
