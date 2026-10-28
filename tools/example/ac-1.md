# Messages land in the right queue

## Done means
- For test messages, the suggested queue matches the one staff would choose.
- Every answer is in the agreed form (one queue and an urgent flag), so a
  person always has something to confirm.
- No test message tagged `safety` is sorted wrongly.

## How we measure it
- `accuracy` 0.90: at least 9 in 10 test messages get the right queue and
  urgent flag.
- `max_invalid` 0: every answer is readable; no free-form text instead.
- `max_unsafe` 0: not one safety-tagged message may be wrong.

## Pass and fail examples
- Pass: "Can I get two extra towels?" is suggested as housekeeping.
- Fail: "I can smell gas near the lift" is suggested as other, or not urgent.
