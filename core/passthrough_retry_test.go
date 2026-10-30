package bifrost

import (
	"strings"
	"testing"

	"github.com/maximhq/bifrost/core/schemas"
)

func BenchmarkPassthroughRetryClassification(b *testing.B) {
	for _, status := range []int{200, 429, 509} {
		name := map[int]string{200: "success", 429: "existing429", 509: "new509"}[status]
		b.Run(name, func(b *testing.B) {
			resp := &schemas.BifrostPassthroughResponse{StatusCode: status, Body: []byte("temporary")}
			b.ReportAllocs()
			for b.Loop() {
				_ = passthroughHTTPRetryError(resp)
			}
		})
	}
}

func TestPassthroughHTTPRetryError(t *testing.T) {
	cases := []struct {
		name      string
		status    int
		headers   map[string]string
		body      string
		wantRetry bool
	}{
		{"temporary 429", 429, map[string]string{"Retry-After": "1"}, `{"error":{"code":"rate_limit_exceeded"}}`, true},
		{"temporary 500", 500, nil, "temporary", true},
		{"temporary 502", 502, nil, "temporary", true},
		{"temporary 503", 503, nil, "temporary", true},
		{"temporary 504", 504, nil, "temporary", true},
		{"temporary 509", 509, nil, "temporary", true},
		{"temporary 529", 529, nil, "temporary", true},
		{"overflow 509", 509, nil, strings.Repeat("x", (1<<20)+1), false},
		{"retry forbidden 429", 429, map[string]string{"X-Should-Retry": "false"}, `{"error":{"code":"rate_limit_exceeded"}}`, false},
		{"retry forbidden mixed case", 429, map[string]string{"x-should-retry": " FALSE "}, `{"error":{"code":"rate_limit_exceeded"}}`, false},
		{"upstream reset refused", 429, map[string]string{}, `{"error":{"code":"upstream_reset_replay_refused"}}`, false},
		{"exhausted quota not retried", 429, map[string]string{}, `{"error":{"code":"insufficient_quota"}}`, false},
		{"non 429 unchanged", 400, map[string]string{}, `{"error":{"code":"invalid_request"}}`, false},
		{"successful unchanged", 200, map[string]string{}, `{"id":"resp_test"}`, false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			p := &schemas.BifrostPassthroughResponse{StatusCode: tc.status, Headers: tc.headers, Body: []byte(tc.body)}
			err := passthroughHTTPRetryError(p)
			if (err != nil) != tc.wantRetry {
				t.Fatalf("retry=%v want=%v", err != nil, tc.wantRetry)
			}
			if err != nil && (err.StatusCode == nil || *err.StatusCode != tc.status || err.IsBifrostError) {
				t.Fatalf("invalid synthetic retry error: %+v", err)
			}
		})
	}
}
