package bifrost

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/maximhq/bifrost/core/providers/openai"
	"github.com/maximhq/bifrost/core/schemas"
)

func TestPassthroughTransientPhysicalSends(t *testing.T) {
	for _, status := range []int{500, 502, 503, 504, 509, 529} {
		for _, streaming := range []bool{false, true} {
			for _, mode := range []string{"recover", "header", "split refused", "late quota", "exhaust"} {
				t.Run(fmt.Sprintf("%d/stream=%v/%s", status, streaming, mode), func(t *testing.T) {
					var sends atomic.Int32
					srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
						n := sends.Add(1)
						w.Header().Set("Content-Type", "application/json")
						w.Header().Set("X-Origin", fmt.Sprint(n))
						if mode == "header" {
							w.Header().Set("X-Should-Retry", "false")
						}
						if mode == "recover" && n > 1 {
							w.WriteHeader(200)
							fmt.Fprint(w, `{"ok":true}`)
							return
						}
						w.WriteHeader(status)
						fmt.Fprint(w, "raw-first:")
						w.(http.Flusher).Flush()
						switch mode {
						case "split refused":
							fmt.Fprint(w, "upstream_reset_")
							w.(http.Flusher).Flush()
							fmt.Fprint(w, "replay_refused")
						case "late quota":
							fmt.Fprint(w, "insufficient_quota")
						default:
							fmt.Fprint(w, "temporary")
						}
					}))
					defer srv.Close()
					config := pilotRetryConfig(2)
					logger := NewDefaultLogger(schemas.LogLevelError)
					provider := openai.NewOpenAIProvider(config, logger)
					ctx := pilotRetryContext()
					req := &schemas.BifrostPassthroughRequest{Method: "POST", Path: "/v1/responses", UpstreamURL: srv.URL, Body: []byte(`{"model":"test"}`)}
					var body strings.Builder
					gotStatus := 0
					var headers map[string]string
					if streaming {
						handler := func(key schemas.Key) (chan *schemas.BifrostStreamChunk, *schemas.BifrostError) {
							return provider.PassthroughStream(ctx, func(_ *schemas.BifrostContext, r *schemas.BifrostResponse, e *schemas.BifrostError) (*schemas.BifrostResponse, *schemas.BifrostError) {
								return r, e
							}, nil, key, req)
						}
						ch, err := executeRequestWithRetries(ctx, config, handler, nil, schemas.PassthroughStreamRequest, schemas.OpenAI, "test", nil, logger)
						if err != nil || ch == nil {
							t.Fatalf("err=%+v", err)
						}
						for chunk := range ch {
							if chunk.BifrostError != nil {
								t.Fatalf("chunk error=%+v", chunk.BifrostError)
							}
							if p := chunk.BifrostPassthroughResponse; p != nil {
								gotStatus = p.StatusCode
								headers = p.Headers
								body.Write(p.Body)
							}
						}
					} else {
						handler := func(key schemas.Key) (*schemas.BifrostResponse, *schemas.BifrostError) {
							p, err := provider.Passthrough(ctx, key, req)
							return &schemas.BifrostResponse{PassthroughResponse: p}, err
						}
						resp, err := executeRequestWithRetries(ctx, config, handler, nil, schemas.PassthroughRequest, schemas.OpenAI, "test", nil, logger)
						if err != nil || resp == nil {
							t.Fatalf("err=%+v", err)
						}
						p := resp.PassthroughResponse
						gotStatus = p.StatusCode
						headers = p.Headers
						body.Write(p.Body)
					}
					wantSends, wantStatus, wantBody := int32(1), status, "raw-first:temporary"
					switch mode {
					case "recover":
						wantSends, wantStatus, wantBody = 2, 200, `{"ok":true}`
					case "exhaust":
						wantSends = 3
					case "split refused":
						wantBody = "raw-first:upstream_reset_replay_refused"
					case "late quota":
						wantBody = "raw-first:insufficient_quota"
					}
					if sends.Load() != wantSends || gotStatus != wantStatus || body.String() != wantBody || headers["X-Origin"] != fmt.Sprint(wantSends) {
						t.Fatalf("sends=%d want=%d status=%d body=%q headers=%v", sends.Load(), wantSends, gotStatus, body.String(), headers)
					}
				})
			}
		}
	}
}

