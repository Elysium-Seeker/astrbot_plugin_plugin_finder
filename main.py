import os

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
    "1.1.8",
)
class PluginFinder(Star):
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

    @filter.llm_tool(name="search_astrbot_plugin")
    async def search_plugin(self, event: AstrMessageEvent, search_keyword: str):
        """当用户想要查找、安装某种功能的插件时，使用此工具去官方市场搜索。
        根据返回的结果，向用户简单推荐最符合的一个或几个插件（包含其基本功能介绍）。
        请务必在回答的最后明确询问用户：“找到了这些插件，是否需要为您安装？”（请使用真实查询到的名称，不要自己编造）。
        禁止在未调用 install_astrbot_plugin 前向用户声称“已经安装成功”。
        """
        results = await self.service.search_plugins(search_keyword)
        if not results:
            return f"未找到与 '{search_keyword}' 有关的插件。请告诉用户需要换个关键词试试。"

        return (
            "找到了以下匹配的插件，请向用户推荐并明确询问'要安装其中哪个插件吗？'\n"
            + str(results)
        )

    @filter.llm_tool(name="install_astrbot_plugin")
    async def install_plugin_tool(
        self,
        event: AstrMessageEvent,
        plugin_name: str,
        has_user_confirmed: bool,
    ):
        """当用户明确同意安装某个特定的插件后（如：回答“是的”、“安装 xx”），调用此工具进行实际的下载和安装。
        plugin_name 请提供在 search 工具中获得的完整插件名称（如 astrbot-plugin-xxx）。
        【极其重要】：如果用户没有明确同意安装，必须将 has_user_confirmed 设置为 False！
        如果由于任何原因你不确定用户是否同意，也设为 False！
        """
        return await self.service.install_plugin_tool(
            event=event,
            plugin_name=plugin_name,
            has_user_confirmed=has_user_confirmed,
        )

    @filter.command("查看安装日志")
    async def show_install_log(self, event: AstrMessageEvent):
        """查看最近一次安装流程的详细日志。"""
        yield event.plain_result(self.service.get_last_install_report(limit=3800))

    @filter.command("查看插件配置")
    async def show_plugin_config(self, event: AstrMessageEvent):
        """查看当前插件运行时配置（来自 _conf_schema.json）。"""
        yield event.plain_result(self.service.format_runtime_config())

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

        if confirm_phrase.strip() != self.config.direct_install_confirm_phrase:
            yield event.plain_result(
                "为避免误触发，请补充确认词。"
                f"\n示例：/直接安装插件 {plugin_keyword} {self.config.direct_install_confirm_phrase}"
            )
            return

        yield event.plain_result(f"执行直接安装命令: {plugin_keyword}...")
        result = await self.service.install_plugin_tool(event, plugin_keyword, True)
        yield event.plain_result(result)
