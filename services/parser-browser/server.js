import express from "express";
import { addExtra } from "playwright-extra";
import StealthPlugin from "puppeteer-extra-plugin-stealth";
import playwright from "playwright";
import fs from 'node:fs/promises';
import { sessionPath, validTaraUrl, internalAccess, saveState, workerState, workerPath, denied } from './sessions.js';

console.log("server.js loaded");

const chromium = addExtra(playwright.chromium);
chromium.use(StealthPlugin());

const app = express();
app.use(express.json({ limit: "2mb" }));

const WORKERS_COUNT = Number(process.env.WORKERS_COUNT || 3);
const MAX_REQUESTS_PER_WORKER = Number(process.env.MAX_REQUESTS_PER_WORKER || 30);
const FETCH_TIMEOUT_MS = Number(process.env.FETCH_TIMEOUT_MS || 60000);
const PAGE_WAIT_MS = Number(process.env.PAGE_WAIT_MS || 1000);

const JITTER_MIN_MS = Number(process.env.JITTER_MIN_MS || 3000);
const JITTER_MAX_MS = Number(process.env.JITTER_MAX_MS || 8000);
const WORKER_STARTUP_DELAY_MS = Number(process.env.WORKER_STARTUP_DELAY_MS || 3000);

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function randomInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function isBlockedContent(html) {
  const lower = String(html || "").toLowerCase();

  return (
    lower.includes("access denied") ||
    lower.includes("request blocked")
  );
}

class Worker {
  constructor(id) {
    this.id = id;
    this.browser = null;
    this.context = null;
    this.requests = 0;
    this.busy = false;
    this.version = null;
  }

  async init() {
    console.log(`[W${this.id}] init browser`);

    this.browser = await chromium.launch({
      headless: false,
      args: [
        "--no-sandbox",
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
      ],
    });

    this.context = await this.browser.newContext({
      viewport: { width: 1920, height: 1080 },
      locale: "ru-RU",
      userAgent:
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
      ...(this.version ? { storageState: await workerState(this.version, this.id) } : {}),
    });

    this.requests = 0;
  }

  async restart() {
    console.log(`[W${this.id}] restart`);

    try {
      await this.context?.close();
    } catch {}

    try {
      await this.browser?.close();
    } catch {}

    this.browser = null;
    this.context = null;

    await this.init();
  }

  async fetch(url, version) {
    this.busy = true;

    let page = null;

    try {
      if (this.version !== version) {
        this.version = version;
        await this.restart();
      }
      if (!this.browser || !this.context) {
        await this.init();
      }

      this.requests += 1;

      if (this.requests >= MAX_REQUESTS_PER_WORKER) {
        await this.restart();
      }

      page = await this.context.newPage();

      const response = await page.goto(url, {
        waitUntil: "domcontentloaded",
        timeout: FETCH_TIMEOUT_MS,
      });

      const status = response ? response.status() : null;

      try {
        await page.waitForSelector("body", { timeout: 10000 });
      } catch {}

      await page.waitForTimeout(PAGE_WAIT_MS);

      const html = await page.content();
      const blocked = denied(status, html) || isBlockedContent(html);
      if (status === 200 && !blocked && this.version && /topic__heading|price_matrix_block|props_block__wrapper/.test(html)) {
        await saveState(workerPath(this.version, this.id), await this.context.storageState());
      }

      console.log(
        `[W${this.id}] OK status=${status} blocked=${blocked} html=${html.length} url=${url}`
      );

      return {
        status,
        html,
        blocked,
        final_url: page.url(),
      };
    } catch (error) {
      console.log(`[W${this.id}] ERROR`, error.message);

      await this.restart();

      throw error;
    } finally {
      try {
        if (page && !page.isClosed()) {
          await page.close();
        }
      } catch {}

      const jitter = randomInt(JITTER_MIN_MS, JITTER_MAX_MS);

      console.log(`[W${this.id}] jitter sleep ${jitter}ms`);

      await sleep(jitter);

      this.busy = false;
    }
  }

  async close() {
    try {
      await this.context?.close();
    } catch {}

    try {
      await this.browser?.close();
    } catch {}

    this.browser = null;
    this.context = null;
  }
}

const workers = [];

