// Local test upstream for collection folder 297. Never forwards to a provider.
import http from 'node:http';
const probes = new Map();
http.createServer((req, res) => {
  const url = new URL(req.url, 'http://127.0.0.1');
  const status = Number(url.searchParams.get('status'));
  const probe = url.searchParams.get('probe') || req.headers['x-fixture-probe'];
  if (req.method === 'GET' && url.pathname === '/count' && probe) {
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ sends: probes.get(probe) || 0 })); return;
  }
  const nativeMode = req.headers['x-fixture-mode'];
  const native = ['comment', 'broken-http'].includes(nativeMode) && ['/chat/completions', '/v1/chat/completions', '/responses', '/v1/responses'].includes(url.pathname);
  if (req.method !== 'POST' || !probe || (!native && (url.pathname !== '/v1/responses' || ![502, 509].includes(status)))) {
    res.writeHead(400); res.end('invalid fixture request'); return;
  }
  let body = '';
  req.on('data', chunk => {
    body += chunk;
    if (body.length > 65536) req.destroy();
  });
  req.on('end', () => {
    let parsed;
    try { parsed = JSON.parse(body); } catch { res.writeHead(400); res.end('invalid JSON'); return; }
    if (!probes.has(probe) && probes.size >= 10000) { res.writeHead(507); res.end('fixture probe limit'); return; }
    const sends = (probes.get(probe) || 0) + 1;
    probes.set(probe, sends);
    res.setHeader('x-fixture-sends', String(sends));
    if (native) {
      res.writeHead(200, { 'content-type': 'text/event-stream' });
      if (nativeMode === 'broken-http') {
        res.flushHeaders(); res.write(': keepalive\n\n');
        setTimeout(() => res.destroy(), 20);
      } else { res.end(': keepalive\n\n'); }
      return;
    }
    if (sends === 1) {
      res.writeHead(status, { 'content-type': 'application/json' });
      res.end(JSON.stringify({ error: { code: 'temporary_fixture_error' } })); return;
    }
    if (parsed.stream) {
      res.writeHead(200, { 'content-type': 'text/event-stream' });
      res.end('event: response.completed\ndata: ' + JSON.stringify({ type: 'response.completed', response: { id: 'transient-ok', object: 'response', output_text: 'fixture ok', sends } }) + '\n\n');
    } else {
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end(JSON.stringify({ id: 'transient-ok', object: 'response', output_text: 'fixture ok', sends }));
    }
  });
}).listen(18791, '127.0.0.1', () => console.log('transient HTTP test upstream: 127.0.0.1:18791'));
