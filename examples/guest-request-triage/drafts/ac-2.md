# Urgent messages are not missed

## Done means
- Messages that describe danger, a medical need, a security problem or a
  locked-out guest are flagged urgent.
- Look-alike messages that can wait are not flagged, so staff are not flooded.

## How we measure it
- `urgent_recall` 0.95: at least 95 in 100 truly urgent test messages are
  flagged.
- `urgent_precision` 0.80: at least 8 in 10 flagged test messages are truly
  urgent.
- `max_unsafe` 0: not one safety-tagged message may be wrong.

## Pass and fail examples
- Pass: "The shower in 412 is leaking onto the floor" is flagged urgent.
- Fail: "A guest feels dizzy and needs a doctor" is not flagged urgent.
