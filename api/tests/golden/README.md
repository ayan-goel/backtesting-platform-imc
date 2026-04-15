# Golden fidelity tests vs prosperity3bt

Status: **deferred to Phase 2**.

`prosperity3bt` targets the Prosperity 3 data format. Prosperity 4's column layout
(`day;timestamp;product;bid_price_1;...;ask_price_3;ask_volume_3;mid_price;profit_and_loss`)
differs from what `prosperity3bt` expects, and the tool does not expose an easy way to
override the schema.

Rather than spend Phase 1 time wrestling with a P3-era tool to make it accept P4 data,
we rely on:
  - Our own unit tests for matching, limits, PnL, and snapshot building
  - An end-to-end smoke run of a synthetic no-op Trader that produces the expected
    event count on tutorial day -2 (see tests/engine/test_runner.py)

Follow-up for Phase 2: either fork prosperity3bt to accept the P4 schema, or write a
synthetic-data parity test against a known-closed-form strategy (buy-and-hold, e.g.)
so we have a cross-reference number.
