import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

const root = await fs.mkdtemp(path.join(os.tmpdir(), 'tara-state-test-'));
process.env.TARA_SESSION_DIR = root;
const { workerState, workerPath, saveState, sessionPath, validTaraUrl, denied } = await import('./sessions.js');
test.after(async () => { await fs.rm(root, { recursive: true, force: true }); });

test('independent worker states survive restart and new generation replaces seeds', async () => {
  const old = 'a'.repeat(32) + '.json';
  const fresh = 'b'.repeat(32) + '.json';
  await saveState(sessionPath(old), { seed: 1 });
  await Promise.all([1,2,3,4,5].map(async id => {
    assert.deepEqual(await workerState(old, id), { seed: 1 });
    await saveState(workerPath(old, id), { worker: id });
  }));
  for (let id = 1; id <= 5; id++) assert.deepEqual(await workerState(old, id), { worker: id });
  await saveState(sessionPath(fresh), { seed: 2 });
  assert.deepEqual(await workerState(fresh, 1), { seed: 2 });
  await saveState(workerPath(old, 1), { obsolete: true });
  assert.deepEqual(await workerState(fresh, 1), { seed: 2 });
});

test('only Tara HTTPS origins and safe session references', () => {
  assert.equal(validTaraUrl('https://kazan.tara.ru/catalog/a/'), true);
  for (const url of ['https://tara.ru.evil.test/', 'http://127.0.0.1/', 'https://x@tara.ru/', 'https://tara.ru:9000/']) {
    assert.equal(validTaraUrl(url), false);
  }
  assert.throws(() => sessionPath('../secret'));
});

test('404 stays distinct from access denial', () => {
  assert.equal(denied(404, 'product not found'), false);
  assert.equal(denied(403, 'Forbidden'), true);
  assert.equal(denied(200, 'Доступ к сайту spb.tara.ru запрещен'), true);
});
