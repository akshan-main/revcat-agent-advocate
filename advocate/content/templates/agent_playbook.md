---
title: "{{ title }}"
date: "{{ date }}"
type: agent_playbook
tags: [{{ tags | join(', ') }}]
---

# {{ title }}

## Goal

{{ goal }}

## Tools Required

{{ tools }}

## Agent Configuration

{{ configuration }}

## Workflow

{% for section in sections %}
### Step {{ loop.index }}: {{ section.heading }}

{{ section.body }}

{% if section.has_code_snippet %}
```{{ section.snippet_language }}
{{ section.snippet_code }}
```
{% endif %}

{% endfor %}

## Monitoring & Verification

{{ monitoring }}

## Sources

{% for source in sources %}
- [{{ source.title }}]({{ source.url }})
{% endfor %}
