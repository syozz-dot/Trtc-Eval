# sample-data — Default Demo Data

`faq-sample.json` contains 5 industry-neutral FAQ entries, matching the structure of `capabilities/knowledge-base/src/core/models.py.FaqEntry`:

```json
{
  "id":       "string, primary key",
  "question": "string",
  "answer":   "string",
  "keywords": "string[]",
  "source":   "string, optional; used for dashboard display of data origin"
}
```

**Top-level is an array** (aligned with the format expected by `LocalJsonKbClient.reload()`).

## How to Enable

Switch KB to the `local_json` adapter and point it to this file:

```env
# capabilities/conversation-core/.env
KB_ADAPTER=local_json
KB_DATA_FILE=scenarios/customer-service/sample-data/faq-sample.json
```

Or, during Path A demo, keep the default `KB_ADAPTER=mock` (the mock adapter has equivalent 5 built-in demo FAQ entries).

## Before Going Live

1. Replace this file with real business FAQ content (or create a new file and point `KB_DATA_FILE` to it);
2. Alternatively, switch to the `default_rest` adapter to connect to an external FAQ service — configure per `capabilities/knowledge-base/INTERFACE_ADAPT.md`; then this directory is no longer needed.