async function initWorkers() {
  for (let i = 0; i < WORKERS_COUNT; i += 1) {
    const startupDelay = i * WORKER_STARTUP_DELAY_MS;

    if (startupDelay > 0) {
      console.log(`[W${i + 1}] startup delay ${startupDelay}ms`);
      await sleep(startupDelay);
    }

    const worker = new Worker(i + 1);

    await worker.init();

    workers.push(worker);
  }
}

async function getFreeWorker() {
  const deadline = Date.now() + 10000;
  while (true) {
    const free = workers.find((worker) => !worker.busy);

    if (free) {
      free.busy = true;
      return free;
    }
    if (Date.now() > deadline) throw new Error('Browser workers busy');

    await sleep(50);
  }
}

app.get("/health", (req, res) => {
  res.status(workers.length === WORKERS_COUNT ? 200 : 503).json({
    ok: workers.length === WORKERS_COUNT,
    workers: workers.length,
    busy: workers.filter((worker) => worker.busy).length,
    config: {
      WORKERS_COUNT,
      MAX_REQUESTS_PER_WORKER,
      FETCH_TIMEOUT_MS,
      PAGE_WAIT_MS,
      JITTER_MIN_MS,
      JITTER_MAX_MS,
      WORKER_STARTUP_DELAY_MS,
    },
  });
});

app.post("/fetch", internalAccess, async (req, res) => {
  const { url, session: version } = req.body || {};

  if (!validTaraUrl(url)) {
    return res.status(400).json({
      error: "No URL provided",
    });
  }

  console.log("\n[REQUEST]", url);

  try {
    sessionPath(version);
    const worker = await getFreeWorker();
    const result = await worker.fetch(url, version);

    return res.json(result);
  } catch (error) {
    return res.status(500).json({
      error: error.message,
    });
  }
});

app.post('/session/check', internalAccess, async (req, res) => {
  let browser;
  try {
    const filename = sessionPath(req.body?.session);
    const urls = req.body?.urls;
    if (!Array.isArray(urls) || !urls.length || urls.length > 3 || !urls.every(validTaraUrl)) {
      return res.status(400).json({ error: 'Invalid validation URLs' });
    }
    browser = await chromium.launch({ headless: false, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
    const context = await browser.newContext({
      storageState: JSON.parse(await fs.readFile(filename, 'utf8')), locale: 'ru-RU',
      viewport: { width: 1920, height: 1080 },
      userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36',
    });
    const page = await context.newPage();
    let missing = 0;
    for (const url of urls) {
      const response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: FETCH_TIMEOUT_MS });
      await page.waitForTimeout(5000);
      const html = new URL(url).pathname.endsWith('.xml') && response
        ? await response.text() : await page.content();
      const status = response?.status();
      if (status === 404) { missing++; continue; }
      if (denied(status, html)) return res.json({ valid: false, reason: 'blocked' });
      if (status === 200 && /topic__heading|props_block__wrapper/.test(html) && validTaraUrl(page.url())) {
        await saveState(filename, await context.storageState());
        return res.json({ valid: true });
      }
      return res.json({ valid: false, reason: 'unavailable' });
    }
    // Real 404s are handled by the parser, never request a new session for them.
    return res.json({ valid: missing === urls.length, reason: 'not_found' });
  } catch (error) {
    console.error('Session check failed:', error.name);
    return res.status(503).json({ valid: false, reason: 'service_unavailable' });
  } finally { await browser?.close().catch(() => {}); }
});

app.post("/shutdown", internalAccess, async (req, res) => {
  console.log("Shutdown requested");

  try {
    for (const worker of workers) {
      await worker.close();
    }
  } catch (error) {
    console.log("shutdown error", error.message);
  }

  res.json({ ok: true });

  process.exit(0);
});

process.on("SIGTERM", async () => {
  console.log("SIGTERM received");

  for (const worker of workers) {
    await worker.close();
  }

  process.exit(0);
});

process.on("SIGINT", async () => {
  console.log("SIGINT received");

  for (const worker of workers) {
    await worker.close();
  }

  process.exit(0);
});

app.listen(3000, async () => {
  console.log(`Browser service running on port 3000, workers=${WORKERS_COUNT}`);

  await initWorkers();
});
