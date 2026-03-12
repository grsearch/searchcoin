#!/usr/bin/env node

import fs from 'node:fs/promises';
import path from 'node:path';

const CONFIG = {
  // CoinGecko Pro Onchain root URL.
  geckoBaseUrl: process.env.GECKO_BASE_URL ?? 'https://pro-api.coingecko.com/api/v3/onchain',
  geckoApiKey: process.env.GECKO_API_KEY ?? '',
  authMode: process.env.GECKO_AUTH_MODE ?? 'header', // header | query
  network: process.env.NETWORK ?? 'solana',
  quoteMint: process.env.QUOTE_MINT ?? 'So11111111111111111111111111111111111111112',
  outputPath: process.env.OUTPUT_PATH ?? 'whitelist.json',
  topN: Number(process.env.TOP_N ?? 20),
  minPoolAgeHours: Number(process.env.MIN_POOL_AGE_HOURS ?? 48),
  maxPoolAgeHours: Number(process.env.MAX_POOL_AGE_HOURS ?? 8760),
  minLiquidityUsd: Number(process.env.MIN_LIQUIDITY_USD ?? 100_000),
  minVolume24hUsd: Number(process.env.MIN_VOLUME_24H_USD ?? 500_000),
  minTxCount24h: Number(process.env.MIN_TX_COUNT_24H ?? 10_000),
  minFdvUsd: Number(process.env.MIN_FDV_USD ?? 1_000_000),
  maxFdvUsd: Number(process.env.MAX_FDV_USD ?? 8_000_000),
  minAtrPct5m14: Number(process.env.MIN_ATR_PCT_5M14 ?? 0.04),
  minAvgRangePct5m24h: Number(process.env.MIN_AVG_RANGE_PCT_5M_24H ?? 0.02),
  minRealizedVol5m: Number(process.env.MIN_REALIZED_VOL_5M ?? 0.015),
  minVolumeLiquidityRatio: Number(process.env.MIN_VOLUME_LIQUIDITY_RATIO ?? 3),
  minDataPoints: Number(process.env.MIN_OHLCV_POINTS ?? 120),
  requestDelayMs: Number(process.env.REQUEST_DELAY_MS ?? 200),
  jupiterQuoteAmount: Number(process.env.JUPITER_QUOTE_AMOUNT ?? 1000000),
  jupiterUrl: process.env.JUPITER_URL ?? 'https://api.jup.ag/swap/v1/quote',
  jupiterApiKey: process.env.JUPITER_API_KEY ?? '',
  jupiterAuthMode: process.env.JUPITER_AUTH_MODE ?? 'header', // header | query
  blacklist: new Set((process.env.BLACKLIST_MINTS ?? '').split(',').map((v) => v.trim()).filter(Boolean)),
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

function percentileRanks(values) {
  const indexed = values.map((value, index) => ({ value, index })).sort((a, b) => a.value - b.value);
  const ranks = new Array(values.length).fill(0.5);
  if (indexed.length <= 1) return ranks;

  for (let i = 0; i < indexed.length; i += 1) {
    ranks[indexed[i].index] = i / (indexed.length - 1);
  }
  return ranks;
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

function computeOHLCVMetrics(candles) {
  const bars = candles
    .map((c) => ({
      open: asNumber(c[1]),
      high: asNumber(c[2]),
      low: asNumber(c[3]),
      close: asNumber(c[4]),
      volume: asNumber(c[5]),
    }))
    .filter((b) => b.close > 0 && b.high >= b.low);

  if (bars.length < 15) return null;

  const trueRanges = [];
  const returns = [];
  const amplitudes = [];
  const wickRatios = [];

  for (let i = 0; i < bars.length; i += 1) {
    const curr = bars[i];
    const prevClose = i > 0 ? bars[i - 1].close : curr.close;
    const tr = Math.max(curr.high - curr.low, Math.abs(curr.high - prevClose), Math.abs(curr.low - prevClose));
    trueRanges.push(tr);

    if (i > 0 && prevClose > 0) returns.push(Math.log(curr.close / prevClose));

    amplitudes.push((curr.high - curr.low) / curr.close);

    const body = Math.abs(curr.close - curr.open);
    const wick = Math.max(0, curr.high - curr.low - body);
    wickRatios.push((curr.high - curr.low) > 0 ? wick / (curr.high - curr.low) : 0);
  }

  const atr14 = trueRanges.slice(-14).reduce((sum, x) => sum + x, 0) / 14;
  const lastClose = bars[bars.length - 1].close;
  const atrPct = lastClose > 0 ? atr14 / lastClose : 0;

  const meanRet = returns.reduce((s, x) => s + x, 0) / Math.max(returns.length, 1);
  const variance = returns.reduce((s, x) => s + (x - meanRet) ** 2, 0) / Math.max(returns.length, 1);
  const realizedVol = Math.sqrt(variance);

  const avgRangePct = amplitudes.reduce((s, x) => s + x, 0) / amplitudes.length;
  const avgWickRatio = wickRatios.reduce((s, x) => s + x, 0) / wickRatios.length;
  const bodyBarsRatio = wickRatios.filter((w) => w < 0.6).length / wickRatios.length;

  return { atrPct, realizedVol, avgRangePct, avgWickRatio, bodyBarsRatio };
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
  const quoteTokenId = safeGet(pool, 'relationships', 'quote_token', 'data', 'id') ?? '';

  return {
    poolId: normalizeTokenId(pool.id),
    baseMint: normalizeTokenId(baseTokenId),
    quoteMint: normalizeTokenId(quoteTokenId),
    symbol: attrs.base_token_symbol ?? 'UNKNOWN',
    name: attrs.name ?? '',
    liquidityUsd,
    volume24hUsd,
    txCount24h,
    fdvUsd,
    ageHours,
  };
}

async function fetchCandidatePools() {
  const urls = [
    `${CONFIG.geckoBaseUrl}/networks/${CONFIG.network}/trending_pools?page=1`,
    `${CONFIG.geckoBaseUrl}/networks/${CONFIG.network}/new_pools?page=1`,
    `${CONFIG.geckoBaseUrl}/networks/${CONFIG.network}/pools/megafilter?page=1`,
    // fallback for docs variant
    `${CONFIG.geckoBaseUrl}/networks/trending_pools?page=1&network=${CONFIG.network}`,
  ];

  const all = [];
  for (const url of urls) {
    try {
      const data = await fetchJson(url);
      const pools = Array.isArray(data?.data) ? data.data : [];
      all.push(...pools.map(buildPoolCandidate));
    } catch (error) {
      console.warn(`[warn] failed fetching ${url}: ${error.message}`);
    }
    await sleep(CONFIG.requestDelayMs);
  }

  const uniq = new Map();
  for (const c of all) {
    if (!c.poolId || !c.baseMint) continue;
    if (!uniq.has(c.poolId)) uniq.set(c.poolId, c);
  }
  return [...uniq.values()];
}

function passHardFilters(pool) {
  if (CONFIG.blacklist.has(pool.baseMint)) return false;
  if (pool.ageHours < CONFIG.minPoolAgeHours || pool.ageHours > CONFIG.maxPoolAgeHours) return false;
  if (pool.liquidityUsd < CONFIG.minLiquidityUsd) return false;
  if (pool.volume24hUsd < CONFIG.minVolume24hUsd) return false;
  if (pool.txCount24h < CONFIG.minTxCount24h) return false;
  if (pool.fdvUsd < CONFIG.minFdvUsd || pool.fdvUsd > CONFIG.maxFdvUsd) return false;
  return true;
}

async function fetchPoolOhlcv(poolId) {
  const url = `${CONFIG.geckoBaseUrl}/networks/${CONFIG.network}/pools/${poolId}/ohlcv/minute?aggregate=5&limit=288`;
  const data = await fetchJson(url);
  const list = safeGet(data, 'data', 'attributes', 'ohlcv_list') ?? [];
  return Array.isArray(list) ? list.reverse() : [];
}

async function checkJupiterRoutable(outputMint) {
  const url = new URL(CONFIG.jupiterUrl);
  url.searchParams.set('inputMint', CONFIG.quoteMint);
  url.searchParams.set('outputMint', outputMint);
  url.searchParams.set('amount', String(CONFIG.jupiterQuoteAmount));
  url.searchParams.set('slippageBps', '100');

  if (CONFIG.jupiterApiKey && CONFIG.jupiterAuthMode === 'query') {
    url.searchParams.set('api-key', CONFIG.jupiterApiKey);
  }

  const headers = {};
  if (CONFIG.jupiterApiKey && CONFIG.jupiterAuthMode === 'header') {
    headers['x-api-key'] = CONFIG.jupiterApiKey;
  }

  const res = await fetch(url.toString(), { headers });
  if (!res.ok) return false;
  const json = await res.json();
  return Boolean(json?.outAmount && Number(json.outAmount) > 0);
}

function recommendTimeframe(atrPct, realizedVol) {
  return atrPct >= 0.05 || realizedVol >= 0.03 ? '1m' : '5m';
}

async function main() {
  if (!CONFIG.geckoApiKey) {
    console.warn('[warn] GECKO_API_KEY is empty. CoinGecko Pro /onchain endpoints may return 401.');
  }

  console.log('[info] fetching candidate pools from CoinGecko Pro /onchain...');
  const candidates = await fetchCandidatePools();
  const hardPassed = candidates.filter(passHardFilters);

  console.log(`[info] candidates=${candidates.length}, hard_passed=${hardPassed.length}`);

  const enriched = [];
  for (const pool of hardPassed) {
    try {
      const candles = await fetchPoolOhlcv(pool.poolId);
      if (candles.length < CONFIG.minDataPoints) continue;
      const metrics = computeOHLCVMetrics(candles);
      if (!metrics) continue;

      if (metrics.atrPct < CONFIG.minAtrPct5m14) continue;
      if (metrics.avgRangePct < CONFIG.minAvgRangePct5m24h) continue;
      if (metrics.realizedVol < CONFIG.minRealizedVol5m) continue;
      if ((pool.volume24hUsd / Math.max(pool.liquidityUsd, 1)) < CONFIG.minVolumeLiquidityRatio) continue;

      enriched.push({ ...pool, ...metrics });
    } catch (error) {
      console.warn(`[warn] pool ${pool.poolId} ohlcv failed: ${error.message}`);
    }
    await sleep(CONFIG.requestDelayMs);
  }

  if (!enriched.length) {
    await fs.writeFile(
      CONFIG.outputPath,
      JSON.stringify({ generatedAt: new Date().toISOString(), config: { network: CONFIG.network }, whitelist: [] }, null, 2),
    );
    console.log('[info] no pools passed filters; outputting empty whitelist');
    return;
  }

  const atrRanks = percentileRanks(enriched.map((x) => x.atrPct));
  const rvRanks = percentileRanks(enriched.map((x) => x.realizedVol));
  const rangeRanks = percentileRanks(enriched.map((x) => x.avgRangePct));
  const volLiqRanks = percentileRanks(enriched.map((x) => x.volume24hUsd / Math.max(x.liquidityUsd, 1)));
  const wickRanks = percentileRanks(enriched.map((x) => x.avgWickRatio));

  const scored = enriched
    .map((item, i) => {
      const baseScore = 0.35 * atrRanks[i] + 0.3 * rvRanks[i] + 0.2 * rangeRanks[i] + 0.15 * volLiqRanks[i];
      const penalty = 0.15 * wickRanks[i] + 0.1 * (1 - item.bodyBarsRatio);
      return { ...item, finalScore: baseScore - penalty };
    })
    .sort((a, b) => b.finalScore - a.finalScore)
    .slice(0, CONFIG.topN);

  const tokenInfoMap = await fetchTokenInfosMulti(scored.map((x) => x.baseMint));

  const whitelist = [];
  for (const token of scored) {
    const routable = await checkJupiterRoutable(token.baseMint);
    if (!routable) continue;

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
      finalScore: Number(token.finalScore.toFixed(6)),
      liquidityUsd: Number(token.liquidityUsd.toFixed(2)),
      volume24hUsd: Number(token.volume24hUsd.toFixed(2)),
      txCount24h: token.txCount24h,
      fdvUsd: Number(token.fdvUsd.toFixed(2)),
      ageHours: Number(token.ageHours.toFixed(2)),
      atrPct5m14: Number((token.atrPct * 100).toFixed(3)),
      avgRangePct5m24h: Number((token.avgRangePct * 100).toFixed(3)),
      realizedVol5m: Number(token.realizedVol.toFixed(6)),
      recommendedTimeframe: recommendTimeframe(token.atrPct, token.realizedVol),
      tradable: true,
    });

    await sleep(CONFIG.requestDelayMs);
  }

  const output = {
    generatedAt: new Date().toISOString(),
    config: {
      dataSource: 'CoinGecko Pro API /api/v3/onchain',
      authMode: CONFIG.authMode,
      jupiterUrl: CONFIG.jupiterUrl,
      jupiterAuthMode: CONFIG.jupiterAuthMode,
      network: CONFIG.network,
      topN: CONFIG.topN,
      minPoolAgeHours: CONFIG.minPoolAgeHours,
      maxPoolAgeHours: CONFIG.maxPoolAgeHours,
      minLiquidityUsd: CONFIG.minLiquidityUsd,
      minVolume24hUsd: CONFIG.minVolume24hUsd,
      minTxCount24h: CONFIG.minTxCount24h,
      minFdvUsd: CONFIG.minFdvUsd,
      maxFdvUsd: CONFIG.maxFdvUsd,
      minAtrPct5m14: CONFIG.minAtrPct5m14,
      minAvgRangePct5m24h: CONFIG.minAvgRangePct5m24h,
      minRealizedVol5m: CONFIG.minRealizedVol5m,
      minVolumeLiquidityRatio: CONFIG.minVolumeLiquidityRatio,
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
