#!/usr/bin/env node

import fs from 'node:fs/promises';

const DEFAULT_SIGNAL_LOG_PATH = process.env.SIGNAL_LOG_PATH ?? 'signal-events.jsonl';
const DEFAULT_WHITELIST_PATH = process.env.WHITELIST_PATH ?? 'whitelist.json';
const POSITION_SIZE_SOL = Number(process.env.BACKTEST_POSITION_SIZE_SOL ?? 1);

function asNumber(v, fallback = NaN) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function safeTs(event) {
  const raw = event?.loggedAt ?? event?.at;
  const ts = raw ? Date.parse(raw) : NaN;
  return Number.isFinite(ts) ? ts : null;
}

async function loadSignalEvents(path = DEFAULT_SIGNAL_LOG_PATH) {
  try {
    const raw = await fs.readFile(path, 'utf8');
    return raw
      .split('\n')
      .map((x) => x.trim())
      .filter(Boolean)
      .map((line) => {
        try {
          return JSON.parse(line);
        } catch {
          return null;
        }
      })
      .filter(Boolean);
  } catch {
    return [];
  }
}

function selectTradeSignals(events, sinceTs = null) {
  return events
    .filter((e) => e?.signal === 'BUY' || e?.signal === 'SELL')
    .filter((e) => {
      if (sinceTs == null) return true;
      const ts = safeTs(e);
      return ts != null && ts >= sinceTs;
    })
    .filter((e) => Number.isFinite(asNumber(e?.price)))
    .sort((a, b) => (safeTs(a) ?? 0) - (safeTs(b) ?? 0));
}

function ensureTokenStat(map, token, symbol = 'N/A') {
  if (!map.has(token)) {
    map.set(token, {
      tokenAddress: token,
      symbol,
      buyCount: 0,
      sellCount: 0,
      realizedPnlSol: 0,
      unrealizedPnlSol: 0,
      totalPnlSol: 0,
      openQty: 0,
      openCostSol: 0,
      markPrice: null,
    });
  }
  return map.get(token);
}


async function loadWhitelistTokens(path = DEFAULT_WHITELIST_PATH) {
  try {
    const raw = await fs.readFile(path, 'utf8');
    const parsed = JSON.parse(raw);
    const list = Array.isArray(parsed?.whitelist) ? parsed.whitelist : [];
    return list
      .map((x) => ({
        tokenAddress: x?.tokenAddress ?? '',
        symbol: x?.symbol ?? 'N/A',
      }))
      .filter((x) => x.tokenAddress);
  } catch {
    return [];
  }
}

function mergeWhitelistTokens(perToken, whitelistTokens) {
  const existing = new Map(perToken.map((x) => [(x.tokenAddress ?? '').toLowerCase(), x]));
  for (const token of whitelistTokens) {
    const key = (token.tokenAddress ?? '').toLowerCase();
    if (!key || existing.has(key)) continue;
    existing.set(key, {
      tokenAddress: token.tokenAddress,
      symbol: token.symbol || 'N/A',
      buyCount: 0,
      sellCount: 0,
      realizedPnlSol: 0,
      unrealizedPnlSol: 0,
      totalPnlSol: 0,
      openQty: 0,
      openCostSol: 0,
      markPrice: null,
    });
  }
  return [...existing.values()].sort((a, b) => b.totalPnlSol - a.totalPnlSol);
}

