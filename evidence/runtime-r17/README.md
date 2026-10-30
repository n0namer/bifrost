# VP49 R17 — retry MVP verified on isolated canary

Accepted executable source: d45ee450b4a9ab1d49bb045ae1b1a8224f5be131.
Binary SHA-256: e69e9a679b19070ced7783b28ae63174adca50aaa99537a5a475abdb10b6db23.

## Delivered behavior

Complete explicit HTTP429,500,502,503,504,509,529 errors use the existing bounded retry/backoff/Retry-After loop. Refusal/quota markers and ambiguous, truncated or partially emitted POST results fail closed. Native OpenAI SSE classification and tool-call controls passed independent review.

## Evidence

- Exact source SHA independently accepted by native reviewer thread01a18dba-d3b3-7300-84fe-cbdaff292365, turn01a18e14-db1c-7f21-a6d8-2467b7e8cd34.
- Full OpenAI provider suite and four original truncation regressions passed.32physical native no-replay cases each observed primary1/fallback0.
- Go1.27.3 build metadata binds the executable to this SHA and the pinned fasthttp revision/checksum.
- Same executable:29/29 fake-upstream contract scenarios passed.
- Actual isolated candidate SSE and an actual old-binary rollback SSE both passed; private process/port/directory cleanup and unchanged production baseline were verified.
- Existing isolated canary now runs this executable on127.0.0.1:15185, PID107928. Its post-switch real SSE completed successfully. Five idle samples plus a final sample preceded the switch; post-switch metrics show zero active requests.
- OpenCodex PID11352 remains ready; live canary config and global Codex config hashes are unchanged. Main Codex routing remains direct to OpenCodex.
- The probe was tightened against redirects, nonstring delta and named SSE errors.13local helper/probe tests passed; redirect301/302/303/307/308 cases each sent1sourcePOST and0redirect-target requests.

## Scope and acceptance

Independent QA_ACCEPT applies to the Bifrost source SHA. The supplemental native helper-review expansion was stopped following the user's explicit MVP correction; its old candidate/report artifacts remain historical and are not claimed accepted. Runtime delivery was controlled by the coordinator using the pinned, independently accepted source/build proofs and fresh live observations. No helper QA receipt or native Goal completion was fabricated. No OpenCodex restart or global routing change occurred.

The wider utils suite is not wholly green: version-guard, host/timing failures and proxy timeout are disclosed in the source QA report and were not all proven pre-existing. Acceptance covers the OpenAI/passthrough MVP contract.

CrewSync server readback confirmed DONE for bifrost-canary:transient-http-retry and bifrost-canary:transient-http-retry-qa. See proofs/transient-http-r17-server-done.json. Broader pilot/reset tasks remain outside this completed retry MVP; the project root is not claimed DONE.

## Artifact layout

The helpers archive preserves files from the original Windows base directory; runtime scripts were executed from its evidence subdirectory and import the existing activation primitives. Restore the original layout to reproduce. The activation is a single guarded action and must not be blindly rerun after a receipt or unknown acknowledgement. Private configs, credentials, binaries and unrelated evidence are excluded.
