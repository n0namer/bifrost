# r14 transient HTTP retry Worker evidence

Task: `bifrost-canary:transient-http-retry`; approved revision `r14-transient-http-retry`; coordinator/session `bifrost-central-canary-20261030`.

Native Goal readback: thread `01a18d42-ea96-7b62-ab31-a185e0f7a99e`, objective `bifrost-canary:transient-http-retry implement bounded explicit HTTP error retries including509 with existing replay safeguards`, active. Native outer transport IDs/type:skill events are not visible to this Worker; no competing App Server was launched. Effective supplied environment: danger-full-access, approval never. FAST Worker, ub-mode and TDD applied. Canonical BMad Help/Quick Dev implementation routing read; user-supplied approved r14 contract controls this bounded Worker. No new planning/acceptance authority was created.

Baseline: `a9d130d3fc39b8ddc907586ec1eb5a7ce470df91`; branch `fix/passthrough-429-dev`. Tracked files were clean at admission; pre-existing untracked evidence files were preserved. No gateway/OpenCodex build, replacement, config/process change, push, PR, external message or CrewSync DONE effect was performed. Independent frozen-source QA/build/runtime verification remain coordinator-owned.

## Current disposition: NOT READY TO FREEZE

The source extends explicit complete passthrough HTTP errors to 429/500/502/503/504/509/529, reusing the existing provider retry budget and cancel-aware Retry-After floor. Nonallowlisted statuses remain raw. Last response status/body/headers are returned on exhaustion. 509 is classified transient only after this raw-response classifier authorizes replay, without changing the general failure classifier or transport-error policy.

Complete bounded streaming error inspection now applies to every allowed status. It rejects explicit read-error chunks, cancellation, byte overflow and chunk overflow. Terminal-looking SSE events are ignored on allowlisted HTTP errors so a later quota/refused marker remains visible. Successful streams and nonallowlisted HTTP statuses retain terminal-event handling. No content-sized context value or persistent cache was introduced.

**Required blocker:** `TestPassthroughStreamReadFailureNeverReplays` exposes a dependency defect: a real HTTP chunked response cut between body chunks, without its terminating zero chunk, is reported by fasthttp v1.74.0 as clean `io.EOF`. A 502/509 therefore currently makes 3 physical sends instead of 1. The 200 control makes one send but incorrectly sees clean EOF. The test remains present and failing; no safeguard acceptance or complete Goal is claimed.

Dependency source inspected read-only: `github.com/valyala/fasthttp@v1.74.0/streaming.go`, `requestStream.Read`, around lines 49-54. `parseChunkSize` errors are returned unchanged; EOF there is indistinguishable from successful end-of-body at the public reader. The existing strictEOF check only guards fixed Content-Length reads. No robust in-scope public API was found to distinguish the two. Requested coordinator scope decision: authorize minimal dependency repair with provenance, or hand back this blocked patch. No dependency/cache source was edited.

## Red before green and verification

All commands below run from repository root unless marked `core`.

1. Before implementation: in `core`, `go test . -run '^TestPassthroughLoopTransientHTTP$' -count=1`. Expected assertion failure: 500/502/503/504/509/529 unary and streaming each returned first status with 1 handler invocation rather than 200 after 2. 429 and negative controls behaved as expected. Raw output: `transient-http-r14-red.txt` (subsequent identical baseline rerun captured to file before source edits).
2. After the terminal-event regression was added, before that fix: `go test ./core/providers/utils -run '^TestStreamPassthrough_HTTPErrorIgnoresTerminalEvents$' -count=1` failed for 429/502/509 because the later refused marker was truncated. Output: `transient-http-r14-terminal-red.txt`. The allowlist-only terminal guard fixes it.
3. `go test ./core ./core/providers/utils -run 'TestPassthrough|TestFirstStreamChunkPassthrough|TestStreamPassthrough_' -count=1`: PASS at that source point, before adding the real malformed-chunked regression. Output: `transient-http-r14-green.txt`. Do not treat this earlier result as full final acceptance.
4. Current focused suite excluding the separately named known blocker: `go test ./core ./core/providers/utils -run 'TestPassthrough(HTTPRetryError|Loop|TransientPhysicalSends|429RetryAfterHint|RetryDelay)|TestFirstStreamChunkPassthrough|TestStreamPassthrough_|TestPassthroughTransient(BodyInspection|Cancellation)' -count=1`: PASS, core 5.947s, utils 2.181s. Output: `transient-http-r14-focused-current.txt`.
5. Real local upstream tests use the actual OpenAI provider and physical request counters: all new statuses, unary and streaming, recover after 2 sends; noRetry, split refused and late quota use 1; exhaustion uses 3 with the last raw body/status/X-Origin. Counter tests are included in command 4. The first iteration failed from a test-only nil post-hook, then test-only header spelling; both were corrected. No production workaround was made for either fixture mistake.
6. `go test ./core -run '^TestPassthroughStreamReadFailureNeverReplays$' -count=1`: FAIL, required blocker described above. Output: `transient-http-r14-read-failure.txt`.
7. `go test ./core ./core/providers/utils -count=1`: core failed `TestOverheadEndToEndUnary` (overhead measured 0s). Output: `transient-http-r14-packages.txt`. `go test ./core -run '^TestOverheadEndToEndUnary$' -count=1`: PASS, 0.594s (`transient-http-r14-overhead-rerun.txt`). Later new blocker means a full current run is expected to fail independently.
8. `git diff --check`: PASS. Graphify 0.9.93 available; no local graph. Both maintained ensure/refresh helpers returned `SKIP_NOT_REGISTERED_CANONICAL_PROJECT`; actual source searches used instead.

