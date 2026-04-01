import re
from dataclasses import dataclass
from urllib.parse import urlparse

from astrbot.api import logger


@dataclass
class PluginFinderConfig:
    market_api_url: str
    allowed_market_api_hosts: set[str]
    git_bin: str
    git_timeout_sec: int
    pip_install_requirements: bool
    trusted_requirements_plugins: set[str]
    pip_timeout_sec: int
    auto_reload_after_install: bool
    full_reload_fallback: bool
    recover_non_git_dir: bool
    allowed_repo_hosts: set[str]
    direct_install_confirm_phrase: str


def _cfg(plugin_config, key: str, default):
    try:
        if isinstance(plugin_config, dict):
            return plugin_config.get(key, default)
        if hasattr(plugin_config, "get"):
            return plugin_config.get(key, default)
        return default
    except Exception as e:
        logger.warning(f"读取配置项失败 key={key}: {e}")
        return default


def _as_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _as_int(value, default: int) -> int:
    if isinstance(value, bool):
        logger.warning(f"整数配置不接受布尔值 value={value}，已回退默认值 {default}")
        return default

    try:
        parsed = int(value)
        return parsed if parsed > 0 else default
    except Exception as e:
        logger.warning(f"整数配置解析失败 value={value}: {e}")
        return default


def _parse_host_allowlist(value) -> set[str]:
    raw_items: list[str] = []
    if isinstance(value, str):
        raw_items = [i.strip().lower() for i in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        raw_items = [str(i).strip().lower() for i in value]

    safe_hosts = {
        host
        for host in raw_items
        if host
        and host not in {".", ".."}
        and re.fullmatch(r"[a-z0-9.-]+", host)
    }
    # 防止误配置成空白名单导致全部安装都被阻断。
    return safe_hosts or {"github.com"}


def _parse_plugin_allowlist(value) -> set[str]:
    raw_items: list[str] = []
    if isinstance(value, str):
        raw_items = [i.strip() for i in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        raw_items = [str(i).strip() for i in value]

    return {item for item in raw_items if item}


def _is_allowed_host(url: str, allowed_hosts: set[str]) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme not in {"http", "https"}:
        return False

    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False

    if host in allowed_hosts:
        return True

    return any(host.endswith(f".{allowed}") for allowed in allowed_hosts)


def _validate_market_api_url(
    raw_url: str,
    allowed_hosts: set[str],
    fallback_url: str,
) -> str:
    if _is_allowed_host(raw_url, allowed_hosts):
        return raw_url

    logger.warning(
        "market_api_url 不在允许范围内或协议非法，已回退默认地址。"
        f" raw={raw_url}, allowed_hosts={sorted(allowed_hosts)}"
    )
    return fallback_url


def load_plugin_finder_config(plugin_config) -> PluginFinderConfig:
    default_market_api_url = "https://api.soulter.top/astrbot/plugins"
    allowed_market_api_hosts = _parse_host_allowlist(
        _cfg(plugin_config, "allowed_market_api_hosts", "api.soulter.top")
    )
    raw_market_api_url = str(
        _cfg(plugin_config, "market_api_url", default_market_api_url)
    ).strip() or default_market_api_url
    market_api_url = _validate_market_api_url(
        raw_market_api_url,
        allowed_market_api_hosts,
        default_market_api_url,
    )

    git_bin = str(_cfg(plugin_config, "git_bin", "git")).strip() or "git"

    direct_install_confirm_phrase = str(
        _cfg(plugin_config, "direct_install_confirm_phrase", "确认安装")
    ).strip() or "确认安装"

    return PluginFinderConfig(
        market_api_url=market_api_url,
        allowed_market_api_hosts=allowed_market_api_hosts,
        git_bin=git_bin,
        git_timeout_sec=_as_int(_cfg(plugin_config, "git_timeout_sec", 120), 120),
        pip_install_requirements=_as_bool(
            _cfg(plugin_config, "pip_install_requirements", False),
            False,
        ),
        trusted_requirements_plugins=_parse_plugin_allowlist(
            _cfg(plugin_config, "trusted_requirements_plugins", "")
        ),
        pip_timeout_sec=_as_int(_cfg(plugin_config, "pip_timeout_sec", 600), 600),
        auto_reload_after_install=_as_bool(
            _cfg(plugin_config, "auto_reload_after_install", True),
            True,
        ),
        full_reload_fallback=_as_bool(
            _cfg(plugin_config, "full_reload_fallback", True),
            True,
        ),
        recover_non_git_dir=_as_bool(_cfg(plugin_config, "recover_non_git_dir", True), True),
        allowed_repo_hosts=_parse_host_allowlist(
            _cfg(plugin_config, "allowed_repo_hosts", "github.com")
        ),
        direct_install_confirm_phrase=direct_install_confirm_phrase,
    )
