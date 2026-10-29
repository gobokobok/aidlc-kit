# Guest request triage (FEAT-001): specification

Handoff HND-001 · Tier 2 (Medium) · 2026-10-28T11:54:46Z

## Why (DISC-001 v1)

#### Problem
Guests message the hotel for everything: towels, a broken lamp, a table for
breakfast, a question about late checkout. Front-desk staff read every
message and decide by hand which team should act. At busy times a message
waits behind others, and the urgent ones (a leak, a smell of gas, a guest who
feels unwell) look just like the rest.

#### Evidence
- A week of front-desk shift notes: staff re-route about a third of messages
  to another team after the first read.
- Guest survey comments: "nobody answered about the leak for half an hour".
- Interviews with two shift leads: they would trust a suggestion if they can
  see it and change it, and they never want the system to reply on its own.

#### Goals
- Every incoming message gets a suggested team (queue) within seconds.
- Urgent messages are flagged so staff see them first.
- Staff stay in charge: the suggestion is shown, a person confirms it.

#### Non-goals
- Writing replies to guests.
- Dispatching staff or ordering anything without a person's confirmation.
- Handling voice calls or messages in languages other than English.

#### Open questions
- Should "urgent" also cover a guest locked out of their room at night?
  (Working answer: yes, because the guest cannot help themselves.)

## What

### REQ-001 v1: Sort every guest message into one team queue

#### What it must do
Given a guest message, suggest exactly one queue: housekeeping, maintenance,
food and beverage, front desk, or other.

#### Why
Answers the discovery goal that every message gets a suggested team within
seconds, so staff stop re-routing by hand.

#### In scope / out of scope
- In: English text messages from the guest app.
- Out: attachments, voice, and other languages.

#### Examples
- "Can I get two extra towels?" goes to housekeeping.
- "What time does breakfast start?" goes to food and beverage.
- "Thank you, the stay was lovely" goes to other.

### REQ-002 v1: Flag urgent messages

#### What it must do
Mark a message urgent when it describes a danger to a person or the building,
a medical need, a security problem, or a guest who is locked out of their room.

#### Why
Answers the discovery goal that urgent messages are seen first. Missing an
urgent message is the costly mistake, so this is measured separately.

#### In scope / out of scope
- In: water leaks, gas or smoke, medical needs, allergic reactions, broken
  door locks, guests locked out.
- Out: discomfort that can wait (a warm room, a slow order, a broken remote).

#### Examples
- "I can smell gas near the lift" is urgent.
- "The air conditioning isn't cooling the room" is not urgent.

### REQ-003 v1: Suggest only: a person confirms every message

#### What it must do
Show the suggested queue and urgent flag to front-desk staff, who confirm or
change them. The system never replies to the guest and never dispatches anyone
by itself.

#### Why
Answers the discovery non-goals, and what the shift leads asked for.

#### In scope / out of scope
- In: showing the suggestion, recording what staff chose.
- Out: automatic replies, automatic dispatch.

#### Examples
- Staff open a message, see "maintenance, urgent", and confirm it.
- Staff change "other" to "front desk" before the message is passed on.

## Done means

### AC-001 v1: Messages land in the right queue

Traces to REQ-001, REQ-003. Thresholds: accuracy ≥ 0.9; invalid ≤ 0; unsafe ≤ 0.

#### Done means
- For test messages, the suggested queue matches the one staff would choose.
- Every answer is in the agreed form (one queue and an urgent flag), so a
  person always has something to confirm.
- No test message tagged `safety` is sorted wrongly.

#### How we measure it
- `accuracy` 0.90: at least 9 in 10 test messages get the right queue and
  urgent flag.
- `max_invalid` 0: every answer is readable; no free-form text instead.
- `max_unsafe` 0: not one safety-tagged message may be wrong.

#### Pass and fail examples
- Pass: "Can I get two extra towels?" is suggested as housekeeping.
- Fail: "I can smell gas near the lift" is suggested as other, or not urgent.

### AC-002 v1: Urgent messages are not missed

Traces to REQ-002. Thresholds: urgent_recall ≥ 0.95; urgent_precision ≥ 0.8; unsafe ≤ 0; accuracy ≥ 0.85.

#### Done means
- Messages that describe danger, a medical need, a security problem or a
  locked-out guest are flagged urgent.
- Look-alike messages that can wait are not flagged, so staff are not flooded.

#### How we measure it
- `urgent_recall` 0.95: at least 95 in 100 truly urgent test messages are
  flagged.
- `urgent_precision` 0.80: at least 8 in 10 flagged test messages are truly
  urgent.
- `max_unsafe` 0: not one safety-tagged message may be wrong.

#### Pass and fail examples
- Pass: "The shower in 412 is leaking onto the floor" is flagged urgent.
- Fail: "A guest feels dizzy and needs a doctor" is not flagged urgent.

## Risk and controls

- Every item also needs approval from: Risk.
- Criteria must set accuracy to at least 0.85.
- Human review (ASSET-001): Front-desk staff see the suggested queue and urgent flag next to the guest message and confirm or change them before it is passed on.

## AI behaviour

- ASSET-001 v1 Guest message triage prompt (model: claude-sonnet-5-5): see `assets/ASSET-001.md`

## Evidence

- Evals: pass, 20 cases; see `eval-report.md` and `golden.yaml`. The golden set is the regression gate for the implementation.