## Harness

Surgical insertion: top-level folder 297, four local fixture cases for unary/streaming 502/509, selected by `transient-http-retry`. Each case requires 200, exact successful fixture payload sends=2, and x-fixture-sends=2; unexpected statuses are asserted, never skipped. Opt-in prerequest only selects the isolated synthetic profile, matching existing fixture conventions. `evidence/transient-http-r14-fixture.mjs` supplies the upstream without forwarding anywhere. See folder description for isolated gateway configuration. It was syntax checked; no live gateway/harness was run.

The sparse skill/collection/validators were retrieved from exact HEAD using process-local Git OpenSSL after default schannel fetch failed. An upstream main skill read was navigation only; exact HEAD skill was subsequently read. Original collection bytes were preserved verbatim outside the added folder (246 additions, 0 deletions). Validation tools and imported libraries were exact tracked source recovered under temporary `evidence/transient-http-r14-harness-tools`.

Commands:
```
node evidence/transient-http-r14-harness-tools/augment-provider-harness.mjs --source tests/e2e/api/collections/provider-harness.json --out evidence/transient-http-r14-harness-augmented.json
node evidence/transient-http-r14-harness-tools/filter-collection.mjs --source evidence/transient-http-r14-harness-augmented.json --out evidence/transient-http-r14-harness-filtered.json --provider openai --feature transient-http-retry
```
PASS: 639 generated requests; filter retained exactly four requested cases; all retained scripts parse with Node vm.Script. Output: `transient-http-r14-harness-validation.txt`. No paid broad harness was run. Coordinator must start an isolated candidate gateway against this fixture before any eventual live harness command; active gateway replacement is outside this Worker phase.

## Request-path cost

`BenchmarkPassthroughRetryClassification`, existing core test file, `go test ./core -run '^$' -bench '^BenchmarkPassthroughRetryClassification$' -benchmem -count=1`.

| Path | Baseline ns/op | After ns/op | Baseline B/op, allocs/op | After B/op, allocs/op |
|---|---:|---:|---|---|
| success 200 | 1.951 | 4.225 | 0, 0 | 0, 0 |
| existing 429 | 390.8 | 639.8 | 584, 4 | 584, 4 |
| new 509 | 1.975 (no retry work) | 652.1 | 0, 0 | 584, 4 |

Single-run measurements on the same VP49 host, with concurrent test/compile activity; no precision or statistical speed claim. Output files `transient-http-r14-benchmark-before.txt` and `transient-http-r14-benchmark-after.txt`. A first after-benchmark build raced a test rename and was discarded; the recorded rerun completed successfully.

Existing 429 body-inspection bounds extend to the new statuses: 1 MiB combined inspection body and at most 1025 retained chunk references before fail-closed forwarding, plus the already received overflow chunk. State is request-local and released/forwarded on completion, refusal, overflow or cancellation. No retained global per-credential/per-stream entries or new manager/cache exist. Normal 200 classifier still allocates zero; HTTP error inspection/retry does work only on allowed statuses with remaining budget. Unary inspection now also rejects bodies larger than 1 MiB.

## Current source SHA-256 (uncommitted; not an accepted candidate)

