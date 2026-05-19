---
idea_id: my-idea-slug
target_project: example_project
hypothesis: One sentence — the change you believe will move the metric.
primary_metric: validation_score
# allowed_files is optional; if omitted it defaults to the capsule's scope.
allowed_files:
  - src/experimental/**
accept_rules:
  - metric: validation_score
    operator: gt
    threshold: 0.0
guardrail_metrics:
  - metric: regression_count
    operator: lte
    threshold: 0
# optional overrides:
# max_files_changed: 5
# max_lines_changed: 300
---

## Context
Why this idea, what was tried before, and what "better" means here.

## Notes
Free-form scratch space. Everything below the frontmatter is kept as `notes`.