func TestPassthroughStreamReadFailureNeverReplays(t *testing.T) {
	for _, status := range []int{200, 502, 509} {
		t.Run(fmt.Sprint(status), func(t *testing.T) {
			var sends atomic.Int32
			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				sends.Add(1)
				w.Header().Set("Content-Type", "text/event-stream")
				w.WriteHeader(status)
				fmt.Fprint(w, "data: partial-output\n\n")
				w.(http.Flusher).Flush()
				conn, _, err := w.(http.Hijacker).Hijack()
				if err == nil {
					_ = conn.Close()
				} // No terminating chunk: incomplete HTTP body.
			}))
			defer srv.Close()
			ctx, config := pilotRetryContext(), pilotRetryConfig(2)
			logger := NewDefaultLogger(schemas.LogLevelError)
			provider := openai.NewOpenAIProvider(config, logger)
			runner := func(_ *schemas.BifrostContext, r *schemas.BifrostResponse, e *schemas.BifrostError) (*schemas.BifrostResponse, *schemas.BifrostError) {
				return r, e
			}
			handler := func(key schemas.Key) (chan *schemas.BifrostStreamChunk, *schemas.BifrostError) {
				return provider.PassthroughStream(ctx, runner, nil, key, &schemas.BifrostPassthroughRequest{Method: "POST", Path: "/v1/responses", UpstreamURL: srv.URL, Body: []byte(`{"model":"test"}`)})
			}
			ch, err := executeRequestWithRetries(ctx, config, handler, nil, schemas.PassthroughStreamRequest, schemas.OpenAI, "test", nil, logger)
			if err != nil || ch == nil {
				t.Fatalf("err=%+v", err)
			}
			var body strings.Builder
			readFailed := false
			for chunk := range ch {
				if chunk.BifrostError != nil {
					readFailed = true
				}
				if chunk.BifrostPassthroughResponse != nil {
					body.Write(chunk.BifrostPassthroughResponse.Body)
				}
			}
			if sends.Load() != 1 || !readFailed || body.String() != "data: partial-output\n\n" {
				t.Fatalf("sends=%d readFailed=%v body=%q", sends.Load(), readFailed, body.String())
			}
		})
	}
}

func TestPassthroughLoopTransientHTTP(t *testing.T) {
	for _, status := range []int{429, 500, 502, 503, 504, 509, 529, 400, 401, 501, 505, 511, -1} {
		for _, streaming := range []bool{false, true} {
			t.Run(fmt.Sprintf("%d/stream=%v", status, streaming), func(t *testing.T) {
				calls := 0
				response := func() *schemas.BifrostResponse {
					calls++
					if calls == 1 {
						return pilotResponse(status, "", "temporary", nil)
					}
					return pilotResponse(200, "", "ok", nil)
				}
				wantCalls, wantStatus := 1, status
				switch status {
				case 429, 500, 502, 503, 504, 509, 529:
					wantCalls, wantStatus = 2, 200
				}
				if streaming {
					handler := func(_ schemas.Key) (chan *schemas.BifrostStreamChunk, *schemas.BifrostError) {
						ch := make(chan *schemas.BifrostStreamChunk, 1)
						ch <- &schemas.BifrostStreamChunk{BifrostPassthroughResponse: response().PassthroughResponse}
						close(ch)
						return ch, nil
					}
					got, err := executeRequestWithRetries(pilotRetryContext(), pilotRetryConfig(2), handler, nil, schemas.PassthroughStreamRequest, schemas.OpenAI, "gpt-test", nil, NewDefaultLogger(schemas.LogLevelError))
					if err != nil || got == nil {
						t.Fatalf("err=%+v", err)
					}
					for chunk := range got {
						if chunk.BifrostPassthroughResponse.StatusCode != wantStatus {
							t.Errorf("status=%d want=%d", chunk.BifrostPassthroughResponse.StatusCode, wantStatus)
						}
					}
				} else {
					handler := func(_ schemas.Key) (*schemas.BifrostResponse, *schemas.BifrostError) { return response(), nil }
					got, err := executeRequestWithRetries(pilotRetryContext(), pilotRetryConfig(2), handler, nil, schemas.PassthroughRequest, schemas.OpenAI, "gpt-test", nil, NewDefaultLogger(schemas.LogLevelError))
					if err != nil || got == nil || got.PassthroughResponse.StatusCode != wantStatus {
						t.Errorf("response=%+v err=%+v want status=%d", got, err, wantStatus)
					}
				}
				if calls != wantCalls {
					t.Errorf("physical sends=%d want=%d", calls, wantCalls)
				}
			})
		}
	}
}