function computePnlFromSignals(signals) {
  const positions = new Map();
  const lastPriceByToken = new Map();
  const tokenStats = new Map();

  let realizedPnlSol = 0;
  let buyCount = 0;
  let sellCount = 0;

  for (const s of signals) {
    const token = s.tokenAddress;
    const price = asNumber(s.price);
    if (!token || !Number.isFinite(price) || price <= 0) continue;

    lastPriceByToken.set(token, price);
    const current = positions.get(token) ?? { qty: 0, costSol: 0, symbol: s.symbol ?? 'N/A' };
    const stat = ensureTokenStat(tokenStats, token, s.symbol ?? current.symbol);

    if (s.signal === 'BUY') {
      const qty = POSITION_SIZE_SOL / price;
      current.qty += qty;
      current.costSol += POSITION_SIZE_SOL;
      current.symbol = s.symbol ?? current.symbol;
      positions.set(token, current);

      stat.buyCount += 1;
      buyCount += 1;
      continue;
    }

    if (s.signal === 'SELL') {
      if (current.qty > 0) {
        const proceeds = current.qty * price;
        const pnl = proceeds - current.costSol;
        realizedPnlSol += pnl;
        stat.realizedPnlSol += pnl;
        current.qty = 0;
        current.costSol = 0;
        positions.set(token, current);
      }
      stat.sellCount += 1;
      sellCount += 1;
    }
  }

  let unrealizedPnlSol = 0;
  const openPositions = [];

  for (const [token, pos] of positions.entries()) {
    const stat = ensureTokenStat(tokenStats, token, pos.symbol);
    if (pos.qty <= 0) continue;

    const mark = lastPriceByToken.get(token);
    if (!Number.isFinite(mark) || mark <= 0) continue;

    const value = pos.qty * mark;
    const pnl = value - pos.costSol;

    unrealizedPnlSol += pnl;
    stat.unrealizedPnlSol += pnl;
    stat.openQty = pos.qty;
    stat.openCostSol = pos.costSol;
    stat.markPrice = mark;

    openPositions.push({
      tokenAddress: token,
      symbol: pos.symbol,
      qty: Number(pos.qty.toFixed(8)),
      costSol: Number(pos.costSol.toFixed(8)),
      markPrice: Number(mark.toFixed(8)),
      valueSol: Number(value.toFixed(8)),
      pnlSol: Number(pnl.toFixed(8)),
    });
  }

  const perToken = [...tokenStats.values()]
    .map((x) => {
      const total = x.realizedPnlSol + x.unrealizedPnlSol;
      return {
        tokenAddress: x.tokenAddress,
        symbol: x.symbol,
        buyCount: x.buyCount,
        sellCount: x.sellCount,
        realizedPnlSol: Number(x.realizedPnlSol.toFixed(8)),
        unrealizedPnlSol: Number(x.unrealizedPnlSol.toFixed(8)),
        totalPnlSol: Number(total.toFixed(8)),
        openQty: Number(x.openQty.toFixed(8)),
        openCostSol: Number(x.openCostSol.toFixed(8)),
        markPrice: x.markPrice == null ? null : Number(x.markPrice.toFixed(8)),
      };
    })
    .sort((a, b) => b.totalPnlSol - a.totalPnlSol);

  const totalPnlSol = realizedPnlSol + unrealizedPnlSol;

  return {
    signalCount: signals.length,
    buyCount,
    sellCount,
    positionSizeSol: POSITION_SIZE_SOL,
    realizedPnlSol: Number(realizedPnlSol.toFixed(8)),
    unrealizedPnlSol: Number(unrealizedPnlSol.toFixed(8)),
    totalPnlSol: Number(totalPnlSol.toFixed(8)),
    perToken,
    openPositions,
  };
}

export async function getPnlSummary({ signalLogPath = DEFAULT_SIGNAL_LOG_PATH, whitelistPath = DEFAULT_WHITELIST_PATH } = {}) {
  const [events, whitelistTokens] = await Promise.all([
    loadSignalEvents(signalLogPath),
    loadWhitelistTokens(whitelistPath),
  ]);
  const allSignals = selectTradeSignals(events);
  const since24h = Date.now() - 24 * 60 * 60 * 1000;
  const signals24h = selectTradeSignals(events, since24h);

  const allTime = computePnlFromSignals(allSignals);
  const last24h = computePnlFromSignals(signals24h);
  allTime.perToken = mergeWhitelistTokens(allTime.perToken, whitelistTokens);
  last24h.perToken = mergeWhitelistTokens(last24h.perToken, whitelistTokens);

  return {
    generatedAt: new Date().toISOString(),
    window: {
      last24hSince: new Date(since24h).toISOString(),
      now: new Date().toISOString(),
    },
    allTime,
    last24h,
    backtest24hSummary: {
      signalCount: last24h.signalCount,
      buyCount: last24h.buyCount,
      sellCount: last24h.sellCount,
      realizedPnlSol: last24h.realizedPnlSol,
      unrealizedPnlSol: last24h.unrealizedPnlSol,
      totalPnlSol: last24h.totalPnlSol,
    },
  };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  getPnlSummary().then((out) => {
    process.stdout.write(`${JSON.stringify(out, null, 2)}\n`);
  }).catch((error) => {
    console.error('[fatal] backtest-pnl failed:', error.message);
    process.exitCode = 1;
  });
}
