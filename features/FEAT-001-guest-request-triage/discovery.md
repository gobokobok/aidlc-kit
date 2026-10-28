---
id: DISC-001
type: discovery
feature: FEAT-001
title: Guests wait too long for a reply to simple requests
version: 1
status: approved
owner: alice
parents: []
approvals:
  - {by: dana, version: 1, at: '2026-10-28T10:38:00Z'}
  - {by: sam, version: 1, at: '2026-10-28T10:45:00Z'}
updated_at: 2026-10-28T09:14:00Z
---

# Guests wait too long for a reply to simple requests

## Problem
Guests message the hotel for everything: towels, a broken lamp, a table for
breakfast, a question about late checkout. Front-desk staff read every
message and decide by hand which team should act. At busy times a message
waits behind others, and the urgent ones (a leak, a smell of gas, a guest who
feels unwell) look just like the rest.

## Evidence
- A week of front-desk shift notes: staff re-route about a third of messages
  to another team after the first read.
- Guest survey comments: "nobody answered about the leak for half an hour".
- Interviews with two shift leads: they would trust a suggestion if they can
  see it and change it, and they never want the system to reply on its own.

## Goals
- Every incoming message gets a suggested team (queue) within seconds.
- Urgent messages are flagged so staff see them first.
- Staff stay in charge: the suggestion is shown, a person confirms it.

## Non-goals
- Writing replies to guests.
- Dispatching staff or ordering anything without a person's confirmation.
- Handling voice calls or messages in languages other than English.

## Open questions
- Should "urgent" also cover a guest locked out of their room at night?
  (Working answer: yes, because the guest cannot help themselves.)
