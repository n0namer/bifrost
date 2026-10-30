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

## Independent review repair, iteration 2

The independent BMad blind, edge and acceptance reviews of frozen `0e78102d1ffbc1f18955c165045f6ed6c7a15905` found three replay paths. Their source findings were reproduced before production changes in `transient-http-r17-independent-red.txt/.json`: all original 18 cases passed, while 14 new cases failed. A mutating hook returning neither response nor error and a first-token timeout each produced primary/fallback counts 1/1. HTTP 200 with an empty or non-SSE body produced 3/1 with MaxRetries=2.

Repairs are limited to existing paths:
- Preserve the latched replay prohibition on the original error object as well as returned errors, because the caller may retain that original object after an empty hook result.
- Mark synthetic first-token timeouts as unsafe to replay, and enforce the same decision when settling an expired attempt that already carries the timeout code. Keep 504, RequestTimedOut, ttft_timeout and the wrapped cause.
- Mark every HTTP-200 non-SSE failure kind as unsafe, preserving the existing 502 diagnostic, raw-response sample and billing information. A sampled JSON error under HTTP 200 does not prove complete rejection.

**Intentional compatibility decision:** an ambiguous first-token timeout no longer selects another provider. Missing headers or tokens do not establish that the POST was unprocessed, and this path has no verified idempotency contract. Existing cutoff, socket closure, abort cleanup and race/drain tests remain. The last-fallback positive control now enters through a complete HTTP400 rejection and still succeeds after a delay longer than the configured first-token deadline. Timely and unconfigured streaming behavior remains unchanged.

The expanded physical matrix covers 32 cases (Chat and Responses), preserves the complete/partial text `hello`, checks terminal events and exact error counts, and checks that the mutating empty-result hook actually ran once. The recorded focused green run `transient-http-r17-independent-green.txt/.json` passes all three packages and the original four OpenAI tests, TTFT checks, passthrough physical counters, first-chunk/preamble checks and transport regressions. A final frozen-SHA run remains required after commit.

Independent triage dismissed the carrier-precedence concern: the actual Bedrock invokeStreamException exposes no Unwrap or Is method, and decoded exception carriers are separate from framing errors. The ordinary two-hook recovery chain and fallback continuation guard also preserve the marker in the inspected source.

The earlier full OpenAI PASS and expanded-utils failures remain honestly recorded above. This repair does not claim that the full utils suite passes. No build, real model E2E, canary switch, rollback exercise, native QA acceptance or CrewSync SERVER_DONE is inferred from these source tests.

The final pre-commit hook-contract run transient-http-r17-hook-contracts-green.txt/.json also passes: exact single-error and mutation-invocation assertions, payload preservation, safe explicit rejection recovery, TTFT socket cleanup and existing plugin recovery contracts.
