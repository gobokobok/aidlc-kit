{% include "_frontmatter.md" %}

# {{ title }}

## Purpose
What this prompt makes the AI do, and which criteria it serves.

## Prompt
Write `{% raw %}{{ input }}{% endraw %}` where each test case's input goes (or
`{% raw %}{{ input.field }}{% endraw %}` for inputs with named fields).

```text
(the prompt goes here)
```

## Output format
The AI must answer with one JSON object whose fields match the `expected`
fields in the golden set, for example `{"category": "maintenance", "urgent": true}`.

## Model and settings
Set in the frontmatter: `model` (or `eval.model` in aidlc.yaml), and
optionally `max_tokens`, `effort` and `temperature` where the provider takes them.

## Human review step
Who checks the AI output before it takes effect, and how. Required at tiers
that demand a human in the loop (`human_review_step` in the frontmatter).
