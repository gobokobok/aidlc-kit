{% include "_frontmatter.md" %}

# {{ title }}

The golden set in `golden.yaml` next to this file: {{ cases }} cases that show
what correct behaviour looks like. Saving it again with /eval records a new
version here, so reviewers approve exactly the cases that are run.

## Cases per criterion
{% for line in per_criterion %}- {{ line }}
{% endfor %}
## Tags
{{ tags }}
