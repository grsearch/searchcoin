import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import settings
from app.dashboard import wallet_gmgn_url


@dataclass
class SmartWalletCandidate:
    address: str
    pnl_30d: float
    pnl_7d: float
    profitable_trades: int
    total_trades: int
    tx_last_7d: int
    tx_last_3d: int
    net_worth_usd: float
    avg_return_after_5m: float
    recent_10_loss_ratio: float = 0.0
    stats_source: str = "unknown"


@dataclass
class SmartWalletScore:
    address: str
    pnl_score: float
    winrate_score: float
    activity_score: float
    wallet_size_score: float
    timing_score: float
    score: float
    wallet_weight: int
    is_blacklisted: bool
    is_whitelisted: bool
    selected_by_min_count: bool
    stats_source: str
    gmgn_url: str


def pnl_score(pnl_30d: float) -> float:
    if pnl_30d > 100000:
        return 100
    if pnl_30d > 50000:
        return 90
    if pnl_30d > 20000:
        return 80
    if pnl_30d > 10000:
        return 70
    if pnl_30d > 5000:
        return 60
    return 40


def winrate_score(winrate: float) -> float:
    if winrate > 0.7:
        return 100
    if winrate > 0.6:
        return 85
    if winrate > 0.5:
        return 70
    if winrate > 0.4:
        return 50
    return 30


def activity_score(tx_7d: int) -> float:
    if tx_7d > 100:
        return 100
    if tx_7d > 50:
        return 85
    if tx_7d > 20:
        return 70
    if tx_7d > 10:
        return 50
    return 20


def wallet_size_score(net_worth_usd: float) -> float:
    if net_worth_usd > 500000:
        return 100
    if net_worth_usd > 200000:
        return 85
    if net_worth_usd > 100000:
        return 70
    if net_worth_usd > 50000:
        return 60
    return 40


def timing_score(avg_return_after_5m: float) -> float:
    if avg_return_after_5m > 0.20:
        return 100
    if avg_return_after_5m > 0.10:
        return 80
    if avg_return_after_5m > 0.05:
        return 60
    if avg_return_after_5m > 0.0:
        return 40
    return 20


def score_to_weight(score: float) -> int:
    if score > 90:
        return 3
    if score > 85:
        return 2
    if score >= 80:
        return 1
    return 0


def should_blacklist(recent_10_loss_ratio: float) -> bool:
    return recent_10_loss_ratio > 0.5


DEFAULT_SMART_WALLETS_DATA = {"wallets": []}


def _load_raw_candidates() -> dict[str, Any]:
    data_file = Path(settings.smart_wallets_data_file)
    if data_file.exists():
        try:
            with data_file.open("r", encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload, dict):
                return payload
        except (OSError, json.JSONDecodeError):
            pass
    return DEFAULT_SMART_WALLETS_DATA


def load_smart_wallet_candidates() -> list[SmartWalletCandidate]:
    raw = _load_raw_candidates()
    wallets: list[SmartWalletCandidate] = []
    for item in raw.get("wallets", []):
        address = str(item.get("address", "")).strip()
        if not address:
            continue
        wallets.append(
            SmartWalletCandidate(
                address=address,
                pnl_30d=float(item.get("pnl_30d", 0.0)),
                pnl_7d=float(item.get("pnl_7d", 0.0)),
                profitable_trades=int(item.get("profitable_trades", 0)),
                total_trades=int(item.get("total_trades", 0)),
                tx_last_7d=int(item.get("tx_last_7d", 0)),
                tx_last_3d=int(item.get("tx_last_3d", 0)),
                net_worth_usd=float(item.get("net_worth_usd", 0.0)),
                avg_return_after_5m=float(item.get("avg_return_after_5m", 0.0)),
                recent_10_loss_ratio=float(item.get("recent_10_loss_ratio", 0.0)),
                stats_source=str(item.get("stats_source", "unknown")),
            )
        )
    return wallets


def score_wallet(candidate: SmartWalletCandidate) -> SmartWalletScore:
    winrate = 0.0
    if candidate.total_trades > 0:
        winrate = candidate.profitable_trades / candidate.total_trades

    p_score = pnl_score(candidate.pnl_30d)
    w_score = winrate_score(winrate)
    a_score = activity_score(candidate.tx_last_7d)
    s_score = wallet_size_score(candidate.net_worth_usd)
    t_score = timing_score(candidate.avg_return_after_5m)

    final_score = (
        0.30 * p_score
        + 0.20 * w_score
        + 0.20 * a_score
        + 0.15 * s_score
        + 0.15 * t_score
    )

    blacklisted = should_blacklist(candidate.recent_10_loss_ratio)
    threshold = settings.smart_wallet_whitelist_score
    whitelisted = final_score >= threshold and not blacklisted

    return SmartWalletScore(
        address=candidate.address,
        pnl_score=p_score,
        winrate_score=w_score,
        activity_score=a_score,
        wallet_size_score=s_score,
        timing_score=t_score,
        score=round(final_score, 2),
        wallet_weight=score_to_weight(final_score) if whitelisted else 0,
        is_blacklisted=blacklisted,
        is_whitelisted=whitelisted,
        selected_by_min_count=False,
        stats_source=candidate.stats_source,
        gmgn_url=wallet_gmgn_url(candidate.address),
    )


def smart_wallet_report() -> dict[str, Any]:
    scored = [score_wallet(w) for w in load_smart_wallet_candidates()]
    scored.sort(key=lambda x: x.score, reverse=True)

    whitelist = [w for w in scored if w.is_whitelisted]
    min_count = max(0, settings.smart_wallet_min_whitelist_count)
    min_proxy_score = settings.smart_wallet_min_proxy_score

    if len(whitelist) < min_count:
        for wallet in scored:
            if wallet.is_blacklisted or wallet.is_whitelisted:
                continue
            if wallet.score < min_proxy_score:
                continue
            wallet.is_whitelisted = True
            wallet.selected_by_min_count = True
            wallet.wallet_weight = max(1, score_to_weight(wallet.score))
            whitelist.append(wallet)
            if len(whitelist) >= min_count:
                break

    blacklist = [w for w in scored if w.is_blacklisted]
    fallback_selected = sum(1 for w in whitelist if w.selected_by_min_count)

    return {
        "scored_wallets": [w.__dict__ for w in scored],
        "smart_wallets": [w.__dict__ for w in whitelist],
        "blacklisted_wallets": [w.__dict__ for w in blacklist],
        "count_scored": len(scored),
        "count_whitelisted": len(whitelist),
        "count_blacklisted": len(blacklist),
        "scoring": {
            "whitelist_score_threshold": settings.smart_wallet_whitelist_score,
            "min_whitelist_count": settings.smart_wallet_min_whitelist_count,
            "min_proxy_score": settings.smart_wallet_min_proxy_score,
            "fallback_selected": fallback_selected,
        },
    }
