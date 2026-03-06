---
title: "{{ title }}"
date: "{{ date }}"
type: case_study
tags: [{{ tags | join(', ') }}]
---

# {{ title }}

## The Challenge

{{ challenge }}

## The Solution

{{ solution }}

## Implementation with RevenueCat

{% for section in sections %}
### {{ section.heading }}

{{ section.body }}

{% if section.has_code_snippet %}
```{{ section.snippet_language }}
{{ section.snippet_code }}
```
{% endif %}

{% endfor %}

## Results

{{ results }}

## Lessons Learned

{{ lessons }}

## Sources

{% for source in sources %}
- [{{ source.title }}]({{ source.url }})
{% endfor %}
