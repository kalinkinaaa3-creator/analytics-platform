import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';

export const sessionRoot = process.env.TARA_SESSION_DIR || '/sessions';

export function sessionPath(name) {
  if (!/^[a-f0-9]{32}\.json$/.test(String(name))) throw new Error('Invalid session reference');
  return path.join(sessionRoot, name);
}

export function validTaraUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && !url.username && !url.password &&
      (!url.port || url.port === '443') &&
      (url.hostname === 'tara.ru' || url.hostname.endsWith('.tara.ru'));
  } catch { return false; }
}

export function internalAccess(req, res, next) {
  const expected = process.env.TARA_SERVICE_KEY || process.env.INTERNAL_API_KEY || '';
  const supplied = String(req.headers['x-tara-service-key'] || '');
  if (!expected || supplied.length !== expected.length ||
      !crypto.timingSafeEqual(Buffer.from(supplied), Buffer.from(expected))) {
    return res.status(403).json({ error: 'Internal access required' });
  }
  next();
}

export async function saveState(filename, state) {
  await fs.mkdir(path.dirname(filename), { recursive: true, mode: 0o700 });
  const temporary = `${filename}.${crypto.randomUUID()}.tmp`;
  await fs.writeFile(temporary, JSON.stringify(state), { mode: 0o600 });
  await fs.rename(temporary, filename);
}

export async function workerState(version, id) {
  sessionPath(version);
  const filename = path.join(sessionRoot, 'workers', version, `${id}.json`);
  try { return JSON.parse(await fs.readFile(filename, 'utf8')); }
  catch (error) {
    if (error.code !== 'ENOENT') throw error;
    return JSON.parse(await fs.readFile(sessionPath(version), 'utf8'));
  }
}

export function workerPath(version, id) {
  sessionPath(version);
  return path.join(sessionRoot, 'workers', version, `${id}.json`);
}

export function denied(status, html) {
  return [401, 403, 502].includes(status) || /access denied|request blocked|403\s*(?:error|forbidden)|доступ к сайту[\s\S]{0,200}запрещен/i.test(html);
}
