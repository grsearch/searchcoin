#!/usr/bin/env node

import fs from 'node:fs/promises';

const DEFAULT_SIGNAL_LOG_PATH = process.env.SIGNAL_LOG_PATH ?? 'signal-events.jsonl';
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

function computePnlFromSignals(signals) {
  const positions = new Map();
  const lastPriceByToken = new Map();
  let realizedPnlSol = 0;
  let buyCount = 0;
  let sellCount = 0;

  for (const s of signals) {
    const token = s.tokenAddress;
    const price = asNumber(s.price);
    if (!token || !Number.isFinite(price) || price <= 0) continue;

    lastPriceByToken.set(token, price);
    const current = positions.get(token) ?? { qty: 0, costSol: 0, symbol: s.symbol ?? 'N/A' };

    if (s.signal === 'BUY') {
      const qty = POSITION_SIZE_SOL / price;
      current.qty += qty;
      current.costSol += POSITION_SIZE_SOL;
      current.symbol = s.symbol ?? current.symbol;
      positions.set(token, current);
      buyCount += 1;
      continue;
    }

    if (s.signal === 'SELL') {
      if (current.qty > 0) {
        const proceeds = current.qty * price;
        realizedPnlSol += proceeds - current.costSol;
        current.qty = 0;
        current.costSol = 0;
        positions.set(token, current);
      }
      sellCount += 1;
    }
  }

  let unrealizedPnlSol = 0;
  const openPositions = [];
  for (const [token, pos] of positions.entries()) {
    if (pos.qty <= 0) continue;
    const mark = lastPriceByToken.get(token);
    if (!Number.isFinite(mark) || mark <= 0) continue;
    const value = pos.qty * mark;
    const pnl = value - pos.costSol;
    unrealizedPnlSol += pnl;
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

  const totalPnlSol = realizedPnlSol + unrealizedPnlSol;

  return {
    signalCount: signals.length,
    buyCount,
    sellCount,
    positionSizeSol: POSITION_SIZE_SOL,
    realizedPnlSol: Number(realizedPnlSol.toFixed(8)),
    unrealizedPnlSol: Number(unrealizedPnlSol.toFixed(8)),
    totalPnlSol: Number(totalPnlSol.toFixed(8)),
    openPositions,
  };
}

export async function getPnlSummary({ signalLogPath = DEFAULT_SIGNAL_LOG_PATH } = {}) {
  const events = await loadSignalEvents(signalLogPath);
  const allSignals = selectTradeSignals(events);
  const since24h = Date.now() - 24 * 60 * 60 * 1000;
  const signals24h = selectTradeSignals(events, since24h);

  return {
    generatedAt: new Date().toISOString(),
    allTime: computePnlFromSignals(allSignals),
    last24h: computePnlFromSignals(signals24h),
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
