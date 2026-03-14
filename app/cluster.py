import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import settings


@dataclass
class RelayResult:
    ok: bool
    target: str
    detail: str


def _data_dir() -> Path:
    return Path("data")


def strategy_wallets_file() -> Path:
    return _data_dir() / "strategy_wallets.json"


def trader_signals_file() -> Path:
    return _data_dir() / "trader_signals.json"


def load_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def save_json_file(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_strategy_wallets() -> list[dict[str, Any]]:
    payload = load_json_file(strategy_wallets_file(), {"wallets": []})
    wallets = payload.get("wallets", []) if isinstance(payload, dict) else []
    return wallets if isinstance(wallets, list) else []


def save_strategy_wallets(wallets: list[dict[str, Any]], source: str = "scanner") -> None:
    save_json_file(
        strategy_wallets_file(),
        {
            "source": source,
            "updated_at": int(time.time()),
            "wallets": wallets,
        },
    )


def append_trader_signal(signal: dict[str, Any]) -> None:
    payload = load_json_file(trader_signals_file(), {"signals": []})
    signals = payload.get("signals", []) if isinstance(payload, dict) else []
    if not isinstance(signals, list):
        signals = []
    signals.append(signal)
    payload = {
        "updated_at": int(time.time()),
        "signals": signals[-500:],
    }
    save_json_file(trader_signals_file(), payload)


def load_trader_signals() -> list[dict[str, Any]]:
    payload = load_json_file(trader_signals_file(), {"signals": []})
    signals = payload.get("signals", []) if isinstance(payload, dict) else []
    return signals if isinstance(signals, list) else []


def normalize_server_role(raw: str) -> str:
    role = (raw or "all").strip().lower()
    allowed = {"all", "scanner", "strategy", "trader"}
    return role if role in allowed else "all"


def role_enabled(role: str, target: str) -> bool:
    if role == "all":
        return True
    return role == target


def auth_ok(token: str | None) -> bool:
    shared = settings.inter_server_shared_token.strip()
    if not shared:
        return True
    return token == shared
