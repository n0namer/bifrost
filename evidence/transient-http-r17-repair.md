# R17 source candidate — native SSE contract and POST replay safety

Status: SOURCE_CANDIDATE / INDEPENDENT_QA_PENDING / NOT_SERVER_DONE.
Baseline: 943261a78e543741e59e87b4acdc9d8d7714cbfe.
Authority: existing CrewSync task bifrost-canary:transient-http-retry, coordinator,
session bifrost-central-canary-20261030, plan bifrost-canary-20261030-r17.

## Reconciled execution

The original source Goal 01a18d42-ea96-7b62-ab31-a185e0f7a99e is preserved.
Its authorized Terra/high repair turn 01a18dde-9e36-7391-8ef6-33356ce1d798 failed
429 before source work. Nearby OpenCodex diagnostic metadata recorded
upstream_reset_replay_refused / transport-ambiguous / headers-only; correlation
is by time/model, not a proven turn-to-request binding. The observer exited.
CrewSync's existing r17 spec/plan/checkpoint records the coordinator as sole
local source executor under the same lease. No duplicate Goal, task, proxy,
scheduler or automatic retry of the ambiguous model request was created.

## Observed defects and repair

The four original OpenAI tests failed on baseline (openai-red receipt).
The new real-HTTP core test reproduced the second R16 concern:

| Native stream result | Before repair: primary + fallback POSTs | After repair |
| --- | --- | --- |
| Complete HTTP, empty/comment/incomplete SSE before output | 3 + 1 | 1 + 0 |
| Missing terminating HTTP chunk before output | 1 + 1 | 1 + 0 |
| Partial output, then clean or broken HTTP end | 1 + 0 | 1 + 0 |
| Complete normal stream | 1 + 0, success | 1 + 0, success |

18 cases cover Chat and Responses, complete and incomplete framing, no output,
partial output and normal completion. Comment cases additionally replace or
mutate the error through a real plugin. A first green attempt exposed a second
post-hook boundary that discarded the safety flag; that failure is retained in
focused-green-1, and focused-green-2 passes.

Transport io.ErrUnexpectedEOF is never converted to EOF. The shared stream
normalizer now preserves the upstream 502/provider_connection_failed contract.
An internal JSON-excluded ReplayUnsafe flag independently forbids retries and
both primary and chained fallbacks. Post-hook processing carries this decision
across replacement, mutation, and temporary recovery. Unclassified read failures
also forbid replay; already-classified reader errors retain their own policy.

This intentionally changes the old pre-output truncation retry policy: no emitted
client token and no SSE terminal marker are not proof that a dispatched POST was
unprocessed. The existing Content-Length regression now asserts the underlying
io.ErrUnexpectedEOF via errors.Is rather than its incidental message text.

Complete explicit 429/500/502/503/504/509/529 passthrough responses keep bounded
retries, Retry-After, denial/quota guards and exact exhausted response behavior.
No dependency version, Go module file, transport reader or global config changed
in R17. R16's upstream fasthttp pseudo-version remains in force.

## Verification and concrete limits

- focused-green-2: PASS for core, OpenAI and utils selected tests. Includes all
  four original OpenAI regressions, 18 native physical-send cases, passthrough
  read failures, complete transient recoveries, refusal/quota/overflow/backoff
  guards, transport framing and existing explicit-error fallbacks.
- Full providers/openai package: PASS, 16.938 seconds. Existing normal SSE,
  terminal-event and tool-call regressions ran, not an empty regex.
- Expanded providers/utils suite: NOT PASS. It reports three failures and reaches
  a 180-second timeout in TestProxyRoutingMatrix. Do not label this suite green:
  - TestFasthttpVersionIsConsistentAcrossModules still hard-codes v1.74.0, while
    core/transports already required v1.77.1-0.20261028061327-329917ed143c in R16.
    This stale guard/dependency-scope discrepancy is disclosed to QA, not removed.
  - TestConfigureDialer_SSRFMultiIPAllFail received a successful connection to
    the TEST-NET target 192.0.2.1:9 on this host. No R17 dialer changes.
  - TestMakeRequestWithContext_SuccessReturnsNoopWait observed zero measured
    latency from an in-memory server. No R17 timing changes.
  - ProxyRoutingMatrix timing out is not attributed to R17 without a baseline
    reproduction. It is a remaining broad-suite limitation outside the proven
    direct loopback MVP path.
  Original full log is retained on VP49 alongside its committed JSON receipt.
- BenchmarkStreamingPostHooks: PASS; 21593 ns/op, 17105 B/op, 347 allocs/op on
  Windows amd64 / i5-11400H, GOMAXPROCS=2. This is a measurement, not a claimed
  improvement over an unmeasured baseline. New state is one bool per error;
  no response buffer, scheduler or per-token payload retention is introduced.
- Existing local fixture extended, four native HTTP harness cases added by a
  textual splice. Canonical augment/filter validation retains exactly four
  OpenAI cases; no paid provider sweep was run. Missing sparse runner blobs were
  obtained from the exact baseline via GitHub after a stalled read-only archive
  hydration was cancelled; neither global Git configuration nor source changed.
- git diff --check is required before the candidate commit.

## Required next gates

Freeze and back up the candidate, verify remote SHA, and obtain independent
QA_ACCEPT specifically for that SHA. Reviewers must see the retained red/green
receipts and the expanded-suite limitations above. A source PASS is not QA_ACCEPT.

Then build that frozen SHA with Go 1.27.3, verify fasthttp/build metadata and binary
hash, run all 29 existing isolated binary cases and a finite real streaming E2E.
Only after QA and same-binary evidence may the isolated canary switch with drain,
fresh process/config checks and a verified rollback. The old canary and OpenCodex
remain running. Global Codex routing is unchanged. The existing CrewSync reducer
and authoritative DONE readback remain mandatory; none is claimed here.
