# Support and version policy

- The supported runtime is Python 3.10–3.13 and the tested ADK range is
  `google-adk>=2.6.3,<2.7.0`.
- Security fixes are prioritized for the current `main` branch and the latest
  promoted image digest. Rotate API keys, OIDC keys, sandbox image digests,
  and database credentials through the deployment platform.
- ADK upgrades require the checklist in TODO.md (T26) and a full compatibility
  matrix before the dependency upper bound is changed.
- Releases use SemVer: patch releases contain fixes, minor releases may add
  configuration/features, and major releases may remove fields or change API
  contracts. Image promotion is digest-based and should occur only after CI and
  staging verification.
- Cloud Run, external OIDC, managed persistence, and real model calls require
  staging verification; the local Compose stack is a development fixture.

See [CONFIGURATION.md](CONFIGURATION.md) for supported settings and
[ADR-003](ADR-003-adk-workflow-migration.md) for the workflow migration gate.
