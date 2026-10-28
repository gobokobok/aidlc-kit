# Sort every guest message into one team queue

## What it must do
Given a guest message, suggest exactly one queue: housekeeping, maintenance,
food and beverage, front desk, or other.

## Why
Answers the discovery goal that every message gets a suggested team within
seconds, so staff stop re-routing by hand.

## In scope / out of scope
- In: English text messages from the guest app.
- Out: attachments, voice, and other languages.

## Examples
- "Can I get two extra towels?" goes to housekeeping.
- "What time does breakfast start?" goes to food and beverage.
- "Thank you, the stay was lovely" goes to other.
