# Independent R17 source review

QA_ACCEPT

Source SHA: `d45ee450b4a9ab1d49bb045ae1b1a8224f5be131`. This is acceptance of the frozen source MVP only, not binary, deployment, canary or CrewSync DONE. Reviewer thread `01a18dba-d3b3-7300-84fe-cbdaff292365` continued independently from the R16 rejection. Effective model/effort requested as Terra/high is **not independently visible in this session**; do not treat that setting as verified. Outer native skill transport is not visible. The same original Goal read back `complete`, createdAt `1793379227`, 112522 tokens and 488 seconds from R16. The available native update API cannot reactivate a completed Goal or set an objective, so it was preserved unchanged; no replacement Goal or claimed R17 Goal accounting was created.

## Judgment and compatibility

No additional concrete blocker was established in the requested source scope. R17 retains `ErrUnexpectedEOF` in the transport, restores the native upstream 502/provider_connection_failed and wrapped unexpected-EOF classification, and independently makes ambiguous truncation `ReplayUnsafe`. The retry loop and primary/chained fallback guards reject that flag. Post-hook code latches it over replacement, mutation and a nil/nil result; TTFT construction and settlement preserve 504/ttft_timeout while refusing uncertain replay; HTTP 200 non-SSE failure is likewise unsafe. The 32 real local-server physical cases exercised chat and Responses, empty/comment/incomplete and partial streams, complete and broken framing, non-SSE, TTFT, and mutating hooks: each logged **1 primary POST, 0 fallback POSTs**, with expected error count, content and completion checks. Complete successful streams and explicit error recovery are separately tested.

The prior R16 expectation of automatic native pre-output retry is intentionally superseded by the approved no-ambiguous-POST policy. Likewise TTFT no longer automatically falls back: missing headers/tokens do not prove non-dispatch. Positive complete explicit 429/500/502/503/504/509/529 passthrough rejection retries, budget, Retry-After and guard/exhaustion tests passed in the selected core suite. A stale comment in `core/providers/utils/nonssestream_test.go` still describes 200 non-SSE as retryable; its assertions check the upstream 502 shape, not replay permission. This documentation/test-name discrepancy does not override the physical no-replay tests.

## Independent test execution

All commands below ran from `core` with exact `C:/Users/Рафик/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.27.3.windows-amd64/bin/go.exe`, its bin prepended to process PATH, and process-local `GOPROXY=off`, `GOSUMDB=off`, `GOTOOLCHAIN=local`, `GOMAXPROCS=2`. No cache patches, overlays, downloads or live API calls. Logs below are in the adjacent evidence directory. Test names were listed before running; selected names were nonempty.

1. `go test ./providers/openai -count=1 -timeout=120s` — PASS, 17.356s. Separate verbose named run confirmed execution and PASS of `TestChatStreamTruncatedPreFirstByte`, `TestChatStreamTruncatedMidStream`, `TestTextCompletionStreamTruncated`, `TestResponsesStreamTruncatedBeforeCompleted`, `TestChatStreamCleanDoneUnaffected`, and both `TestCustomToolStreamRestorer` cases. Tool restorer tests cover stream transformations, not an end-to-end provider tool execution.
2. `go test . -run '^(TestNativeStreamAmbiguousPOSTNeverReplays|TestStreamTTFT.*|TestPassthrough.*|TestStreamFinalErrorRecovery|TestStreamRetriesExhaustedRunErrorPostHooksOnce|TestStreamRetryRunsPostHooksOnlyForServedAttempt|TestStreamErrorAfterContentDoesNotFallBack|TestStreamFallbackAfterFirstChunkError|TestStreamRetryAfterFirstChunkError|TestStream.*Preamble.*)$' -count=1 -timeout=120s -v` — PASS, 9.880s, including 32/32 physical cases and passthrough/TTFT/fallback controls.
3. `go test ./providers/utils -run '^(TestContextTransport_.*|TestStreamPassthrough_.*|TestCheckStreamPreamble.*|TestCheckFirstStreamChunk.*|TestAttemptAbort_.*|TestStreamStartupState.*)$' -count=1 -timeout=90s -v` — PASS, 1.742s, including chunked and fixed-length truncation and connection discard.
4. `git diff --check` passed; tracked tree clean and HEAD remained `d45ee450b4a9ab1d49bb045ae1b1a8224f5be131` after tests. Process snapshot found no command line naming the checkout, but this does not prove the absence of all possible writers. GitHub backup SHA was supplied in the handoff, not independently read here.
5. Offline `go list -m -json github.com/valyala/fasthttp` resolves `v1.77.1-0.20261028061327-329917ed143c`, no replacement. R17 does not change core or transports go.mod/go.sum. Framework declares lower v1.74.0; minimum-version selection resolves the approved higher version.

## Limits

The disclosed expanded utils suite is **not passing**: the prior report records a version-consistency guard hard-coded to v1.74.0, an SSRF TEST-NET connection unexpectedly succeeding, a zero-latency timing assertion, and a 180-second proxy matrix timeout. They were not rerun or all proven pre-existing. Source MVP acceptance is appropriate for the bounded direct-loopback repair with these limitations explicit, not a whole-utils-suite claim. The r17 module-version discrepancy remains a broader integration/CI issue. Binary build and dependency metadata, 29 isolated binary fixtures, live streaming E2E, canary/rollback and authoritative CrewSync readback remain future gates. No production source, Git index/HEAD, config, services or task status was changed. BMad Code Review discipline was applied to the approved source and spec without a new approval checkpoint; no parallel independent review is claimed.

## Evidence log SHA-256
- `r17-qa-core-list.txt` — `8f64f467b32843d538be5fe70ac8851d25d2650052f65c15c66e462c9193f718`
- `r17-qa-core.txt` — `b786ce727b8b832d065574860db044870143b498b5e1fac05c3cb2c4207bd89c`
- `r17-qa-module.txt` — `79542dd8c6a4caa79ca997b97f982ca9ca49061834164c2d8e053334db55006a`
- `r17-qa-openai-list.txt` — `9f944e8eba4a5ad3e50f64969a58cdea291f2995d78705d2f4921e6dd5f5a9f0`
- `r17-qa-openai-named.txt` — `9d524879915f3ead9eef714023392ab28a41e134233091606dc2d53a8d823ed6`
- `r17-qa-openai.txt` — `32bd38b32e673cff3aaa957eb62db27420decdf0fbdda58e69a829928a196eb3`
- `r17-qa-utils-list.txt` — `f80ffa3ea35a4bad268ec87d89e10a8e422676ac58719583faa01b1b5d881d6a`
- `r17-qa-utils.txt` — `8a8ebe5c4c8f3ebc704598a2f81a78669b15c1d95828deea7b838d99e6ccab6d`