func pilotRetryContext() *schemas.BifrostContext {
	ctx := schemas.NewBifrostContext(context.Background(), schemas.NoDeadline)
	ctx.SetValue(schemas.BifrostContextKeyTracer, &schemas.NoOpTracer{})
	return ctx
}

func TestPassthroughLoopTransientGuardsAndExhaustion(t *testing.T) {
	for _, status := range []int{500, 502, 503, 504, 509, 529} {
		for _, streaming := range []bool{false, true} {
			for _, guard := range []string{"header", "quota", "refused", "exhausted", "zero budget"} {
				t.Run(fmt.Sprintf("%d/stream=%v/%s", status, streaming, guard), func(t *testing.T) {
					calls, budget, wantCalls := 0, 2, 1
					if guard == "exhausted" {
						wantCalls = 3
					}
					if guard == "zero budget" {
						budget = 0
					}
					var last *schemas.BifrostPassthroughResponse
					response := func() *schemas.BifrostPassthroughResponse {
						calls++
						h := map[string]string{"X-Origin": fmt.Sprint(calls)}
						body := fmt.Sprintf("raw-%d", calls)
						switch guard {
						case "header":
							h["X-Should-Retry"] = " FALSE "
							h["Retry-After"] = "10"
						case "quota":
							body += "insufficient_quota"
						case "refused":
							body += "upstream_reset_replay_refused"
						}
						last = &schemas.BifrostPassthroughResponse{StatusCode: status, Headers: h, Body: []byte(body)}
						return last
					}
					var got *schemas.BifrostPassthroughResponse
					if streaming {
						handler := func(_ schemas.Key) (chan *schemas.BifrostStreamChunk, *schemas.BifrostError) {
							ch := make(chan *schemas.BifrostStreamChunk, 1)
							ch <- &schemas.BifrostStreamChunk{BifrostPassthroughResponse: response()}
							close(ch)
							return ch, nil
						}
						ch, err := executeRequestWithRetries(pilotRetryContext(), pilotRetryConfig(budget), handler, nil, schemas.PassthroughStreamRequest, schemas.OpenAI, "gpt-test", nil, NewDefaultLogger(schemas.LogLevelError))
						if err != nil || ch == nil {
							t.Fatalf("err=%+v", err)
						}
						for chunk := range ch {
							got = chunk.BifrostPassthroughResponse
						}
					} else {
						handler := func(_ schemas.Key) (*schemas.BifrostResponse, *schemas.BifrostError) {
							return &schemas.BifrostResponse{PassthroughResponse: response()}, nil
						}
						resp, err := executeRequestWithRetries(pilotRetryContext(), pilotRetryConfig(budget), handler, nil, schemas.PassthroughRequest, schemas.OpenAI, "gpt-test", nil, NewDefaultLogger(schemas.LogLevelError))
						if err != nil || resp == nil {
							t.Fatalf("err=%+v", err)
						}
						got = resp.PassthroughResponse
					}
					if calls != wantCalls || got == nil || got.StatusCode != status || string(got.Body) != string(last.Body) || got.Headers["X-Origin"] != last.Headers["X-Origin"] {
						t.Fatalf("sends=%d want=%d got=%+v last=%+v", calls, wantCalls, got, last)
					}
				})
			}
		}
	}
}

