#!/usr/bin/env node

import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';

const CONFIG = {
  port: Number(process.env.DASHBOARD_PORT ?? 4173),
  host: process.env.DASHBOARD_HOST ?? '0.0.0.0',
  whitelistPath: process.env.WHITELIST_PATH ?? 'whitelist.json',
  signalLogPath: process.env.SIGNAL_LOG_PATH ?? 'signal-events.jsonl',
  signalLogLimit: Number(process.env.SIGNAL_LOG_LIMIT ?? 200),
  geckoBaseUrl: process.env.GECKO_BASE_URL ?? 'https://pro-api.coingecko.com/api/v3/onchain',
  geckoApiKey: process.env.GECKO_API_KEY ?? '',
  geckoAuthMode: process.env.GECKO_AUTH_MODE ?? 'header',
  network: process.env.NETWORK ?? 'solana',
  publicDir: path.resolve(process.cwd(), 'public'),
};


function withGeckoAuth(url) {
  const final = new URL(url);
  if (CONFIG.geckoApiKey && CONFIG.geckoAuthMode === 'query') {
    final.searchParams.set('x_cg_pro_api_key', CONFIG.geckoApiKey);
  }
  return final.toString();
}

async function fetchGeckoJson(url) {
  const headers = { Accept: 'application/json' };
  if (CONFIG.geckoApiKey && CONFIG.geckoAuthMode === 'header') {
    headers['x-cg-pro-api-key'] = CONFIG.geckoApiKey;
  }
  const res = await fetch(withGeckoAuth(url), { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function fetchTokenSymbols(addresses) {
  const uniq = [...new Set(addresses.map((x) => (x || '').trim()).filter(Boolean))];
  if (!uniq.length) return new Map();
  const out = new Map();

  const parseAddress = (item) => {
    const attrs = item?.attributes ?? {};
    const raw = attrs.address ?? attrs.token_address ?? item?.id ?? '';
    if (!raw) return '';
    return raw.includes('_') ? raw.split('_').slice(1).join('_').toLowerCase() : raw.toLowerCase();
  };

  const fetchOne = async (address) => {
    const url = `${CONFIG.geckoBaseUrl}/networks/${CONFIG.network}/tokens/${address}/info`;
    try {
      const json = await fetchGeckoJson(url);
      const symbol = json?.data?.attributes?.symbol ?? '';
      if (symbol) out.set(address.toLowerCase(), symbol);
    } catch {
      // ignore
    }
  };

  try {
    const url = `${CONFIG.geckoBaseUrl}/networks/${CONFIG.network}/tokens/multi/${uniq.join(',')}`;
    const json = await fetchGeckoJson(url);
    for (const item of json?.data ?? []) {
      const attrs = item?.attributes ?? {};
      const addr = parseAddress(item);
      if (addr) out.set(addr, attrs.symbol ?? '');
    }
  } catch {}

  const unresolved = uniq.filter((address) => !out.get(address.toLowerCase()));
  for (const address of unresolved) {
    await fetchOne(address);
  }

  return out;
}

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
};

async function readWhitelist() {
  try {
    const raw = await fs.readFile(CONFIG.whitelistPath, 'utf8');
    const parsed = JSON.parse(raw);
    const whitelist = Array.isArray(parsed?.whitelist) ? parsed.whitelist : [];
    const missing = whitelist.filter((x) => !x?.symbol && x?.tokenAddress).map((x) => x.tokenAddress);
    const symbolMap = await fetchTokenSymbols(missing);
    const enriched = whitelist.map((item) => {
      if (item?.symbol) return item;
      const key = (item?.tokenAddress ?? '').toLowerCase();
      const sym = symbolMap.get(key) || `${(item?.tokenAddress ?? '').slice(0, 6)}...`;
      return { ...item, symbol: sym };
    });

    return {
      generatedAt: parsed?.generatedAt ?? null,
      config: parsed?.config ?? {},
      count: enriched.length,
      tradableCount: enriched.filter((x) => x?.tradable === true).length,
      whitelist: enriched,
    };
  } catch {
    return { generatedAt: null, config: {}, count: 0, tradableCount: 0, whitelist: [] };
  }
}

async function readSignalEvents() {
  try {
    const raw = await fs.readFile(CONFIG.signalLogPath, 'utf8');
    const lines = raw.split('\n').map((x) => x.trim()).filter(Boolean);
    const recent = lines.slice(-CONFIG.signalLogLimit);
    const events = recent
      .map((line) => {
        try {
          return JSON.parse(line);
        } catch {
          return null;
        }
      })
      .filter(Boolean)
      .reverse();

    return {
      count: events.length,
      events,
    };
  } catch {
    return { count: 0, events: [] };
  }
}

async function serveFile(reqPath, res) {
  const safePath = reqPath === '/' ? '/index.html' : reqPath;
  const fullPath = path.resolve(CONFIG.publicDir, `.${safePath}`);
  if (!fullPath.startsWith(CONFIG.publicDir)) {
    res.writeHead(403);
    res.end('Forbidden');
    return;
  }

  try {
    const data = await fs.readFile(fullPath);
    const ext = path.extname(fullPath);
    res.writeHead(200, { 'content-type': MIME[ext] ?? 'application/octet-stream' });
    res.end(data);
  } catch {
    res.writeHead(404);
    res.end('Not Found');
  }
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url ?? '/', `http://${req.headers.host}`);

  if (url.pathname === '/api/health') {
    res.writeHead(200, { 'content-type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ ok: true, now: new Date().toISOString() }));
    return;
  }

  if (url.pathname === '/api/whitelist') {
    const data = await readWhitelist();
    res.writeHead(200, { 'content-type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify(data));
    return;
  }

  if (url.pathname === '/api/signals') {
    const data = await readSignalEvents();
    res.writeHead(200, { 'content-type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify(data));
    return;
  }

  await serveFile(url.pathname, res);
});

server.listen(CONFIG.port, CONFIG.host, () => {
  console.log(`[info] dashboard at http://${CONFIG.host}:${CONFIG.port}`);
});
