import re
from dataclasses import dataclass

from astrbot.api import logger


@dataclass
class PluginFinderConfig:
    market_api_url: str
    git_bin: str
    git_timeout_sec: int
    pip_install_requirements: bool
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


def load_plugin_finder_config(plugin_config) -> PluginFinderConfig:
    market_api_url = str(
        _cfg(plugin_config, "market_api_url", "https://api.soulter.top/astrbot/plugins")
    ).strip() or "https://api.soulter.top/astrbot/plugins"
    git_bin = str(_cfg(plugin_config, "git_bin", "git")).strip() or "git"

    direct_install_confirm_phrase = str(
        _cfg(plugin_config, "direct_install_confirm_phrase", "确认安装")
    ).strip() or "确认安装"

    return PluginFinderConfig(
        market_api_url=market_api_url,
        git_bin=git_bin,
        git_timeout_sec=_as_int(_cfg(plugin_config, "git_timeout_sec", 120), 120),
        pip_install_requirements=_as_bool(
            _cfg(plugin_config, "pip_install_requirements", True),
            True,
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
