---
id: {{ id }}
type: {{ type }}
feature: {{ feature }}
title: {{ title | yaml }}
version: 1
status: draft
owner: {{ owner }}
parents: {{ parents | yaml }}
approvals: []
updated_at: {{ now }}
{% for key, value in extra.items() %}{{ key }}: {{ value | yaml }}
{% endfor %}---