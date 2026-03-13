#!/usr/bin/env node

import fs from 'node:fs/promises';
import path from 'node:path';

const CONFIG = {
  geckoBaseUrl: process.env.GECKO_BASE_URL ?? 'https://pro-api.coingecko.com/api/v3/onchain',
  geckoApiKey: process.env.GECKO_API_KEY ?? '',
  authMode: process.env.GECKO_AUTH_MODE ?? 'header',
  network: process.env.NETWORK ?? 'solana',
  outputPath: process.env.OUTPUT_PATH ?? 'whitelist.json',
  topN: Number(process.env.TOP_N ?? 40),
  minPoolAgeHours: Number(process.env.MIN_POOL_AGE_HOURS ?? 48),
  minLiquidityUsd: Number(process.env.MIN_LIQUIDITY_USD ?? 50_000),
  minVolume24hUsd: Number(process.env.MIN_VOLUME_24H_USD ?? 300_000),
  minFdvUsd: Math.max(Number(process.env.MIN_FDV_USD ?? 500_000), 500_000),
  maxFdvUsd: Math.min(Number(process.env.MAX_FDV_USD ?? 5_000_000), 5_000_000),
  requestDelayMs: Number(process.env.REQUEST_DELAY_MS ?? 200),
  candidatePages: Number(process.env.CANDIDATE_PAGES ?? 5),
  filterDebug: (process.env.FILTER_DEBUG ?? 'true').toLowerCase() === 'true',
};

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function asNumber(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function parsePoolAgeHours(createdAt) {
  const ts = createdAt ? new Date(createdAt).getTime() : NaN;
  if (!Number.isFinite(ts)) return Infinity;
  return (Date.now() - ts) / 3_600_000;
}

function safeGet(obj, ...keys) {
  return keys.reduce((acc, key) => (acc?.[key] == null ? undefined : acc[key]), obj);
}

function increaseCounter(map, key) {
  map[key] = (map[key] ?? 0) + 1;
}

function withAuth(url) {
  const finalUrl = new URL(url);
  if (CONFIG.geckoApiKey && CONFIG.authMode === 'query') {
    finalUrl.searchParams.set('x_cg_pro_api_key', CONFIG.geckoApiKey);
  }
  return finalUrl.toString();
}

function normalizeTokenId(tokenId) {
  if (!tokenId) return '';
  if (tokenId.includes('_')) return tokenId.split('_').slice(1).join('_');
  return tokenId;
}

function parseAddressFromTokenItem(item) {
  const attrs = item?.attributes ?? {};
  const raw = attrs.address ?? attrs.token_address ?? item?.id ?? '';
  return normalizeTokenId(raw).toLowerCase();
}

async function fetchTokenInfosMulti(addresses) {
  const uniq = [...new Set(addresses.map((x) => (x || '').trim()).filter(Boolean))];
  if (!uniq.length) return new Map();

  const url = `${CONFIG.geckoBaseUrl}/networks/${CONFIG.network}/tokens/multi/${uniq.join(',')}`;
  try {
    const data = await fetchJson(url);
    const items = Array.isArray(data?.data) ? data.data : [];
    const out = new Map();
    for (const item of items) {
      const attrs = item?.attributes ?? {};
      const address = parseAddressFromTokenItem(item);
      if (!address) continue;
      out.set(address, {
        symbol: attrs.symbol ?? '',
        name: attrs.name ?? '',
      });
    }
    return out;
  } catch (error) {
    console.warn(`[warn] token info multi failed: ${error.message}`);
    return new Map();
  }
}

async function fetchTokenInfo(address) {
  if (!address) return null;
  const url = `${CONFIG.geckoBaseUrl}/networks/${CONFIG.network}/tokens/${address}/info`;
  try {
    const data = await fetchJson(url);
    const attrs = data?.data?.attributes ?? {};
    return {
      symbol: attrs.symbol ?? '',
      name: attrs.name ?? '',
    };
  } catch {
    return null;
  }
}

async function fetchJson(url) {
  const headers = { Accept: 'application/json' };
  if (CONFIG.geckoApiKey && CONFIG.authMode === 'header') headers['x-cg-pro-api-key'] = CONFIG.geckoApiKey;

  const authedUrl = withAuth(url);
  const res = await fetch(authedUrl, { headers });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`HTTP ${res.status} for ${authedUrl}${body ? ` | ${body.slice(0, 300)}` : ''}`);
  }
  return res.json();
}

