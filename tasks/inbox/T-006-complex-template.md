{
  "task_type": "complex",
  "objective": "Build and validate a dependency-aware plan",
  "deliverables": [
    "workflow state artifact",
    "integration summary"
  ],
  "constraints": [
    "deterministic step selection",
    "machine-evaluable done_when conditions"
  ],
  "steps": [
    {
      "id": "s01",
      "description": "Define acceptance criteria for the feature",
      "depends_on": [],
      "done_when": [
        "file_exists(artifacts/acceptance.criteria.md)"
      ]
    },
    {
      "id": "s02",
      "description": "Produce an implementation plan using the accepted criteria",
      "depends_on": ["s01"],
      "done_when": [
        "file_exists(artifacts/implementation.plan.md)"
      ]
    },
    {
      "id": "s03",
      "description": "Create integration summary with risks and follow-ups",
      "depends_on": ["s02"],
      "done_when": [
        "file_exists(artifacts/integration.summary.md)"
      ]
    }
  ]
}

Use this task with `complex_reasoning_loop` to exercise dependency-aware workflow state and resume behavior.
