#!/usr/bin/env node

import fs from 'node:fs/promises';
import { spawn } from 'node:child_process';

const CONFIG = {
  whitelistPath: process.env.WHITELIST_PATH ?? 'whitelist.json',
  webhookUrl: process.env.WEBHOOK_URL ?? '',
  webhookAuthHeader: process.env.WEBHOOK_AUTH_HEADER ?? '',
  webhookAuthToken: process.env.WEBHOOK_AUTH_TOKEN ?? '',
  dryRun: (process.env.DRY_RUN ?? 'false').toLowerCase() === 'true',
  signalLogPath: process.env.SIGNAL_LOG_PATH ?? 'signal-events.jsonl',
};

async function readWhitelist(path) {
  try {
    const raw = await fs.readFile(path, 'utf8');
    const parsed = JSON.parse(raw);
    const list = Array.isArray(parsed?.whitelist) ? parsed.whitelist : [];
    return list.filter((x) => x?.tokenAddress);
  } catch {
    return [];
  }
}

function runBuildWhitelist() {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, ['src/whitelist-builder.js'], {
      stdio: 'inherit',
      env: process.env,
    });

    child.on('error', reject);
    child.on('exit', (code) => {
      if (code === 0) resolve();
      else reject(new Error(`whitelist-builder exited with code ${code}`));
    });
  });
}


async function appendSignalEvent(event) {
  const line = `${JSON.stringify(event)}\n`;
  await fs.appendFile(CONFIG.signalLogPath, line, 'utf8');
}

async function sendWebhook(payload) {
  if (!CONFIG.webhookUrl) return { sent: false, status: 'skipped_no_webhook' };
  if (CONFIG.dryRun) return { sent: false, status: 'dry_run' };

  const headers = { 'content-type': 'application/json' };
  if (CONFIG.webhookAuthHeader && CONFIG.webhookAuthToken) {
    headers[CONFIG.webhookAuthHeader] = CONFIG.webhookAuthToken;
  }

  const res = await fetch(CONFIG.webhookUrl, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error(`webhook HTTP ${res.status}`);
  }

  return { sent: true, status: 'ok' };
}

function mapByToken(list) {
  const m = new Map();
  for (const item of list) m.set(item.tokenAddress, item);
  return m;
}

async function main() {
  const prevWhitelist = await readWhitelist(CONFIG.whitelistPath);
  const prevMap = mapByToken(prevWhitelist);

  // 每6小时运行一次此脚本：先更新白名单。
  await runBuildWhitelist();

  const nextWhitelist = await readWhitelist(CONFIG.whitelistPath);
  const nextMap = mapByToken(nextWhitelist);

  // 一旦有币退出白名单，优先发出卖出/退出信号。
  const exited = prevWhitelist.filter((item) => !nextMap.has(item.tokenAddress));

  const exitSignals = [];
  for (const token of exited) {
    const payload = {
      signal: 'SELL',
      subtype: 'EXIT_WHITELIST',
      reason: 'Token removed from whitelist on 6h refresh',
      tokenAddress: token.tokenAddress,
      symbol: token.symbol ?? 'UNKNOWN',
      poolAddress: token.primaryPool ?? null,
      finalScore: token.finalScore ?? null,
      at: new Date().toISOString(),
    };

    const webhook = await sendWebhook(payload);
    const enriched = { ...payload, webhook };
    exitSignals.push(enriched);
    await appendSignalEvent({
      eventType: 'EXIT_WHITELIST',
      ...enriched,
      loggedAt: new Date().toISOString(),
    });
  }

  const summary = {
    generatedAt: new Date().toISOString(),
    mode: 'whitelist_6h_cycle',
    previousCount: prevWhitelist.length,
    currentCount: nextWhitelist.length,
    enteredCount: nextWhitelist.filter((item) => !prevMap.has(item.tokenAddress)).length,
    exitedCount: exited.length,
    exitSignals,
  };

  process.stdout.write(`${JSON.stringify(summary, null, 2)}\n`);
}

main().catch((error) => {
  console.error('[fatal] whitelist-cycle failed:', error.message);
  process.exitCode = 1;
});