function buildPoolCandidate(pool) {
  const attrs = pool.attributes ?? {};
  const liquidityUsd = asNumber(attrs.reserve_in_usd);
  const volume24hUsd = asNumber(safeGet(attrs, 'volume_usd', 'h24'));
  const buys24h = asNumber(safeGet(attrs, 'transactions', 'h24', 'buys'));
  const sells24h = asNumber(safeGet(attrs, 'transactions', 'h24', 'sells'));
  const txCount24h = buys24h + sells24h;
  const fdvUsd = asNumber(attrs.fdv_usd ?? attrs.market_cap_usd);
  const ageHours = parsePoolAgeHours(attrs.pool_created_at);

  const baseTokenId = safeGet(pool, 'relationships', 'base_token', 'data', 'id') ?? '';

  return {
    poolId: normalizeTokenId(pool.id),
    baseMint: normalizeTokenId(baseTokenId),
    symbol: attrs.base_token_symbol ?? 'UNKNOWN',
    liquidityUsd,
    volume24hUsd,
    txCount24h,
    fdvUsd,
    ageHours,
  };
}

async function fetchCandidatePools() {
  const endpoints = [
    { name: 'trending_pools', build: (page) => `${CONFIG.geckoBaseUrl}/networks/${CONFIG.network}/trending_pools?page=${page}` },
    { name: 'megafilter', build: (page) => `${CONFIG.geckoBaseUrl}/networks/${CONFIG.network}/pools/megafilter?page=${page}` },
    { name: 'top_pools', build: (page) => `${CONFIG.geckoBaseUrl}/networks/${CONFIG.network}/pools?page=${page}` },
    { name: 'trending_fallback', build: (page) => `${CONFIG.geckoBaseUrl}/networks/trending_pools?page=${page}&network=${CONFIG.network}` },
  ];

  const all = [];
  const sourceCounts = {};
  for (const endpoint of endpoints) {
    for (let page = 1; page <= CONFIG.candidatePages; page += 1) {
      const url = endpoint.build(page);
      try {
        const data = await fetchJson(url);
        const pools = Array.isArray(data?.data) ? data.data : [];
        const mapped = pools.map(buildPoolCandidate);
        all.push(...mapped);
        sourceCounts[endpoint.name] = (sourceCounts[endpoint.name] ?? 0) + mapped.length;
      } catch (error) {
        console.warn(`[warn] failed fetching ${url}: ${error.message}`);
      }
      await sleep(CONFIG.requestDelayMs);
    }
  }

  const uniq = new Map();
  for (const c of all) {
    if (!c.poolId || !c.baseMint) continue;
    if (!uniq.has(c.poolId)) uniq.set(c.poolId, c);
  }
  return {
    candidates: [...uniq.values()],
    sourceCounts,
    rawCount: all.length,
  };
}

function getHardFilterFailReason(pool) {
  if (pool.ageHours < CONFIG.minPoolAgeHours) return 'age';
  if (pool.liquidityUsd < CONFIG.minLiquidityUsd) return 'liquidity';
  if (pool.volume24hUsd < CONFIG.minVolume24hUsd) return 'volume24h';
  if (pool.fdvUsd < CONFIG.minFdvUsd || pool.fdvUsd > CONFIG.maxFdvUsd) return 'fdv';
  return null;
}

