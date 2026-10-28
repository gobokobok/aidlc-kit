{% include "_frontmatter.md" %}

# {{ title }}

Technical plan for handoff {{ handoff }}. It is a starting point built from the
package: refine each section, and give every task the criteria it satisfies.
Tasks with no criterion are flagged, because nothing says what they are for.

## Components
{% for line in components %}- {{ line }}
{% endfor %}
## Interfaces and contracts
What each component receives and returns, including the output format the
prompt must produce.

## Data
What data is stored or passed around, where it comes from, and who can see it.
Note personal or sensitive data against the risk tier.

## Risks
What could go wrong in building or running this, and what we do about it.

## Regression gate
The golden set in the handoff package (`golden.yaml`, {{ cases }} cases) is the
regression gate for the implementation: the same cases must keep passing the
criteria thresholds, and the check runs in CI.

## Tasks
```yaml
{{ tasks_yaml }}
```
