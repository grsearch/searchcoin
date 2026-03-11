#!/usr/bin/env node

import fs from 'node:fs/promises';

const CONFIG = {
  geckoBaseUrl: process.env.GECKO_BASE_URL ?? 'https://pro-api.coingecko.com/api/v3/onchain',
  geckoApiKey: process.env.GECKO_API_KEY ?? '',
  geckoAuthMode: process.env.GECKO_AUTH_MODE ?? 'header', // header | query
  network: process.env.NETWORK ?? 'solana',
  whitelistPath: process.env.WHITELIST_PATH ?? 'whitelist.json',
  // 主策略周期：5m K线
  signalTimeframe: process.env.SIGNAL_TIMEFRAME ?? 'minute',
  signalAggregate: Number(process.env.SIGNAL_AGGREGATE ?? 5),
  signalLimit: Number(process.env.SIGNAL_LIMIT ?? 120),
  // 开单过滤条件：15m EMA9 > EMA20
  trendTimeframe: process.env.TREND_TIMEFRAME ?? 'minute',
  trendAggregate: Number(process.env.TREND_AGGREGATE ?? 15),
  trendLimit: Number(process.env.TREND_LIMIT ?? 120),
  entryEmaFast: Number(process.env.ENTRY_EMA_FAST ?? 9),
  entryEmaSlow: Number(process.env.ENTRY_EMA_SLOW ?? 20),
  rsiPeriod: Number(process.env.RSI_PERIOD ?? 14),
  rsiOversold: Number(process.env.RSI_OVERSOLD ?? 30),
  rsiOverbought: Number(process.env.RSI_OVERBOUGHT ?? 70),
  webhookUrl: process.env.WEBHOOK_URL ?? '',
  webhookAuthHeader: process.env.WEBHOOK_AUTH_HEADER ?? '',
  webhookAuthToken: process.env.WEBHOOK_AUTH_TOKEN ?? '',
  dryRun: (process.env.DRY_RUN ?? 'false').toLowerCase() === 'true',
};

function safeNumber(v, fallback = 0) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function withGeckoAuth(url) {
  const final = new URL(url);
  if (CONFIG.geckoApiKey && CONFIG.geckoAuthMode === 'query') {
    final.searchParams.set('x_cg_pro_api_key', CONFIG.geckoApiKey);
  }
  return final.toString();
}

