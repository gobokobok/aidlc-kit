{% include "_frontmatter.md" %}

# {{ title }}

The package engineering picks up: the specification, the approved prompt and
risk profile, the golden set ({{ cases }} cases) and the trace from each
criterion back to the discovery brief. It is frozen when built. Once reviewers
accept it, the feature is merged and tagged `{{ tag }}`.

{{ tier }}.

## Built from
{% for line in items %}- {{ line }}
{% endfor %}
## In this folder
`spec.md`, `risk.md`, `assets/`, `golden.yaml`, `eval-report.md`,
`trace.json` and `manifest.json` (with a checksum of each file).
