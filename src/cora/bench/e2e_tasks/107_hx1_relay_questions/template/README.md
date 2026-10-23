# relay

`relay` is a small store-and-forward message relay. Producers hand messages to the
relay, which keeps them in a spool directory until a downstream receiver accepts
them. Failed deliveries are retried with exponential backoff. A small HTTP API lets
operators look up messages, and a command line tool offers the same lookups plus
queue inspection.

## Layout

- `relay/config/` loads settings from defaults, an optional settings file and
  environment variables.
- `relay/transport/` holds the delivery side: retry arithmetic, the retry decision
  and a simulated sender.
- `relay/api/` holds error types, request handlers and the routing table.
- `relay/queue/` holds the in-memory queues that feed the sender.
- `relay/storage/` writes spooled messages to disk and keeps an index.
- `relay/metrics/` counts events and measures durations.
- `relay/cli/` is the command line front end.
- `relay/util/` has small helpers shared by the other packages.

## Design notes

Settings are plain values. Nothing reads the environment except the loader, and the
loader only reads variables that are named in the override table. Delivery code
never talks to the network directly; the transport layer receives a callable that
does the actual send, which keeps the relay testable without sockets.

Errors raised by the API layer carry a message and are mapped to HTTP status codes
in one table. Handlers never build status codes by hand.

## Running

The package uses only the standard library. Import `relay` from the workspace root.
There is no install step.
