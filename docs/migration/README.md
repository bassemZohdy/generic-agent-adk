# Runtime consolidation: preparation only

This repository has not been migrated or archived. The following gates must
be satisfied before replacing an installed runtime or retiring its source.

## Native ADK-specific gates

The original baseline is `9fb772d270f44bdf189e257fb912d798624ab629`.
The package is `basic-adk-agent`, namespace `basic_agent`, with Google ADK
`>=2.6.3,<2.7.0`. The local main snapshot is 22 commits behind the captured
GitHub baseline, not an unpublished replacement; its remote audit ref was also
preserved in the backup. No original checkout is updated by this preparation.

The [native compiler](https://github.com/bassemZohdy/generic-agent-adk/blob/9fb772d270f44bdf189e257fb912d798624ab629/src/basic_agent/compile/workflow.py)
builds ADK Workflow/FunctionNode/JoinNode graphs. The
[preset catalog](https://github.com/bassemZohdy/generic-agent-adk/blob/9fb772d270f44bdf189e257fb912d798624ab629/src/basic_agent/presets/catalog.py)
also owns synthesis, dynamic planning and delegation behavior.
OWA's common executor inside engine envelopes is not that compiler.
Keep ADK-specific graph/config/evaluation fixtures until a target contract is
selected and all observable results reconcile; do not advertise native lowering
or new compiler support in canonical OWA as part of consolidation.

The [approval policy](https://github.com/bassemZohdy/generic-agent-adk/blob/9fb772d270f44bdf189e257fb912d798624ab629/src/basic_agent/policies/approval.py)
uses ADK before-tool veto/confirmation callbacks. Its unconditional tool and
delegation exceptions, callback order and detection-failure behavior require
explicit migration tests. They must not be replaced by the LangGraph prototype's
status-string gate or blindly treated as equivalent to OWA durable approvals.

| Legacy preset | Candidate OWA expression | Required reconciliation before migration |
|---|---|---|
| assistant | Generated one-task `agent:1.0.0@default` workflow | Provider/model selection, message/session identity, tool allowlists and response shape |
| pipeline | Explicit ordered `do` tasks | Per-role instructions/models/tools, prior-stage context, output keys and step limits |
| multi_perspective | `fork` followed by an explicit synthesis task | Stable branch outputs, joins, synthesis instruction/model and partial failures |
| refine_until_good | Bounded `for`/`switch` or subworkflow | Quality predicate, loop budget, retry versus refinement semantics and termination |
| expert_dispatch | Explicit `switch`/catalog calls | Route parsing, default/unknown route, fixed roster and per-role restrictions |
| team_coordinator | Explicit subworkflows/catalog operations | Dynamic delegation, worker ownership, recursion and cancellation; no native graph equivalence claimed |
| plan_and_execute | Explicit planner result plus bounded workflow steps | Plan validation, iteration budget, executor context and forbidden operations |
| approval_gate | Durable approval service plus `emit`/`listen` and approved-only branch | Protected operator identity, pending/unknown/rejected/expired refusal, restart/replay, idempotency and zero side effects before approval |


Also preserve graph sugar/nesting/routing/retries, custom function modules,
Live API, authentication, cloud deployment, persistence and sandbox verification
fixtures. Read [configuration](../CONFIGURATION.md),
[native migration ADR](../ADR-003-adk-workflow-migration.md) and
[graph taxonomy ADR](../ADR-005-graph-first-taxonomy-and-configuration.md).

Keep the original [Apache-2.0 license](../../LICENSE) and applicable origin
notices with any later copied/modified material; nothing in this stage changes
the licensing or adds an external-source import. Main CI may publish an image,
so this proposal is a draft and does not promote a legacy image or freeze writes.
CI/image acceptance and actual consumer coordinates remain retirement gates.

## Target and compatibility boundary

Workflow behavior belongs in [Open Workflow Agent at the reviewed baseline](https://github.com/bassemZohdy/open-workflow-agent/tree/15bcfba17b4327f927d0729c03c968718738f6db).
Its public authoring contract is Open Workflow 1.0.3; core is framework neutral.
Managed definitions/catalog/deployment lifecycle belong in
[Open Simple Agent at the reviewed baseline](https://github.com/bassemZohdy/open-simple-agent/tree/178039de5b4060d9a7a8b593fcbb479ee57eecb7)
only where a missing management capability has been established. The current
inspection found no direct predecessor SDK import in those two canonical source
trees. This is not an inventory of external installations.

The mappings below are a migration plan, not tested drop-in compatibility.
No legacy configuration loader, provider credential, database, deployment,
package name or live client is changed by this documentation stage.

## Repository-side preparation

The accompanying [source manifest](source-manifest.json) records every tracked
file at the original revision, with its Git blob id, mode and disposition.
Original source, histories, branches, tags and unpublished local refs remain
preserved. Complete-history Git bundles were independently restored, compared
ref-for-ref and checked with `git fsck --full` during preparation. No LFS
objects were found. These Git backups do not include ignored live settings or
untracked runtime data; those existing files were left untouched.

There is no runtime code or configuration copied into a canonical repository
in this stage. License files and provenance remain unchanged. A manifest entry
marked pending is not evidence that its behavior has been migrated.

## Acceptance and rollback

1. Identify callers by package/import, image digest, service/Live URL, auth
   contract, session/checkpoint store and custom tool/function modules.
   The bounded portfolio source scan found only self references and the
   canonical ADK distribution's own references; it cannot prove no external users.
2. Reconcile each selected fixture on both advertised engines, using deterministic
   models and isolated temporary stores. Preserve model/role/tool differences,
   output shapes, cancellation, timeouts, retry budgets and runtime error codes.
3. For approval, prove pending/unknown/rejected/expired states cannot execute an
   action, approved decisions are operator-bound, and restart/replay cannot
   duplicate the action. A status string or prompt is not approval enforcement.
4. Keep credentials/auth settings and live storage untouched until a separately
   reviewed consumer cutover. Verify migration and rollback with the chosen
   deployment before changing an installed client or service.
5. Before read-only archival, complete unique-file dispositions, preserve all
   current refs/collaboration, resolve licensing/package ownership and publish
   accurate consumer instructions. No archive is authorized by an incomplete
   checklist. Archive only after those gates pass; permanent deletion is excluded.

Reverting this documentation commit restores the previous documentation without
changing executable behavior. Original commits remain addressable. Future live
cutover must retain the original immutable image/package and database snapshot;
record how to reconcile writes after cutover rather than assuming an old backup
alone can recover them.

Existing OWA [portable fixture tests](https://github.com/bassemZohdy/open-workflow-agent/blob/15bcfba17b4327f927d0729c03c968718738f6db/tests/contract/test_contract.py)
and [durable approval replay test](https://github.com/bassemZohdy/open-workflow-agent/blob/15bcfba17b4327f927d0729c03c968718738f6db/tests/contract/test_durable_approvals.py)
are a target baseline. They are not migration acceptance for this predecessor.