func TestPassthroughLoopTransientRetryAfter(t *testing.T) {
	for _, streaming := range []bool{false, true} {
		for _, cancelWait := range []bool{false, true} {
			t.Run(fmt.Sprintf("stream=%v/cancel=%v", streaming, cancelWait), func(t *testing.T) {
				parent, cancel := context.WithCancel(context.Background())
				defer cancel()
				ctx := schemas.NewBifrostContext(parent, schemas.NoDeadline)
				ctx.SetValue(schemas.BifrostContextKeyTracer, &schemas.NoOpTracer{})
				calls := 0
				response := func() *schemas.BifrostPassthroughResponse {
					calls++
					if calls == 1 {
						if cancelWait {
							time.AfterFunc(50*time.Millisecond, cancel)
						}
						return pilotResponse(509, "", "temporary", map[string]string{"Retry-After": "1"}).PassthroughResponse
					}
					return pilotResponse(200, "", "ok", nil).PassthroughResponse
				}
				start := time.Now()
				var err *schemas.BifrostError
				if streaming {
					handler := func(_ schemas.Key) (chan *schemas.BifrostStreamChunk, *schemas.BifrostError) {
						ch := make(chan *schemas.BifrostStreamChunk, 1)
						ch <- &schemas.BifrostStreamChunk{BifrostPassthroughResponse: response()}
						close(ch)
						return ch, nil
					}
					var ch chan *schemas.BifrostStreamChunk
					ch, err = executeRequestWithRetries(ctx, pilotRetryConfig(2), handler, nil, schemas.PassthroughStreamRequest, schemas.OpenAI, "gpt-test", nil, NewDefaultLogger(schemas.LogLevelError))
					if ch != nil {
						for range ch {
						}
					}
				} else {
					handler := func(_ schemas.Key) (*schemas.BifrostResponse, *schemas.BifrostError) {
						return &schemas.BifrostResponse{PassthroughResponse: response()}, nil
					}
					_, err = executeRequestWithRetries(ctx, pilotRetryConfig(2), handler, nil, schemas.PassthroughRequest, schemas.OpenAI, "gpt-test", nil, NewDefaultLogger(schemas.LogLevelError))
				}
				elapsed := time.Since(start)
				if cancelWait {
					if calls != 1 || err == nil || elapsed >= time.Second {
						t.Fatalf("sends=%d err=%+v elapsed=%s", calls, err, elapsed)
					}
				} else if calls != 2 || err != nil || elapsed < time.Second {
					t.Fatalf("sends=%d err=%+v elapsed=%s", calls, err, elapsed)
				}
			})
		}
	}
}
func pilotRetryConfig(max int) *schemas.ProviderConfig {
	return createTestConfig(max, time.Millisecond, 5*time.Millisecond)
}
func pilotResponse(status int, code, content string, h map[string]string) *schemas.BifrostResponse {
	return &schemas.BifrostResponse{PassthroughResponse: &schemas.BifrostPassthroughResponse{
		StatusCode: status, Body: []byte(content), Headers: h,
	}}
}
func TestPassthroughLoopRetriesOrdinary429(t *testing.T) {
	calls := 0
	handler := func(_ schemas.Key) (*schemas.BifrostResponse, *schemas.BifrostError) {
		calls++
		if calls == 1 {
			return pilotResponse(429, "rate_limit_exceeded", `{"error":{"code":"rate_limit_exceeded"}}`, map[string]string{"Retry-After": "1"}), nil
		}
		return pilotResponse(200, "", "ok", nil), nil
	}
	got, err := executeRequestWithRetries(pilotRetryContext(), pilotRetryConfig(2), handler, nil, schemas.PassthroughRequest, schemas.OpenAI, "gpt-test", nil, NewDefaultLogger(schemas.LogLevelError))
	if err != nil || got == nil || got.PassthroughResponse == nil || got.PassthroughResponse.StatusCode != 200 || calls != 2 {
		t.Fatalf("calls=%d response=%+v err=%+v", calls, got, err)
	}
}
func TestPassthroughLoopRespectsNoRetry(t *testing.T) {
	calls := 0
	handler := func(_ schemas.Key) (*schemas.BifrostResponse, *schemas.BifrostError) {
		calls++
		return pilotResponse(429, "", "original-raw-429", map[string]string{"x-should-retry": "false"}), nil
	}
	got, err := executeRequestWithRetries(pilotRetryContext(), pilotRetryConfig(3), handler, nil, schemas.PassthroughRequest, schemas.OpenAI, "gpt-test", nil, NewDefaultLogger(schemas.LogLevelError))
	if err != nil || got == nil || got.PassthroughResponse == nil || got.PassthroughResponse.StatusCode != 429 || string(got.PassthroughResponse.Body) != "original-raw-429" || calls != 1 {
		t.Fatalf("calls=%d response=%+v err=%+v", calls, got, err)
	}
}
func TestPassthroughLoopExhaustionPreservesRaw429(t *testing.T) {
	calls := 0
	handler := func(_ schemas.Key) (*schemas.BifrostResponse, *schemas.BifrostError) {
		calls++
		return pilotResponse(429, "", "original-raw-429", map[string]string{"Retry-After": "1"}), nil
	}
	got, err := executeRequestWithRetries(pilotRetryContext(), pilotRetryConfig(2), handler, nil, schemas.PassthroughRequest, schemas.OpenAI, "gpt-test", nil, NewDefaultLogger(schemas.LogLevelError))
	if err != nil || got == nil || got.PassthroughResponse == nil || got.PassthroughResponse.StatusCode != 429 || string(got.PassthroughResponse.Body) != "original-raw-429" || calls != 3 {
		t.Fatalf("calls=%d response=%+v err=%+v", calls, got, err)
	}
}
func TestPassthroughLoopStream429BeforeOutput(t *testing.T) {
	calls := 0
	handler := func(_ schemas.Key) (chan *schemas.BifrostStreamChunk, *schemas.BifrostError) {
		calls++
		stream := make(chan *schemas.BifrostStreamChunk, 2)
		if calls == 1 {
			stream <- &schemas.BifrostStreamChunk{BifrostPassthroughResponse: &schemas.BifrostPassthroughResponse{StatusCode: 429, Body: []byte(`{"error":{"code":"rate_limit_exceeded"}}`)}}
		} else {
			stream <- &schemas.BifrostStreamChunk{BifrostPassthroughResponse: &schemas.BifrostPassthroughResponse{StatusCode: 200, Body: []byte("event: response.completed\\n\\n")}}
		}
		close(stream)
		return stream, nil
	}
	got, err := executeRequestWithRetries(pilotRetryContext(), pilotRetryConfig(2), handler, nil, schemas.PassthroughStreamRequest, schemas.OpenAI, "gpt-test", nil, NewDefaultLogger(schemas.LogLevelError))
	if err != nil || calls != 2 || got == nil {
		t.Fatalf("calls=%d got=%v err=%+v", calls, got, err)
	}
	first, ok := <-got
	if !ok || first.BifrostPassthroughResponse == nil || first.BifrostPassthroughResponse.StatusCode != 200 {
		t.Fatalf("first=%+v ok=%v", first, ok)
	}
	for range got {
	}
}
func TestPassthroughLoopStreamNoReplayHeader(t *testing.T) {
	calls := 0
	handler := func(_ schemas.Key) (chan *schemas.BifrostStreamChunk, *schemas.BifrostError) {
		calls++
		stream := make(chan *schemas.BifrostStreamChunk, 1)
		stream <- &schemas.BifrostStreamChunk{BifrostPassthroughResponse: &schemas.BifrostPassthroughResponse{StatusCode: 429, Headers: map[string]string{"x-should-retry": "false"}, Body: []byte("raw-error")}}
		close(stream)
		return stream, nil
	}
	got, err := executeRequestWithRetries(pilotRetryContext(), pilotRetryConfig(3), handler, nil, schemas.PassthroughStreamRequest, schemas.OpenAI, "gpt-test", nil, NewDefaultLogger(schemas.LogLevelError))
	if err != nil || calls != 1 || got == nil {
		t.Fatalf("calls=%d got=%v err=%+v", calls, got, err)
	}
	first, ok := <-got
	if !ok || first.BifrostPassthroughResponse == nil || first.BifrostPassthroughResponse.StatusCode != 429 || string(first.BifrostPassthroughResponse.Body) != "raw-error" {
		t.Fatalf("first=%+v ok=%v", first, ok)
	}
	for range got {
	}
}

