# VP49 R17 — candidate backup, runtime acceptance pending

Accepted executable source: d45ee450b4a9ab1d49bb045ae1b1a8224f5be131.
Binary SHA-256: e69e9a679b19070ced7783b28ae63174adca50aaa99537a5a475abdb10b6db23.

## Verified evidence

- Independent native source review: QA_ACCEPT for the exact source SHA; full OpenAI provider suite, the four original SSE regressions, selected utils/core contracts, and 32 physical no-replay cases passed.
- Build: Go1.27.3, exact vcs.revision, pinned fasthttp version/sum, stable source; executable hash matched the same-binary fixture.
- Binary fixture: 29/29 PASS, no real provider calls, no client retries.
- Runtime-helper candidate:9/9 Windows tests PASS, including3 local HTTP cases with exactly1 physical POST each. Native partial probe contribution was preserved; coordinator completed the remaining helpers after verified native429/terminal handoff.
- Current source HEAD and original Git index are preserved by evidence publication in a separate branch.

## Gates still open at this backup

Independent frozen-helper QA, real isolated streaming E2E, verified rollback rehearsal, canary activation, and CrewSync DONE are still pending. This archive is not activation authorization and does not claim SERVER_DONE.

Native source-review turn: 01a18e14-db1c-7f21-a6d8-2467b7e8cd34; original reviewer thread: 01a18dba-d3b3-7300-84fe-cbdaff292365. The original R16 Goal accounting was preserved; the later R17 turn and SHA-bound verdict are recorded separately.

The wider utils suite is not fully green: version-guard, host/timing failures and proxy timeout remain disclosed in the original QA report; they were not all proven pre-existing. Acceptance is the bounded OpenAI/passthrough MVP contract.

## Layout and reproduction context

The helpers folder archives the exact scripts deployed in C:\Users\Рафик\Documents\DEV\llm-gateway-bakeoff-20261030, alongside the bifrost-sparse checkout. They are not meant to be executed from this archive folder without restoring that layout and satisfying their proof gates. build/go.work is the hash-verified build workspace projection. The proofs folder contains normalized receipts and tests; source-tests contains the independently executed Go test logs.

No live configuration, credential file, binary, whole evidence directory, or unrelated project material is included. Global Codex routing remains outside this delivery scope.
