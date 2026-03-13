#!/usr/bin/env node

import fs from 'node:fs/promises';

export async function loadWhitelist(filePath = process.env.WHITELIST_PATH ?? 'whitelist.json') {
  const raw = await fs.readFile(filePath, 'utf8');
  const parsed = JSON.parse(raw);
  const list = Array.isArray(parsed?.whitelist) ? parsed.whitelist : [];

  return {
    generatedAt: parsed?.generatedAt ?? null,
    config: parsed?.config ?? {},
    whitelist: list,
  };
}

export function filterTradable(whitelist, options = {}) {
  const {
    minScore = Number(process.env.MIN_FINAL_SCORE ?? Number.NEGATIVE_INFINITY),
    timeframe = process.env.RECOMMENDED_TIMEFRAME ?? '',
  } = options;

  return whitelist
    .filter((item) => item?.tradable === true)
    .filter((item) => typeof item?.finalScore === 'number' && item.finalScore >= minScore)
    .filter((item) => (timeframe ? item?.recommendedTimeframe === timeframe : true));
}

export async function getTradableWhitelist(options = {}) {
  const { filePath = process.env.WHITELIST_PATH ?? 'whitelist.json' } = options;
  const { generatedAt, config, whitelist } = await loadWhitelist(filePath);
  const tradable = filterTradable(whitelist, options);

  return {
    generatedAt,
    config,
    count: tradable.length,
    whitelist: tradable,
    tokenMints: tradable.map((item) => item.tokenAddress),
  };
}

async function main() {
  const data = await getTradableWhitelist({
    filePath: process.env.WHITELIST_PATH ?? 'whitelist.json',
    minScore: process.env.MIN_FINAL_SCORE ? Number(process.env.MIN_FINAL_SCORE) : undefined,
    timeframe: process.env.RECOMMENDED_TIMEFRAME ?? '',
  });

  // 供其他程序直接读取 stdout，不再依赖 webhook。
  process.stdout.write(`${JSON.stringify(data, null, 2)}\n`);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((error) => {
    console.error('[fatal] whitelist-reader failed:', error.message);
    process.exitCode = 1;
  });
}
