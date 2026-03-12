#!/usr/bin/env node

import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';

const CONFIG = {
  port: Number(process.env.DASHBOARD_PORT ?? 4173),
  host: process.env.DASHBOARD_HOST ?? '0.0.0.0',
  whitelistPath: process.env.WHITELIST_PATH ?? 'whitelist.json',
  publicDir: path.resolve(process.cwd(), 'public'),
};

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
    return {
      generatedAt: parsed?.generatedAt ?? null,
      config: parsed?.config ?? {},
      count: whitelist.length,
      tradableCount: whitelist.filter((x) => x?.tradable === true).length,
      whitelist,
    };
  } catch {
    return { generatedAt: null, config: {}, count: 0, tradableCount: 0, whitelist: [] };
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

  await serveFile(url.pathname, res);
});

server.listen(CONFIG.port, CONFIG.host, () => {
  console.log(`[info] dashboard at http://${CONFIG.host}:${CONFIG.port}`);
});