async function main() {
  if (!CONFIG.geckoApiKey) {
    console.warn('[warn] GECKO_API_KEY is empty. CoinGecko Pro /onchain endpoints may return 401.');
  }

  console.log('[info] fetching candidate pools from CoinGecko Pro /onchain...');
  const { candidates, sourceCounts, rawCount } = await fetchCandidatePools();

  const rejectCounts = {};
  const hardPassed = [];
  for (const pool of candidates) {
    const reason = getHardFilterFailReason(pool);
    if (reason) {
      increaseCounter(rejectCounts, reason);
      continue;
    }
    hardPassed.push(pool);
  }

  console.log(`[info] raw_candidates=${rawCount}, dedup_candidates=${candidates.length}, hard_passed=${hardPassed.length}`);
  if (CONFIG.filterDebug) {
    console.log(`[debug] source_counts=${JSON.stringify(sourceCounts)}`);
    console.log(`[debug] reject_counts=${JSON.stringify(rejectCounts)}`);
  }

  const ranked = hardPassed
    .sort((a, b) => {
      if (b.volume24hUsd !== a.volume24hUsd) return b.volume24hUsd - a.volume24hUsd;
      return b.liquidityUsd - a.liquidityUsd;
    })
    .slice(0, CONFIG.topN)
    .map((item, index) => ({ ...item, finalScore: CONFIG.topN - index }));

  const tokenInfoMap = await fetchTokenInfosMulti(ranked.map((x) => x.baseMint));

  const whitelist = [];
  for (const token of ranked) {
    const key = (token.baseMint ?? '').toLowerCase();
    let resolvedSymbol = tokenInfoMap.get(key)?.symbol ?? token.symbol ?? '';
    if (!resolvedSymbol) {
      const info = await fetchTokenInfo(token.baseMint);
      resolvedSymbol = info?.symbol ?? '';
    }
    if (!resolvedSymbol) resolvedSymbol = `${(token.baseMint ?? '').slice(0, 6)}...`;

    whitelist.push({
      tokenAddress: token.baseMint,
      symbol: resolvedSymbol,
      primaryPool: token.poolId,
      finalScore: token.finalScore,
      liquidityUsd: Number(token.liquidityUsd.toFixed(2)),
      volume24hUsd: Number(token.volume24hUsd.toFixed(2)),
      txCount24h: token.txCount24h,
      fdvUsd: Number(token.fdvUsd.toFixed(2)),
      ageHours: Number(token.ageHours.toFixed(2)),
      tradable: true,
    });

    await sleep(CONFIG.requestDelayMs);
  }

  const output = {
    generatedAt: new Date().toISOString(),
    config: {
      dataSource: 'CoinGecko Pro API /api/v3/onchain',
      authMode: CONFIG.authMode,
      network: CONFIG.network,
      topN: CONFIG.topN,
      minPoolAgeHours: CONFIG.minPoolAgeHours,
      minLiquidityUsd: CONFIG.minLiquidityUsd,
      minVolume24hUsd: CONFIG.minVolume24hUsd,
      minFdvUsd: CONFIG.minFdvUsd,
      maxFdvUsd: CONFIG.maxFdvUsd,
      fdvPolicy: 'hard_enforced_500k_to_5m',
      rankMode: 'volume_desc_then_liquidity_desc',
      candidatePages: CONFIG.candidatePages,
    },
    debug: {
      rawCandidates: rawCount,
      dedupCandidates: candidates.length,
      hardPassed: hardPassed.length,
      sourceCounts,
      rejectCounts,
    },
    whitelist,
  };

  const dir = path.dirname(CONFIG.outputPath);
  if (dir && dir !== '.') await fs.mkdir(dir, { recursive: true });
  await fs.writeFile(CONFIG.outputPath, JSON.stringify(output, null, 2));

  console.log(`[info] whitelist entries=${whitelist.length}, saved=${CONFIG.outputPath}`);
}

main().catch((error) => {
  console.error('[fatal]', error);
  process.exitCode = 1;
});
