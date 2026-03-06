---
title: "{{ title }}"
date: "{{ date }}"
type: tutorial
tags: [{{ tags | join(', ') }}]
---

# {{ title }}

## Introduction

{{ intro }}

## Prerequisites

{{ prerequisites }}

{% for section in sections %}
## {{ section.heading }}

{{ section.body }}

{% if section.has_code_snippet %}
```{{ section.snippet_language }}
{{ section.snippet_code }}
```
{% endif %}

{% endfor %}

## Key Takeaways

{{ takeaways }}

## Next Steps

{{ next_steps }}

## Sources

{% for source in sources %}
- [{{ source.title }}]({{ source.url }})
{% endfor %}
