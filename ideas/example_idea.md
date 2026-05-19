---
idea_id: warm-start-experimental-config
target_project: example_project
hypothesis: A small isolated change to the experimental config improves the validation score.
primary_metric: validation_score
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
---

## Context
A worked example idea. `autoresearch plan ideas/example_idea.md` turns this
into a run contract under `experiments/contracts/`.
