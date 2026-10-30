"""One POST to an explicit loopback port; caller supplies a 95s wall deadline."""
from __future__ import annotations
import argparse
import json
import re
import time
from urllib.request import Request, build_opener, ProxyHandler


def validate_sse(status: int, raw: str, sentinel: str) -> dict:
    events, pending, malformed = [], [], False
    for line in raw.splitlines():
        if line.startswith('data:'):
            pending.append(line[5:].lstrip(' '))
        elif not line and pending:
            payload = '\n'.join(pending)
            pending = []
            if payload == '[DONE]':
                continue
            try:
                event = json.loads(payload)
                if not isinstance(event, dict):
                    raise ValueError('NON_OBJECT_EVENT')
                events.append(event)
            except ValueError:
                malformed = True
    malformed = malformed or bool(pending)
    types = [event.get('type') for event in events]
    completed = [event for event in events if event.get('type') == 'response.completed']
    response = completed[0].get('response') if completed else None
    terminal_status = response.get('status') if isinstance(response, dict) else None
    text = ''.join(str(event.get('delta', '')) for event in events
                   if event.get('type') == 'response.output_text.delta')
    errors = any(t in ('error', 'response.failed', 'response.incomplete', 'response.cancelled') for t in types)
    good = (status == 200 and len(completed) == 1 and terminal_status == 'completed'
            and sentinel in text and not errors and not malformed)
    return {'httpStatus': status, 'completedCount': len(completed),
            'terminalStatus': terminal_status, 'semanticSentinelPresent': sentinel in text,
            'errorEvent': errors, 'malformedSSE': malformed,
            'eventTypes': sorted({str(t) for t in types}), 'pass': good}


def probe(port: int, sentinel: str, timeout: float) -> dict:
    if not 1 <= port <= 65535:
        raise ValueError('PORT_OUT_OF_RANGE')
    if not re.fullmatch(r'[A-Z0-9_]{1,64}', sentinel):
        raise ValueError('SAFE_SENTINEL_REQUIRED')
    if not 0 < timeout <= 90:
        raise ValueError('TIMEOUT_OUT_OF_RANGE')
    body = {'model': 'gpt-6.1-sol', 'input': [{'role': 'user', 'content': [
        {'type': 'input_text', 'text': f'Reply with exactly {sentinel}.'}]}],
        'store': False, 'stream': True}
    request = Request(f'http://127.0.0.1:{port}/openai_passthrough/v1/responses',
                      data=json.dumps(body).encode(), method='POST', headers={
                          'Content-Type': 'application/json', 'Accept': 'text/event-stream',
                          'Authorization': 'Bearer test-key-no-provider', 'Connection': 'close'})
    started = time.monotonic()
    with build_opener(ProxyHandler({})).open(request, timeout=timeout) as response:
        raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise RuntimeError('SSE_PROBE_BODY_LIMIT')
        result = validate_sse(response.status, raw.decode('utf-8', errors='strict'), sentinel)
    result.update(port=port, seconds=round(time.monotonic() - started, 3), clientRetries=0)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--sentinel', default='RETRY_R17_OK')
    parser.add_argument('--timeout', type=float, default=90)
    args = parser.parse_args()
    try:
        result = probe(args.port, args.sentinel, args.timeout)
    except Exception as exc:
        result = {'pass': False, 'port': args.port, 'clientRetries': 0, 'error': type(exc).__name__}
    print(json.dumps(result, separators=(',', ':')), flush=True)
    return 0 if result['pass'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