async function fetchJson(url) {
  const headers = { Accept: 'application/json' };
  if (CONFIG.geckoApiKey && CONFIG.geckoAuthMode === 'header') {
    headers['x-cg-pro-api-key'] = CONFIG.geckoApiKey;
  }

  const res = await fetch(withGeckoAuth(url), { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
  return res.json();
}

async function loadWhitelist() {
  const raw = await fs.readFile(CONFIG.whitelistPath, 'utf8');
  const parsed = JSON.parse(raw);
  return Array.isArray(parsed?.whitelist) ? parsed.whitelist : [];
}

async function fetchPoolOhlcv(poolAddress, timeframe, aggregate, limit) {
  const url = `${CONFIG.geckoBaseUrl}/networks/${CONFIG.network}/pools/${poolAddress}/ohlcv/${timeframe}?aggregate=${aggregate}&limit=${limit}`;
  const data = await fetchJson(url);
  const list = data?.data?.attributes?.ohlcv_list ?? [];
  return Array.isArray(list) ? list.reverse() : [];
}

function calcRsi(closes, period) {
  if (closes.length <= period) return [];
  const rsis = [];
  let gainSum = 0;
  let lossSum = 0;

  for (let i = 1; i <= period; i += 1) {
    const diff = closes[i] - closes[i - 1];
    gainSum += diff > 0 ? diff : 0;
    lossSum += diff < 0 ? -diff : 0;
  }

  let avgGain = gainSum / period;
  let avgLoss = lossSum / period;
  let rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
  rsis.push(100 - 100 / (1 + rs));

  for (let i = period + 1; i < closes.length; i += 1) {
    const diff = closes[i] - closes[i - 1];
    const gain = diff > 0 ? diff : 0;
    const loss = diff < 0 ? -diff : 0;
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
    rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
    rsis.push(100 - 100 / (1 + rs));
  }

  return rsis;
}

function calcEmaSeries(values, period) {
  if (values.length < period) return [];
  const multiplier = 2 / (period + 1);
  const series = [];

  const sma = values.slice(0, period).reduce((sum, x) => sum + x, 0) / period;
  series.push(sma);

  for (let i = period; i < values.length; i += 1) {
    const prev = series[series.length - 1];
    const ema = (values[i] - prev) * multiplier + prev;
    series.push(ema);
  }

  return series;
}

function getEntryTrend(closes) {
  const fast = calcEmaSeries(closes, CONFIG.entryEmaFast);
  const slow = calcEmaSeries(closes, CONFIG.entryEmaSlow);
  if (!fast.length || !slow.length) return null;

  const emaFast = fast[fast.length - 1];
  const emaSlow = slow[slow.length - 1];
  return {
    emaFast,
    emaSlow,
    bullish: emaFast > emaSlow,
  };
}

function buildSignal(token, previousRsi, currentRsi, closePrice, trend) {
  // BUY 开单必须满足 15m EMA9 > EMA20
  if (previousRsi <= CONFIG.rsiOversold && currentRsi > CONFIG.rsiOversold) {
    if (!trend?.bullish) return null;

    return {
      signal: 'BUY',
      reason: 'RSI crossover above oversold with 15m EMA9>EMA20 filter',
      tokenAddress: token.tokenAddress,
      symbol: token.symbol,
      poolAddress: token.primaryPool,
      timeframe: `${CONFIG.signalAggregate}m`,
      trendTimeframe: `${CONFIG.trendAggregate}m`,
      emaFast: Number(trend.emaFast.toFixed(8)),
      emaSlow: Number(trend.emaSlow.toFixed(8)),
      rsi: Number(currentRsi.toFixed(2)),
      price: Number(closePrice.toFixed(8)),
      at: new Date().toISOString(),
    };
  }

  if (previousRsi >= CONFIG.rsiOverbought && currentRsi < CONFIG.rsiOverbought) {
    return {
      signal: 'SELL',
      reason: 'RSI crossover below overbought',
      tokenAddress: token.tokenAddress,
      symbol: token.symbol,
      poolAddress: token.primaryPool,
      timeframe: `${CONFIG.signalAggregate}m`,
      trendTimeframe: `${CONFIG.trendAggregate}m`,
      emaFast: trend ? Number(trend.emaFast.toFixed(8)) : null,
      emaSlow: trend ? Number(trend.emaSlow.toFixed(8)) : null,
      rsi: Number(currentRsi.toFixed(2)),
      price: Number(closePrice.toFixed(8)),
      at: new Date().toISOString(),
    };
  }

  return null;
}

async function sendWebhook(signalPayload) {
  if (!CONFIG.webhookUrl) return { sent: false, status: 'skipped_no_webhook' };
  if (CONFIG.dryRun) return { sent: false, status: 'dry_run' };

  const headers = { 'content-type': 'application/json' };
  if (CONFIG.webhookAuthHeader && CONFIG.webhookAuthToken) {
    headers[CONFIG.webhookAuthHeader] = CONFIG.webhookAuthToken;
  }

  const res = await fetch(CONFIG.webhookUrl, {
    method: 'POST',
    headers,
    body: JSON.stringify(signalPayload),
  });

  if (!res.ok) throw new Error(`webhook HTTP ${res.status}`);
  return { sent: true, status: 'ok' };
}

async function main() {
  const whitelist = await loadWhitelist();
  const tradable = whitelist.filter((x) => x?.tradable === true && x?.primaryPool);

  const signals = [];
  for (const token of tradable) {
    try {
      const signalOhlcv = await fetchPoolOhlcv(token.primaryPool, CONFIG.signalTimeframe, CONFIG.signalAggregate, CONFIG.signalLimit);
      const signalCloses = signalOhlcv.map((x) => safeNumber(x[4])).filter((x) => x > 0);
      const rsis = calcRsi(signalCloses, CONFIG.rsiPeriod);
      if (rsis.length < 2) continue;

      const trendOhlcv = await fetchPoolOhlcv(token.primaryPool, CONFIG.trendTimeframe, CONFIG.trendAggregate, CONFIG.trendLimit);
      const trendCloses = trendOhlcv.map((x) => safeNumber(x[4])).filter((x) => x > 0);
      const trend = getEntryTrend(trendCloses);

      const previousRsi = rsis[rsis.length - 2];
      const currentRsi = rsis[rsis.length - 1];
      const closePrice = signalCloses[signalCloses.length - 1];
      const signal = buildSignal(token, previousRsi, currentRsi, closePrice, trend);
      if (!signal) continue;

      const webhookResult = await sendWebhook(signal);
      signals.push({ ...signal, webhook: webhookResult });
    } catch (error) {
      console.warn(`[warn] token ${token.symbol ?? token.tokenAddress} signal check failed: ${error.message}`);
    }
  }

  const out = {
    generatedAt: new Date().toISOString(),
    mode: 'signal_only_no_trade_execution',
    strategy: {
      signalKline: `${CONFIG.signalAggregate}m`,
      entryFilter: `${CONFIG.trendAggregate}m EMA${CONFIG.entryEmaFast} > EMA${CONFIG.entryEmaSlow}`,
    },
    scanned: tradable.length,
    signals,
  };

  process.stdout.write(`${JSON.stringify(out, null, 2)}\n`);
}

main().catch((error) => {
  console.error('[fatal] signal-engine failed:', error.message);
  process.exitCode = 1;
});
