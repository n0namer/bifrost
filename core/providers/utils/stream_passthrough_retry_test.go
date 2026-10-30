package utils

import (
	"context"
	"strings"
	"testing"

	"github.com/maximhq/bifrost/core/schemas"
)

func TestFirstStreamChunkPassthrough429RetryClassifier(t *testing.T) {
	src := make(chan *schemas.BifrostStreamChunk, 2)
	src <- &schemas.BifrostStreamChunk{BifrostPassthroughResponse: &schemas.BifrostPassthroughResponse{StatusCode: 429, Body: []byte(`{"error":"limited"}`)}}
	close(src)
	code := 429
	expected := &schemas.BifrostError{StatusCode: &code, Error: &schemas.ErrorField{Message: "retryable"}}
	got, done, err := CheckFirstStreamChunkForError(context.Background(), src, func(first *schemas.BifrostStreamChunk) *schemas.BifrostError {
		if first.BifrostPassthroughResponse != nil && first.BifrostPassthroughResponse.StatusCode == 429 {
			return expected
		}
		return nil
	})
	if got != nil || err != expected {
		t.Fatalf("first failure must remain internal: stream=%v err=%v", got, err)
	}
	<-done
}

func TestFirstStreamChunkPassthrough429BufferOverflowFailsClosed(t *testing.T) {
	first := &schemas.BifrostStreamChunk{BifrostPassthroughResponse: &schemas.BifrostPassthroughResponse{StatusCode: 429, Headers: map[string]string{"X-Origin": "kept"}, Body: []byte("first")}}
	rest := make(chan *schemas.BifrostStreamChunk, 1)
	lastBody := strings.Repeat("x", maxPassthrough429RetryBodyBytes)
	last := &schemas.BifrostStreamChunk{BifrostPassthroughResponse: &schemas.BifrostPassthroughResponse{StatusCode: 429, Body: []byte(lastBody)}}
	rest <- last
	close(rest)
	classified := false
	got, done, retryErr, handled := bufferPassthrough429ForRetry(first, rest, func(*schemas.BifrostStreamChunk) *schemas.BifrostError {
		classified = true
		return nil
	})
	if !handled || retryErr != nil || classified {
		t.Fatalf("overflow must bypass retry classification: handled=%v retryErr=%v classified=%v", handled, retryErr, classified)
	}
	var chunks []*schemas.BifrostStreamChunk
	for chunk := range got {
		chunks = append(chunks, chunk)
	}
	<-done
	if len(chunks) != 2 || chunks[0] != first || chunks[1] != last || chunks[0].BifrostPassthroughResponse.StatusCode != 429 || chunks[0].BifrostPassthroughResponse.Headers["X-Origin"] != "kept" || string(chunks[1].BifrostPassthroughResponse.Body) != lastBody {
		t.Fatalf("overflow did not preserve the original stream: chunks=%d", len(chunks))
	}
}

func TestFirstStreamChunkPassthroughNoRetryPreservesRawStream(t *testing.T) {
	src := make(chan *schemas.BifrostStreamChunk, 2)
	original := &schemas.BifrostStreamChunk{BifrostPassthroughResponse: &schemas.BifrostPassthroughResponse{StatusCode: 429, Headers: map[string]string{"x-should-retry": "false"}, Body: []byte("opaque")}}
	src <- original
	close(src)
	got, done, err := CheckFirstStreamChunkForError(context.Background(), src, func(first *schemas.BifrostStreamChunk) *schemas.BifrostError {
		return nil
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	first, ok := <-got
	if !ok || first != original {
		t.Fatalf("raw error must remain visible to caller: chunk=%v ok=%v", first, ok)
	}
	for range got {
	}
	<-done
}
