# Fix Unsafe API Retries

## Goal

Stop the HTTP client from sending duplicate POST requests after a transient
timeout.

## Final Outcome

Automatic retries now apply only to idempotent methods. POST requests are
retried only when the caller supplies an idempotency key.

## Key Commands

- python3 -m pytest tests/test_retry_policy.py -q
- python3 -m ruff check src tests

## Tests / Verification

The retry policy tests cover GET, POST without an idempotency key, and POST with
an idempotency key. All tests passed.

## User Notes

Keep the retry rule and its reason.

## Things Not To Record

Do not promote temporary logging or failed library experiments into project
guidance.

## AI Conversation Summary

The developer and coding agent traced duplicate writes to a generic retry loop,
changed the policy, and added regression tests. A future change to the HTTP
client should preserve the idempotency rule.
