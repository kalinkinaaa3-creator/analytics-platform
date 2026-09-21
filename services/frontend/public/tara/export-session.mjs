import { writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

// Node.js 22+. Reads only the open spb.tara.ru tab's cookies/localStorage.
let socket;
const pending = new Map();
let sequence = 0;
function call(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error(`Timeout: ${method}`));
    }, 10000);
    pending.set(id, { resolve, reject, timer });
    socket.send(JSON.stringify({ id, method, params }));
  });
}
try {
  if (typeof WebSocket === 'undefined') throw new Error('Node.js 22+ required.');
  const response = await fetch('http://127.0.0.1:9222/json/list', {
    signal: AbortSignal.timeout(5000),
  });
  if (!response.ok) throw new Error('Cannot list browser tabs.');
  const tabs = await response.json();
  const tab = tabs.find(t => {
    try { return t.type === 'page' && new URL(t.url).origin === 'https://spb.tara.ru'; }
    catch { return false; }
  });
  if (!tab) throw new Error('Open a working https://spb.tara.ru product tab first.');
  const endpoint = new URL(tab.webSocketDebuggerUrl);
  if (!['127.0.0.1', 'localhost'].includes(endpoint.hostname)) {
    throw new Error('Expected a loopback debugging endpoint.');
  }
  socket = new WebSocket(endpoint);
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Browser connection timeout.')), 5000);
    socket.addEventListener('open', () => { clearTimeout(timer); resolve(); }, { once: true });
    socket.addEventListener('error', () => { clearTimeout(timer); reject(new Error('Browser connection failed.')); }, { once: true });
  });
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data);
    const request = pending.get(message.id);
    if (!request) return;
    clearTimeout(request.timer);
    pending.delete(message.id);
    if (message.error) request.reject(new Error('Browser command failed.'));
    else request.resolve(message.result);
  });
  const result = await call('Network.getCookies', { urls: [tab.url, 'https://spb.tara.ru/'] });
  const matching = result.cookies.filter(c => {
    const domain = c.domain.replace(/^\./, '');
    return domain === 'tara.ru' || domain.endsWith('.tara.ru');
  });
  if (matching.some(c => c.partitionKey || c.partitionKeyOpaque)) {
    throw new Error('Partitioned cookies detected; export stopped to avoid an incomplete conversion.');
  }
  const cookies = matching.map(c => ({
    name: c.name, value: c.value, domain: c.domain, path: c.path,
    expires: c.session ? -1 : c.expires,
    httpOnly: c.httpOnly, secure: c.secure, sameSite: c.sameSite || 'Lax',
  }));
  const storage = await call('Runtime.evaluate', {
    expression: `(() => {
      if (location.origin !== 'https://spb.tara.ru') throw new Error('Origin changed');
      return { origin: location.origin, localStorage: Object.keys(localStorage).map(name => ({name, value: localStorage.getItem(name)})) };
    })()`,
    returnByValue: true,
  });
  if (storage.exceptionDetails || !storage.result?.value) throw new Error('Cannot read Tara localStorage.');
  const output = resolve(process.argv[2] || 'tara-session.json');
  await writeFile(output, JSON.stringify({ cookies, origins: [storage.result.value] }, null, 2), {
    flag: 'wx', mode: 0o600,
  });
  console.log(`Saved: ${output}`);
  console.log(`Cookies: ${cookies.length}; localStorage entries: ${storage.result.value.localStorage.length}`);
  console.log('Session values were not printed. Keep this file private.');
} catch (error) {
  console.error(error.code === 'EEXIST' ? 'Output already exists; choose another output filename.' : error.message);
  process.exitCode = 1;
} finally {
  for (const request of pending.values()) clearTimeout(request.timer);
  socket?.close();
}