func TestPassthroughLoopStreamLateReplayRefusedMarkerNeverReplays(t *testing.T) {
	for _, status := range []int{429, 502, 509} {
		t.Run(fmt.Sprint(status), func(t *testing.T) {
			tests := []struct {
				name  string
				parts []string
			}{
				{"split replay refused", []string{`{"error":{"code":"upstream_reset_`, `replay_refused"}}`}},
				{"late insufficient quota", []string{`{"error":{"code":"rate_limit_exceeded"}}`, `{"error":{"code":"insufficient_quota"}}`}},
			}
			for _, tt := range tests {
				t.Run(tt.name, func(t *testing.T) {
					calls := 0
					wantHeaders := map[string]string{"Content-Type": "application/json", "X-Upstream": "kept"}
					handler := func(_ schemas.Key) (chan *schemas.BifrostStreamChunk, *schemas.BifrostError) {
						calls++
						stream := make(chan *schemas.BifrostStreamChunk, len(tt.parts))
						for i, part := range tt.parts {
							headers := map[string]string(nil)
							if i == 0 {
								headers = wantHeaders
							}
							stream <- &schemas.BifrostStreamChunk{BifrostPassthroughResponse: &schemas.BifrostPassthroughResponse{StatusCode: status, Headers: headers, Body: []byte(part)}}
						}
						close(stream)
						return stream, nil
					}
					got, err := executeRequestWithRetries(pilotRetryContext(), pilotRetryConfig(3), handler, nil, schemas.PassthroughStreamRequest, schemas.OpenAI, "gpt-test", nil, NewDefaultLogger(schemas.LogLevelError))
					if err != nil || got == nil || calls != 1 {
						t.Fatalf("calls=%d got=%v err=%+v", calls, got, err)
					}
					var body string
					var first *schemas.BifrostPassthroughResponse
					for chunk := range got {
						if chunk.BifrostPassthroughResponse == nil {
							t.Fatalf("unexpected chunk: %+v", chunk)
						}
						if first == nil {
							first = chunk.BifrostPassthroughResponse
						}
						body += string(chunk.BifrostPassthroughResponse.Body)
					}
					wantBody := ""
					for _, part := range tt.parts {
						wantBody += part
					}
					if first == nil || first.StatusCode != status || first.Headers["Content-Type"] != wantHeaders["Content-Type"] || first.Headers["X-Upstream"] != wantHeaders["X-Upstream"] || body != wantBody {
						t.Fatalf("raw response lost: first=%+v body=%q want=%q", first, body, wantBody)
					}
				})
			}
		})
	}
}

