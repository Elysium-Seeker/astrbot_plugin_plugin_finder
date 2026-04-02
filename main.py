import json
import os
import re
import asyncio

from astrbot.api import logger
from astrbot.api.all import Context, AstrMessageEvent
from astrbot.api.event import filter
from astrbot.api.star import register, Star

if __package__:
    from .plugin_finder_config import load_plugin_finder_config
    from .plugin_finder_service import PluginFinderService
else:
    from plugin_finder_config import load_plugin_finder_config
    from plugin_finder_service import PluginFinderService


@register(
    "astrbot_plugin_plugin_finder",
    "插件发现者",
    "支持用户使用自然语言或者命令在官方市场检索、发现、确认并自动安装、热重载 AstrBot 插件。",
    "1.1.22",
)
class PluginFinder(Star):
    _INVALID_PLUGIN_LITERALS = {
        "plugin",
        "plugin_name",
        "pluginname",
        "plugin_keyword",
        "target_plugin",
        "name",
        "args",
        "kwargs",
        "search_astrbot_plugin",
        "install_astrbot_plugin",
    }

    _INVALID_SEARCH_LITERALS = {
        "search",
        "search_keyword",
        "searchkeyword",
        "search_astrbot_plugin",
        "install_astrbot_plugin",
        "keyword",
        "query",
        "name",
        "plugin",
        "plugin_name",
        "pluginname",
        "plugin_keyword",
        "has_user_confirmed",
        "user_confirmed",
        "confirmed",
        "is_confirmed",
        "args",
        "kwargs",
        "true",
        "false",
        "yes",
        "no",
        "ok",
        "confirm",
    }

    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.config = load_plugin_finder_config(config or {})

        current_plugin_dir = os.path.dirname(os.path.abspath(__file__))
        plugins_root = os.path.dirname(current_plugin_dir)
        self.service = PluginFinderService(
            context=self.context,
            config=self.config,
            plugins_root=plugins_root,
        )

    @staticmethod
    def _compact_text(value: str, limit: int) -> str:
        text = (value or "").strip()
        if len(text) <= limit:
            return text
        if limit <= 3:
            return text[:limit]
        return text[: limit - 3] + "..."

    @staticmethod
    def _format_search_results(results: list[dict]) -> str:
        compact_items = []
        for item in results[:3]:
            compact_items.append(
                {
                    "plugin_name": str(item.get("plugin_name", "")).strip(),
                    "display_name": str(item.get("display_name", "")).strip(),
                    "description": PluginFinder._compact_text(
                        str(item.get("description", "")),
                        100,
                    ),
                }
            )

        payload = {
            "total": len(results),
            "items": compact_items,
            "install_hint": "安装时必须传 plugin_name=items[].plugin_name",
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _pick_first_non_empty(mapping: dict, candidate_keys: tuple[str, ...]) -> str:
        for key in candidate_keys:
            value = mapping.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return ""

    @staticmethod
    def _extract_plugin_name_token(text: str) -> str:
        raw = (text or "").strip()
        if not raw:
            return ""

        match = re.search(r"(astrbot[_-]plugin[_-][A-Za-z0-9._-]+)", raw, flags=re.IGNORECASE)
        if match:
            return match.group(1)

        normalized = raw.strip("\"' ")
        lowered = normalized.lower()
        if (
            normalized
            and "plugin" in normalized.lower()
            and re.fullmatch(r"[A-Za-z0-9._-]+", normalized)
            and lowered not in PluginFinder._INVALID_PLUGIN_LITERALS
        ):
            return normalized

        # Keep a permissive fallback for direct tool arguments,
        # then let service-level matching decide exact target.
        if normalized and lowered not in PluginFinder._INVALID_PLUGIN_LITERALS:
            return normalized[:120]

        return ""

    @staticmethod
    def _collect_string_values(value, *, depth: int = 0) -> list[str]:
        if depth > 4:
            return []

        if value is None:
            return []

        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []

            collected = [text]
            if text[:1] in {"{", "["}:
                try:
                    parsed = json.loads(text)
                    collected.extend(
                        PluginFinder._collect_string_values(parsed, depth=depth + 1)
                    )
                except Exception:
                    pass
            return collected

        if isinstance(value, dict):
            collected: list[str] = []
            for key, item in value.items():
                collected.extend(PluginFinder._collect_string_values(key, depth=depth + 1))
                collected.extend(PluginFinder._collect_string_values(item, depth=depth + 1))
            return collected

        if isinstance(value, (list, tuple, set)):
            collected: list[str] = []
            for item in value:
                collected.extend(PluginFinder._collect_string_values(item, depth=depth + 1))
            return collected

        return [str(value)]

    @staticmethod
    def _collect_string_values_only(value, *, depth: int = 0) -> list[str]:
        if depth > 4:
            return []

        if value is None:
            return []

        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []

            collected = [text]
            if text[:1] in {"{", "["}:
                try:
                    parsed = json.loads(text)
                    collected.extend(
                        PluginFinder._collect_string_values_only(parsed, depth=depth + 1)
                    )
                except Exception:
                    pass
            return collected

        if isinstance(value, dict):
            collected: list[str] = []
            for item in value.values():
                collected.extend(
                    PluginFinder._collect_string_values_only(item, depth=depth + 1)
                )
            return collected

        if isinstance(value, (list, tuple, set)):
            collected: list[str] = []
            for item in value:
                collected.extend(
                    PluginFinder._collect_string_values_only(item, depth=depth + 1)
                )
            return collected

        return [str(value)]

    @staticmethod
    def _extract_plugin_name_from_kwargs(kwargs: dict) -> str:
        if not kwargs:
            return ""

        direct_keys = (
            "plugin_name",
            "plugin",
            "name",
            "plugin_keyword",
            "target_plugin",
            "pluginName",
            "plugin_name_or_keyword",
            "selected_plugin_name",
            "selectedPlugin",
            "plugin_id",
            "id",
            "candidate",
            "selection",
            "query",
            "search_keyword",
            "keyword",
        )

        for key in direct_keys:
            if key not in kwargs:
                continue
            token = PluginFinder._extract_plugin_name_token(str(kwargs.get(key) or ""))
            if token:
                return token

        tokens: list[str] = []
        for text in PluginFinder._collect_string_values_only(kwargs):
            token = PluginFinder._extract_plugin_name_token(text)
            if token and token not in tokens:
                tokens.append(token)

        plugin_candidates = [
            item
            for item in tokens
            if re.search(r"astrbot[_-]plugin[_-]", item, flags=re.IGNORECASE)
        ]
        if len(plugin_candidates) == 1:
            return plugin_candidates[0]

        if len(plugin_candidates) > 1:
            return ""

        if len(tokens) == 1:
            return tokens[0]

        return ""

    @staticmethod
    def _extract_plugin_name_from_event(event: AstrMessageEvent) -> str:
        possible_attrs = (
            "message_str",
            "message",
            "raw_message",
            "content",
            "text",
        )

        texts: list[str] = []
        for attr in possible_attrs:
            try:
                value = getattr(event, attr, None)
            except Exception:
                continue

            if value is None:
                continue

            if callable(value):
                try:
                    value = value()
                except Exception:
                    continue

            texts.extend(PluginFinder._collect_string_values_only(value))

        for text in texts:
            token = PluginFinder._extract_plugin_name_token(text)
            if token:
                return token

        return ""

    @staticmethod
    def _extract_search_keyword_token(text: str) -> str:
        raw = (text or "").strip().strip("\"'")
        if not raw:
            return ""

        plugin_match = re.search(
            r"(astrbot[_-]plugin[_-][A-Za-z0-9._-]+)",
            raw,
            flags=re.IGNORECASE,
        )
        if plugin_match:
            return plugin_match.group(1)

        lowered = raw.lower()
        if lowered in PluginFinder._INVALID_SEARCH_LITERALS:
            return ""

        cleaned = re.sub(
            r"^(?:请|麻烦|帮我|请你|bot[，,:\s]*|我想|我想要|我需要|给我|替我)+",
            "",
            raw,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"(?:帮我|请你)?(?:搜索|查找|找|搜|安装|装)(?:一个|一下|下|个)?",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = cleaned.strip(" ：:，,。.!?！？")
        cleaned = re.sub(r"(?:的)?插件$", "", cleaned).strip()

        if cleaned:
            lowered_cleaned = cleaned.lower()
            if lowered_cleaned not in PluginFinder._INVALID_SEARCH_LITERALS:
                if re.fullmatch(r"[A-Za-z0-9._-]{2,64}", cleaned):
                    return cleaned
                if re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9._-]{1,20}", cleaned):
                    return cleaned

        if re.fullmatch(r"[A-Za-z0-9._-]{2,64}", raw):
            return raw

        if re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9._-]{1,20}", raw):
            return raw

        # Do not over-filter: keep non-empty keyword as fallback
        # unless it is an obvious structural/control literal.
        if lowered not in PluginFinder._INVALID_SEARCH_LITERALS:
            return raw[:120]

        return ""

    @staticmethod
    def _extract_search_keyword_from_kwargs(kwargs: dict) -> str:
        if not kwargs:
            return ""

        direct_keys = (
            "search_keyword",
            "keyword",
            "query",
            "search",
            "plugin_keyword",
            "plugin_name",
            "plugin",
            "name",
            "searchKeyword",
            "pluginName",
            "q",
            "text",
            "content",
        )

        for key in direct_keys:
            if key not in kwargs:
                continue
            token = PluginFinder._extract_search_keyword_token(str(kwargs.get(key) or ""))
            if token:
                return token

        candidates: list[str] = []
        for text in PluginFinder._collect_string_values_only(kwargs):
            token = PluginFinder._extract_search_keyword_token(text)
            if token and token.lower() not in PluginFinder._INVALID_SEARCH_LITERALS:
                if token not in candidates:
                    candidates.append(token)

        if not candidates:
            return ""

        plugin_candidates = [
            item
            for item in candidates
            if re.search(r"astrbot[_-]plugin[_-]", item, flags=re.IGNORECASE)
        ]
        if plugin_candidates:
            return plugin_candidates[0]

        return candidates[0]

    @staticmethod
    def _extract_search_keyword_from_event(event: AstrMessageEvent) -> str:
        possible_attrs = (
            "message_str",
            "message",
            "raw_message",
            "content",
            "text",
        )

        texts: list[str] = []
        for attr in possible_attrs:
            try:
                value = getattr(event, attr, None)
            except Exception:
                continue

            if value is None:
                continue

            if callable(value):
                try:
                    value = value()
                except Exception:
                    continue

            texts.extend(PluginFinder._collect_string_values_only(value))

        for text in texts:
            plugin_token = PluginFinder._extract_plugin_name_token(text)
            if plugin_token:
                return plugin_token

        for text in texts:
            keyword = PluginFinder._extract_search_keyword_token(text)
            if keyword:
                return keyword

        return ""

    @staticmethod
    def _as_confirmed_flag(value) -> bool:
        if isinstance(value, bool):
            return value

        if isinstance(value, (int, float)):
            if value in {0, 1}:
                return bool(value)
            return False

        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on", "ok", "confirm", "已确认", "确认", "是", "好的"}:
                return True
            if normalized in {"0", "false", "no", "off", "否", "未确认", "取消"}:
                return False

        return False

    @filter.llm_tool(name="search_astrbot_plugin")
    async def search_plugin(
        self,
        event: AstrMessageEvent,
        search_keyword: str = "",
        **kwargs,
    ):
        """搜索官方市场插件并返回候选。

        Args:
            search_keyword (str): 搜索关键词，可为功能词或插件名。
        """
        try:
            if not (search_keyword or "").strip() and kwargs:
                search_keyword = self._extract_search_keyword_from_kwargs(kwargs)

            if not (search_keyword or "").strip():
                search_keyword = self._extract_search_keyword_from_event(event)

            if not (search_keyword or "").strip():
                return "[SEARCH_FAIL] 搜索关键词为空，请先告诉我你想找什么功能的插件。"

            results = await self.service.search_plugins(search_keyword)
            if not results:
                return f"未找到与 '{search_keyword}' 有关的插件。请告诉用户需要换个关键词试试。"

            return self._format_search_results(results)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"search_plugin 执行失败: {e}")
            return "[SEARCH_FAIL] 检索插件时发生异常，请稍后重试。"

    @filter.llm_tool(name="install_astrbot_plugin")
    async def install_plugin_tool(
        self,
        event: AstrMessageEvent,
        plugin_name: str = "",
        has_user_confirmed: bool = False,
        **kwargs,
    ):
        """用户明确确认后执行安装。

        Args:
            plugin_name (str): 目标插件名，建议传 search 返回的完整 plugin_name。
            has_user_confirmed (bool): 用户是否明确确认安装。
        """
        try:
            if not (plugin_name or "").strip() and kwargs:
                plugin_name = self._extract_plugin_name_from_kwargs(kwargs)

            if not (plugin_name or "").strip():
                plugin_name = self._extract_plugin_name_from_event(event)

            confirmed_value = has_user_confirmed
            if kwargs:
                for key in (
                    "has_user_confirmed",
                    "confirmed",
                    "user_confirmed",
                    "confirm",
                    "is_confirmed",
                ):
                    if key in kwargs:
                        confirmed_value = kwargs[key]
                        break

            has_user_confirmed_bool = self._as_confirmed_flag(confirmed_value)

            return await self.service.install_plugin_tool(
                event=event,
                plugin_name=plugin_name,
                has_user_confirmed=has_user_confirmed_bool,
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"install_plugin_tool 执行失败: {e}")
            return "[INSTALL_FAIL] 安装流程执行异常，请稍后重试。"

    @filter.command("查看安装日志")
    async def show_install_log(self, event: AstrMessageEvent):
        """查看最近一次安装流程的详细日志。"""
        yield event.plain_result(self.service.get_last_install_report(limit=2400))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("查看插件配置")
    async def show_plugin_config(self, event: AstrMessageEvent):
        """查看当前插件运行时配置（来自 _conf_schema.json）。"""
        yield event.plain_result(self.service.format_runtime_config())

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("直接安装插件")
    async def cmd_direct_install(
        self,
        event: AstrMessageEvent,
        plugin_keyword: str,
        confirm_phrase: str = "",
    ):
        """
        通过命令直接强制安装：/直接安装插件 <插件名> <确认词>
        """
        plugin_keyword = plugin_keyword.strip()
        if not plugin_keyword:
            yield event.plain_result("请输入有效插件名，例如：/直接安装插件 astrbot_plugin_weather 确认安装")
            return

        if not self.config.direct_install_confirm_phrase:
            yield event.plain_result(
                "直接安装命令当前已禁用。"
                "\n请先在插件配置中设置 direct_install_confirm_phrase（建议使用高强度随机短语）。"
            )
            return

        if confirm_phrase.strip() != self.config.direct_install_confirm_phrase:
            yield event.plain_result(
                "确认词不正确，已拒绝执行高风险安装命令。"
                "\n请检查 direct_install_confirm_phrase 配置后重试。"
            )
            return

        yield event.plain_result(f"执行直接安装命令: {plugin_keyword}...")
        try:
            result = await self.service.install_plugin_tool(event, plugin_keyword, True)
            yield event.plain_result(result)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"cmd_direct_install 执行失败: {e}")
            yield event.plain_result("[INSTALL_FAIL] 直接安装流程异常，请稍后重试。")
