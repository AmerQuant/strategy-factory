# configs/costs

Cost profiles (F-0.2.1, F-0.2.3, F-0.2.4). One profile per `*.yaml` file, validated by
`strategy_factory.costs.profile.CostProfile`; `assignments.yaml` maps asset classes and
symbols to profiles. A symbol without a profile cannot run (`sfac costs validate`).

All profiles are **placeholders** (`status: placeholder`) until the execution broker is
known; results that use them carry a visible flag. Replacing the numbers is a YAML-only change.