// A successful HTTP envelope does not prove that an already-sent generation
// POST is safe to replay. Count actual requests through core, including fallbacks.
func TestNativeStreamAmbiguousPOSTNeverReplays(t *testing.T) {
	for _, responses := range []bool{false, true} {
		for _, mode := range []string{"empty", "comment", "incomplete-event", "partial-output", "complete"} {
			for _, brokenHTTP := range []bool{false, true} {
				if mode == "complete" && brokenHTTP {
					continue // terminal-event transport-tail handling has separate provider coverage
				}
				t.Run(fmt.Sprintf("responses=%v/%s/broken-http=%v", responses, mode, brokenHTTP), func(t *testing.T) {
					var primarySends, fallbackSends atomic.Int32
					body := ""
					switch mode {
					case "comment":
						body = ": keepalive\n\n"
					case "incomplete-event":
						body = "data: {\"id\":\"partial\""
					case "partial-output", "complete":
						if responses {
							body = "event: response.output_text.delta\ndata: {\"type\":\"response.output_text.delta\",\"item_id\":\"msg_1\",\"output_index\":0,\"content_index\":0,\"delta\":\"hello\"}\n\n"
							if mode == "complete" {
								body += "event: response.completed\ndata: {\"type\":\"response.completed\",\"response\":{\"id\":\"resp_1\",\"object\":\"response\",\"status\":\"completed\",\"model\":\"gpt-4o-mini\",\"output\":[],\"usage\":{\"input_tokens\":1,\"output_tokens\":1,\"total_tokens\":2}}}\n\n"
							}
						} else {
							body = "data: {\"id\":\"chatcmpl-1\",\"object\":\"chat.completion.chunk\",\"created\":1,\"model\":\"gpt-4o-mini\",\"choices\":[{\"index\":0,\"delta\":{\"content\":\"hello\"},\"finish_reason\":null}]}\n\n"
							if mode == "complete" {
								body += "data: {\"id\":\"chatcmpl-1\",\"object\":\"chat.completion.chunk\",\"created\":1,\"model\":\"gpt-4o-mini\",\"choices\":[{\"index\":0,\"delta\":{},\"finish_reason\":\"stop\"}]}\n\ndata: [DONE]\n\n"
							}
						}
					}
					primary := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
						if req.Method != http.MethodPost {
							t.Errorf("unexpected upstream method %s", req.Method)
						}
						primarySends.Add(1)
						w.Header().Set("Content-Type", "text/event-stream")
						w.WriteHeader(http.StatusOK)
						w.(http.Flusher).Flush()
						fmt.Fprint(w, body)
						w.(http.Flusher).Flush()
						if brokenHTTP {
							panic(http.ErrAbortHandler) // omit terminating zero chunk
						}
					}))
					defer primary.Close()
					fallback := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
						fallbackSends.Add(1)
						anthropicMessagesHandler()(w, req)
					}))
					defer fallback.Close()
					account := NewMockAccount()
					for provider, url := range map[schemas.ModelProvider]string{schemas.OpenAI: primary.URL, schemas.Anthropic: fallback.URL} {
						account.AddProviderWithBaseURL(provider, 1, 1, url)
						config := account.configs[provider]
						config.NetworkConfig.MaxRetries = 2
						config.NetworkConfig.RetryBackoffInitial = time.Millisecond
						config.NetworkConfig.RetryBackoffMax = 5 * time.Millisecond
						account.SetKeysForProvider(provider, []schemas.Key{{ID: string(provider), Value: *schemas.NewSecretVar("test-key"), Models: schemas.WhiteList{"*"}, Weight: 100}})
					}
					// Replacement models a plugin that discards the original cause and flags.
					// The transport's replay prohibition must still survive it.
					var plugins []schemas.LLMPlugin
					if mode == "comment" {
						plugins = append(plugins, &retryReplacingStreamPlugin{mutate: brokenHTTP})
					}
					client := newStreamTestClient(t, account, plugins...)
					ctx := schemas.NewBifrostContext(context.Background(), time.Now().Add(10*time.Second))
					req := &schemas.BifrostChatRequest{
						Provider: schemas.OpenAI, Model: "gpt-4o-mini",
						Input:     []schemas.ChatMessage{{Role: schemas.ChatMessageRoleUser, Content: &schemas.ChatMessageContent{ContentStr: schemas.Ptr("hi")}}},
						Fallbacks: []schemas.Fallback{{Provider: schemas.Anthropic, Model: "claude-3-5-haiku-20241022"}},
					}
					var stream chan *schemas.BifrostStreamChunk
					var err *schemas.BifrostError
					if responses {
						stream, err = client.ResponsesStreamRequest(ctx, req.ToResponsesRequest())
					} else {
						stream, err = client.ChatCompletionStreamRequest(ctx, req)
					}
					sawError := err != nil
					if stream != nil {
						for chunk := range stream {
							if chunk != nil && chunk.BifrostError != nil {
								sawError = true
							}
						}
					}
					t.Logf("physical POST sends: primary=%d fallback=%d; sawError=%v", primarySends.Load(), fallbackSends.Load(), sawError)
					if primarySends.Load() != 1 || fallbackSends.Load() != 0 {
						t.Errorf("unsafe replay: primary=%d fallback=%d; want 1+0", primarySends.Load(), fallbackSends.Load())
					}
					if sawError != (mode != "complete") {
						t.Errorf("sawError=%v, mode=%s; incomplete SSE must not become success", sawError, mode)
					}
				})
			}
		}
	}
}

type retryReplacingStreamPlugin struct{ mutate bool }

func (*retryReplacingStreamPlugin) GetName() string { return "retry-replacing-stream" }
func (*retryReplacingStreamPlugin) Cleanup() error  { return nil }
func (*retryReplacingStreamPlugin) PreRequestHook(*schemas.BifrostContext, *schemas.BifrostRequest) error {
	return nil
}
func (*retryReplacingStreamPlugin) PreLLMHook(_ *schemas.BifrostContext, req *schemas.BifrostRequest) (*schemas.BifrostRequest, *schemas.LLMPluginShortCircuit, error) {
	return req, nil, nil
}
func (p *retryReplacingStreamPlugin) PostLLMHook(_ *schemas.BifrostContext, resp *schemas.BifrostResponse, err *schemas.BifrostError) (*schemas.BifrostResponse, *schemas.BifrostError, error) {
	if err == nil {
		return resp, nil, nil
	}
	replacement := schemas.BifrostError{StatusCode: schemas.Ptr(502), Error: &schemas.ErrorField{Message: "plugin replacement"}, AllowFallbacks: schemas.Ptr(true)}
	if p.mutate {
		*err = replacement
		return resp, err, nil
	}
	return resp, &replacement, nil
}