| Path | SHA-256 |
|---|---|
| `core/bifrost.go` | `b42b2566e881a11b0c0e3e88829e6da762c010be2a8438da5c3a814d3ef01a39` |
| `core/passthrough_retry.go` | `177b115b0c42dbc058b05cdbecc724bba384f63a66c0eaaa9a389c1c34c80887` |
| `core/providers/utils/stream.go` | `9c47ddc9d704d66c8ad182b49e12113b66727b3db8436155a0d5afca4cf92c11` |
| `core/providers/utils/passthrough_stream.go` | `7a6fe17dc6589221d7305d48a922c98a0903f1f6e4c26bfa9ee9fba2bd973b76` |
| `core/passthrough_retry_loop_test.go` | `c619b572d503d774bd22d82a0b45348c184087c9dbb25945fffc4d3284cf71ca` |
| `core/passthrough_retry_test.go` | `e435cf4048e40ada76e9f20e6aba9a717c14a958415ca24dda1280683d85ed8b` |
| `core/passthrough_retryafter_test.go` | `22e3213afeca44a2409bbc2dc2b8dc0cfc69e125e18707f0137d66f02cd6fc46` |
| `core/providers/utils/passthrough_stream_test.go` | `53b7bc7c9285387036fa8afc8906975b2732c783b389a29a3e40414d000cf420` |
| `core/providers/utils/stream_passthrough_retry_test.go` | `5090b9094de9f3d6c869673d116916293d311845d6ee6e4eb44f2c015a671ee5` |
| `tests/e2e/api/collections/provider-harness.json` | `4e113ecf9e72ef5b7955a7eec552a66d4a31d52046467bbf0c754ecd5d92f47d` |
| `evidence/transient-http-r14-fixture.mjs` | `defc1c59d4e67786e7e8ba5f0d1bf9249b51f3452672cde6f0f6810b5913545f` |

## Further verified results and corrections

- `TestStreamPassthrough_NonRetryStatusKeepsTerminalEvents` was added red first: the initial success-only guard changed HTTP 400 behavior. `transient-http-r14-nonretry-terminal-red.txt` records the expected failure. The guard now disables terminal-event detection only for the explicit retry allowlist. `go test ./core/providers/utils -run '^TestStreamPassthrough_' -count=1 -timeout 60s`: PASS, 0.558s (`transient-http-r14-stream-final.txt`).
- Current focused command rerun after that correction, with `-timeout 60s`: PASS, core 5.947s, utils 2.181s. The malformed chunked-body regression remains separately failing and was not silently omitted from acceptance.
- `go test ./core -skip '^TestPassthroughStreamReadFailureNeverReplays$' -count=1`: FAIL, `TestListAllModelsIncludesEveryPageOfASlowLargeProvider` deadline. `go test ./core -run '^TestListAllModelsIncludesEveryPageOfASlowLargeProvider$' -count=1`: PASS, 3.157s. Logs: `transient-http-r14-core-package-except-blocker.txt`, `transient-http-r14-listmodels-rerun.txt`. No broad package PASS is claimed.
- An old unbounded utils-package test was stopped by its verified Worker-owned `utils.test.exe` process ID/path after a source correction. It was never reported passing. A fresh `go test ./core/providers/utils -count=1 -timeout 90s` failed `TestConfigureDialer_SSRFMultiIPAllFail` (TEST-NET address unexpectedly connectable) and timed out in `TestProxyRoutingMatrix/fasthttp/unset/no-env/https-8443`; stack shows Windows DNS lookup. This is environment-dependent, outside this source scope. Log: `transient-http-r14-utils-package-final.txt`. The failed broad run is retained. No gateway or OpenCodex process was stopped.
- `BenchmarkStreamPassthroughSuccess` exercises the entire successful shared streaming loop. Baseline exact HEAD `passthrough_stream.go` was supplied through a Go build overlay, without modifying actual source. `go test -overlay evidence/transient-http-r14-stream-overlay.json ./core/providers/utils -run '^$' -bench '^BenchmarkStreamPassthroughSuccess$' -benchmem -count=1`: PASS, 18,362 ns/op, 12,449 B/op, 40 allocs/op. Current source same command without overlay: PASS, 18,496 ns/op, 12,449 B/op, 40 allocs/op. Single runs, no statistical claim. An initial PowerShell equals-form overlay invocation misparsed the filename; the successful baseline was invoked with explicit subprocess arguments. Logs: `transient-http-r14-stream-benchmark-before.txt`, `transient-http-r14-stream-benchmark-after.txt`.
- Harness fixture successful unary replies include nonempty `output_text`, satisfying the collection-level content assertion. All four cases also assert absence of the first error marker. Temporary large recovered/augmented JSON artifacts were removed after validation; exact validator tools remain available, and the commands can regenerate them.

- `go test ./core/providers/utils -skip '^(TestProxyRoutingMatrix|TestConfigureDialer_SSRFMultiIPAllFail)$' -count=1 -timeout 90s`: also timed out, this time in `TestWebSocketProxyMatrix/unset/HTTPS_PROXY+NO_PROXY/http`; stack again shows Windows DNS lookup. Log: `transient-http-r14-utils-except-environment.txt`. These broad environment-dependent gates remain unverified; no further broad retries were launched. All Worker test processes reached terminal state before handoff.

No candidate commit was created because the explicit complete-body/no-replay requirement is contradicted by the real malformed-chunked regression. HEAD remains the admitted base SHA. The Goal remains active, awaiting the scope decision already requested. This is not independent QA, acceptance or CrewSync DONE.
