---
title: 'Transient HTTP retries: native SSE truncation and replay safety repair'
type: bugfix
created: '2026-10-30'
status: ready-for-review
baseline_commit: '943261a78e543741e59e87b4acdc9d8d7714cbfe'
review_loop_iteration: 1
authority: 'CrewSync global note bifrost-canary:transient-http-retry:spec'
authority_revision: 'r17-native-sse-no-replay-repair'
task_key: 'bifrost-canary:transient-http-retry'
source_thread: '01a18d42-ea96-7b62-ab31-a185e0f7a99e'
source_executor: 'coordinator under the existing CrewSync lease; original native Goal blocked'
context: ['AGENTS.md']
---

This is the implementation projection of the existing CrewSync spec, not a separate task plan. The user's 2026-10-30 handoff explicitly authorizes repairing both R16 QA findings and proceeding through focused verification, backup, independent QA and gated isolated canary activation. No new feature approval is requested.

<frozen-after-approval reason="Existing user-approved repair intent">

## Intent

**Problem:** R16 correctly preserves chunked HTTP truncation errors, but four native OpenAI streaming tests now receive a generic internal error. Separately, clean HTTP EOF after an SSE comment or incomplete event can create a retryable first error and replay an already-processed POST.

**Approach:** Reconcile native truncation error semantics with an explicit fail-closed replay decision. Preserve the existing bounded retry loop for fully received explicit transient HTTP errors. Use physical request counters to distinguish correct recovery from duplicate execution.

## Boundaries & Constraints

**Always:** Keep io.ErrUnexpectedEOF observable. Keep source ownership in the original native thread and preserve original Goal identity/accounting. Keep client-visible truncation classification meaningful, including before output and mid-stream. An uncertain already-sent POST must not retry or fall back absent suitable idempotency. Coordinator owns the Git index, commit, push and acceptance.

**Ask coordinator:** Any additional source write scope or runtime operation outside the existing spec. Source-level implementation choices within this goal need no further human approval.

**Never:** Restore unexpected-EOF-to-EOF masking; infer safe replay solely from missing terminal SSE or absent client tokens; disable positive HTTP retries; add a scheduler/proxy/daemon; edit global configuration; restart OpenCodex; activate an unaccepted binary; claim CrewSync DONE from worker tests.

## I/O & Edge-Case Matrix

| Input/state | Required behavior |
|---|---|
| Complete explicit HTTP 429/500/502/503/504/509/529 error, then success | Bounded retry using existing MaxRetries/backoff/Retry-After |
| X-Should-Retry:false, refusal/quota marker, oversized/error/cancelled body | One physical POST; preserve failure |
| Native successful HTTP headers then truncated framing before first client chunk | Visible upstream truncation error; one POST, no fallback |
| Complete HTTP framing, comment-only or incomplete/nonterminal SSE then EOF | Visible truncation/failure; one POST, no fallback |
| Native stream ends after emitted content/tool-call delta | Preserve emitted data and visible error, no replay |
| Normal SSE, tool calls and terminal events | Existing successful behavior and data preserved |

</frozen-after-approval>

## Code Map

- `../core/providers/utils/roundtripper.go`: current transport now retains truncation errors; keep it.
- `../core/providers/utils/utils.go`: generic read-error and semantic truncation helpers, current 502 classification.
- `../core/providers/openai/openai.go`: native text/chat/Responses and sibling SSE read loops.
- `../core/bifrost.go`: existing retry loop and first-stream-chunk handling.
- `../core/providers/openai/streamtruncation_test.go`: existing four failing regression tests and successful stream fixtures.
- `../core/passthrough_retry_loop_test.go`: real send counters and core retry fixture patterns.
- `../core/providers/utils/makerequest_test.go`, `../core/providers/utils/utils_test.go`: affected transport/helper checks.
- `../tests/e2e/api/collections/provider-harness.json`: existing wire contract cases; surgical update if relevant.

## Tasks & Acceptance

- [ ] Reproduce the four named native regressions on baseline and save a red receipt.
- [ ] Add minimal physical native POST-count cases to an existing test file for clean and malformed HTTP completion with nonterminal SSE; demonstrate the expected defect before repair.
- [ ] Implement the smallest compatible classification/no-replay fix within approved scope; retain complete explicit HTTP retries and passthrough read-error safety.
- [ ] Verify happy SSE, streaming tool-call and terminal-event behavior using existing local fixtures.
- [ ] Run targeted passthrough/transport/native suites, exact named cases, formatting and diff checks; record runtime cost and retained-memory bound, reusing relevant existing benchmarks.
- [ ] Return candidate diff, exact tests and receipts to coordinator; do not stage, commit, push or accept.

**Acceptance Criteria:**

- Given a fully received explicit transient rejection, when retry budget remains, then recovery occurs within the existing budget and Retry-After floor.
- Given an ambiguous already-sent native POST, when HTTP or semantic SSE ends incompletely, then the physical upstream count is exactly one and fallback cannot repeat the operation.
- Given native truncation before or after output, when the client consumes the stream, then the documented upstream error shape is preserved or deliberately updated with compatibility evidence.
- Given normal SSE/tool calls/terminal events, when processed with the repair, then successful payloads and completion behavior remain intact.

## Spec Change Log

- R17 follows independent review `../../evidence/transient-http-r16-independent-qa.md`: reconcile four native regressions and reproduce clean-framing/nonterminal-SSE replay. KEEP: transport ErrUnexpectedEOF, bounded positive retries, late refusal/quota markers, overflow/cancel protection, last raw response. Original reviewer: 01a18dba-d3b3-7300-84fe-cbdaff292365.

## Verification

Run from `../core` using installed Go 1.27.3 and verified local dependencies. Process-local GOPROXY=off, GOTOOLCHAIN=local; use GOSUMDB=off only for offline cache verification if needed, never globally.

- `go test ./providers/openai -run '^(TestChatStreamTruncatedPreFirstByte|TestChatStreamTruncatedMidStream|TestTextCompletionStreamTruncated|TestResponsesStreamTruncatedBeforeCompleted)$' -count=1 -timeout=60s`
- `go test . -run '^TestPassthroughStreamReadFailureNeverReplays$' -count=1 -v`
- `go test ./providers/utils -run '^TestContextTransport_' -count=1`
- `go test ./providers/utils -run '^TestStreamPassthrough_' -count=1`
- Select exact new native physical-send cases and existing positive/guard/Retry-After cases; list tests first so empty regex coverage is detected.
- `git diff --check`

Frozen SHA, backup readback, independent native QA, same-binary 29-case fixture, one real streaming E2E, canary rollback and CrewSync reducer/readback remain coordinator gates after this repair.

## Execution reconcile and candidate readback

The original native worker's authorized Terra/high turn failed 429 before edits. The existing CrewSync r17 spec/plan/checkpoint now authorizes the coordinator as sole local source executor under the same task/session; the original Goal identity, accounting and failure history are preserved. This supersedes only the native-worker-only execution wording above. The approved repair intent and runtime gates are unchanged. See transient-http-r17-repair.md for actual red/green evidence, physical POST counts, the full OpenAI PASS and the expanded utils-suite limitations. Candidate preparation is complete; independent SHA acceptance and runtime delivery remain pending.
