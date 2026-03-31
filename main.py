import os
import sys
import asyncio
import httpx
from astrbot.api.all import Context, AstrMessageEvent
from astrbot.api.event.filter import command, llm_tool
from astrbot.api.star import register, Star


@register(
    "astrbot_plugin_plugin_finder",
    "插件发现者",
    "支持用户使用自然语言或者命令在官方市场检索、发现、确认并自动安装、热重载 AstrBot 插件。",
    "1.1.0",
)
class PluginFinder(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.market_api_url = "https://api.soulter.top/astrbot/plugins"

        # 确定插件根目录
        current_plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self.plugins_root = os.path.dirname(current_plugin_dir)

    async def _fetch_market_plugins(self) -> dict:
        """获取官方市场的全部插件数据"""
        async with httpx.AsyncClient() as client:
            resp = await client.get(self.market_api_url)
            if resp.status_code == 200:
                return resp.json()
        return {}

    @llm_tool(name="search_astrbot_plugin")
    async def search_plugin(self, event: AstrMessageEvent, search_keyword: str):
        """当用户想要查找、安装某种功能的插件时，使用此工具去官方市场搜索。
        根据返回的结果，向用户简单推荐最符合的一个或几个插件（包含其基本功能介绍）。
        请务必在回答的最后明确询问用户：“找到了这些插件，是否需要为您安装？”（请使用真实查询到的名称，不要自己编造）。
        """
        plugins = await self._fetch_market_plugins()
        results = []
        for key, data in plugins.items():
            desc = data.get("desc", "")
            display_name = data.get("display_name", key)
            if (
                search_keyword.lower() in desc.lower()
                or search_keyword.lower() in display_name.lower()
                or search_keyword.lower() in key.lower()
            ):
                results.append(
                    {
                        "plugin_name": key,
                        "display_name": display_name,
                        "description": desc,
                        "repo_url": data.get("repo", ""),
                    }
                )

        if not results:
            return f"未找到与 '{search_keyword}' 有关的插件。请告诉用户需要换个关键词试试。"

        # 限制返回数量避免超出 token
        results = results[:5]
        return (
            "找到了以下匹配的插件，请向用户推荐并明确询问'要安装其中哪个插件吗？'\n"
            + str(results)
        )

    @llm_tool(name="install_astrbot_plugin")
    async def install_plugin_tool(
        self, event: AstrMessageEvent, plugin_name: str, has_user_confirmed: bool
    ):
        """当用户明确同意安装某个特定的插件后（如：回答“是的”、“安装 xx”），调用此工具进行实际的下载和安装。
        plugin_name 请提供在 search 工具中获得的完整插件名称或 repo_url（如果可以的话最好是完整的 astrbot_plugin_xxx 格式）。
        【极其重要】：如果用户没有明确同意安装，必须将 has_user_confirmed 设置为 False！
        如果由于任何原因你不确定用户是否同意，也设为 False！
        """
        if not has_user_confirmed:
            return "执行已被拒绝：请先向用户询问'找到插件...，是否确认安装？'，等用户确认后再调用此工具并传入 true 参数。"

        # 执行耗时操作时可以先利用 yield 发送提示，但 llm_tool 中我们也可以借助于 event.send
        await event.send(
            event.plain_result(
                f"⏳ 收到确认，开始为您安装插件：{plugin_name}，请稍候..."
            )
        )

        # 1. 在市场中校验以获取正确的 repo 和 name
        plugins = await self._fetch_market_plugins()
        target_data = None
        target_key = None
        for key, data in plugins.items():
            if (
                plugin_name.lower() == key.lower()
                or plugin_name.lower() == data.get("repo", "").lower()
            ):
                target_data = data
                target_key = key
                break

        if not target_data:
            # 尝试宽松匹配
            for key, data in plugins.items():
                if (
                    plugin_name.lower() in key.lower()
                    or plugin_name.lower() in data.get("display_name", "").lower()
                ):
                    target_data = data
                    target_key = key
                    break

        if not target_data:
            return f"安装失败：在市场中未找到名为 {plugin_name} 的合法插件，为保证安全已终止安装。"

        repo_url = target_data["repo"]
        if not repo_url.startswith("http"):
            repo_url = f"https://github.com/{repo_url}"

        repo_name = repo_url.rstrip("/").split("/")[-1]
        target_dir = os.path.join(self.plugins_root, repo_name)

        # 2. Git Clone
        # 为了不阻塞 LLM 太久，我们可以做简单的快速拉取
        try:
            if os.path.exists(target_dir):
                process = await asyncio.create_subprocess_exec(
                    "git", "pull", cwd=target_dir
                )
                await process.communicate()
            else:
                process = await asyncio.create_subprocess_exec(
                    "git", "clone", repo_url, target_dir
                )
                await process.communicate()
                if process.returncode != 0:
                    return "安装失败：Git Clone 失败，可能网络问题。"
        except Exception as e:
            return f"安装中发生本地异常：{e}"

        # 3. 安装依赖
        req_file = os.path.join(target_dir, "requirements.txt")
        if os.path.exists(req_file):
            try:
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "-r",
                    "requirements.txt",
                    cwd=target_dir,
                )
                await process.communicate()
            except Exception:
                pass

        # 4. 热重载
        try:
            if hasattr(self.context, "_star_manager"):
                success, err = await self.context._star_manager.reload(repo_name)
                if success:
                    return f"插件 {target_data.get('display_name', target_key)} 安装完全成功，并且已经通过热重载在后台生效了！请用友好的口吻向用户汇报这个好消息。"
                else:
                    return f"插件 {target_key} 已就绪，但热重载存在问题：{err}。可能部分功能受限，建议用户之后重启。"
            else:
                return "插件已安装完毕！但当前版本不支持静默热重载，请建议用户发送 /plugin reload 命令。"
        except Exception as e:
            return f"安装成功，但应用刷新时出错了：{e}。"

    @command("直接安装插件")
    async def cmd_direct_install(self, event: AstrMessageEvent, plugin_keyword: str):
        """
        通过命令直接强制安装：/直接安装插件 <插件名>
        """
        yield event.plain_result(f"执行直接安装命令: {plugin_keyword}...")
        result = await self.install_plugin_tool(event, plugin_keyword, True)
        yield event.plain_result(result)
