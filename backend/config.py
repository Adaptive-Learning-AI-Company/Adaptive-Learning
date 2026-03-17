import json
import os
from functools import lru_cache
from pathlib import Path

DEFAULT_AVATAR_ID = "schoolgirl"
SUPPORTED_AVATARS = {"schoolgirl", "schoolboy"}
DEFAULT_ACCOUNT_STATUS = "active"
SUPPORTED_ACCOUNT_STATUSES = {"active", "disabled", "pending"}


def normalize_avatar_id(avatar_id: str | None) -> str:
    normalized = (avatar_id or DEFAULT_AVATAR_ID).strip().lower()
    if normalized in SUPPORTED_AVATARS:
        return normalized
    return DEFAULT_AVATAR_ID


def normalize_account_status(account_status: str | None) -> str:
    normalized = (account_status or DEFAULT_ACCOUNT_STATUS).strip().lower()
    if normalized in SUPPORTED_ACCOUNT_STATUSES:
        return normalized
    return DEFAULT_ACCOUNT_STATUS


def load_local_env():
    if os.getenv("_ADAPTIVE_ENV_LOADED") == "1":
        return

    protected_keys = set(os.environ.keys())
    candidates = []
    env_filenames = (".env.public", ".env", ".env.secret")
    explicit_paths = (
        Path("/etc/secrets/.env"),
        Path("/etc/secrets/.env.secret"),
        Path("/etc/secrets/.env.public"),
    )
    roots = (
        Path.cwd(),
        Path(__file__).resolve().parents[1],
        Path(__file__).resolve().parent,
    )

    for candidate in explicit_paths:
        if candidate not in candidates:
            candidates.append(candidate)

    for root in roots:
        for filename in env_filenames:
            candidate = root / filename
            if candidate not in candidates:
                candidates.append(candidate)

    for env_path in candidates:
        if not env_path.exists():
            continue
        _load_env_file(env_path, protected_keys)

    os.environ["_ADAPTIVE_ENV_LOADED"] = "1"


def _load_env_file(env_path: Path, protected_keys: set[str]):
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if value and value[0] == value[-1] and value[0] in ['"', "'"]:
            value = value[1:-1]

        if key in protected_keys:
            continue
        os.environ[key] = value


def get_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@lru_cache(maxsize=8)
def load_repo_json_file(filename: str) -> dict:
    path = get_repo_root() / filename
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    return payload if isinstance(payload, dict) else {}
