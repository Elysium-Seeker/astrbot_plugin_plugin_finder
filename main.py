import os
import sys
import subprocess
import asyncio
import httpx
from astrbot.api.all import Context, AstrMessageEvent
from astrbot.api.event.filter import command
from astrbot.api.star import register, Star


@register(
    "astrbot_plugin_plugin_finder",
    "插件发现者",
    "在对话中自行查询、校验、下载并安装 AstrBot 官方平台插件。",
    "1.0.0",
)
class PluginFinder(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.market_api_url = "https://api.soulter.top/astrbot/plugins"

        # 确定插件目录，通常是 data/plugins/
        current_plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self.plugins_root = os.path.dirname(current_plugin_dir)

    async def check_plugin_in_market(self, plugin_name: str) -> dict:
        """检查插件是否存在于官方插件市场"""
        async with httpx.AsyncClient() as client:
            resp = await client.get(self.market_api_url)
            if resp.status_code == 200:
                market_plugins = resp.json()
                # market_API数据结构通常键是插件名如 "astrbot-plugin-DUT-Notices"
                for key, data in market_plugins.items():
                    # 匹配用户传入的名字，可能包含/不包含 'astrbot_plugin_' 前缀
                    if (
                        plugin_name.lower() in key.lower()
                        or plugin_name.lower() in data.get("display_name", "").lower()
                    ):
                        if "repo" in data:
                            return {
                                "name": key,
                                "repo": data["repo"],
                                "display_name": data.get("display_name", key),
                            }
        return {}

    @command("安装插件")
    async def install_plugin(self, event: AstrMessageEvent, plugin_keyword: str):
        """
        安装指定的插件：/安装插件 <插件名或关键字>
        """
        yield event.plain_result(f"正在官方市场中搜索 [{plugin_keyword}] ...")

        # 1. 自动校验是否在官方列表（安全白名单）
        plugin_info = await self.check_plugin_in_market(plugin_keyword)
        if not plugin_info:
            yield event.plain_result(
                f"⚠️ 在官方插件市场中未找到 `{plugin_keyword}`，为保障安全，已终止安装。"
            )
            return

        repo_url = plugin_info["repo"]
        # 必须确保 repo URL 规范，比如转为 github
        if not repo_url.startswith("http"):
            repo_url = f"https://github.com/{repo_url}"

        repo_name = repo_url.rstrip("/").split("/")[-1]
        target_dir = os.path.join(self.plugins_root, repo_name)

        yield event.plain_result(
            f"✅ 找到官方插件：{plugin_info['display_name']} ({repo_name})\n正在执行下载..."
        )

        # 2. 自动下载 (使用 git)
        try:
            if os.path.exists(target_dir):
                yield event.plain_result(
                    "发现已有同名文件夹，正在尝试更新(git pull)或重置..."
                )
                # 简单处理：如果已存在，让用户自行解决，或强制 pull
                process = await asyncio.create_subprocess_exec(
                    "git",
                    "pull",
                    cwd=target_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                await process.communicate()
            else:
                process = await asyncio.create_subprocess_exec(
                    "git",
                    "clone",
                    repo_url,
                    target_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                stdout, stderr = await process.communicate()
                if process.returncode != 0:
                    yield event.plain_result(
                        f"❌ Git Clone 失败：\n{stderr.decode('utf-8', errors='ignore')}"
                    )
                    return
        except Exception as e:
            yield event.plain_result(
                f"❌ 源码下载环节发生错误: {str(e)}\n请确保宿主机已安装 Git。"
            )
            return

        yield event.plain_result("📦 源码下载成功！正在检查依赖(requirements.txt)...")

        # 3. 自动安装依赖
        req_file = os.path.join(target_dir, "requirements.txt")
        if os.path.exists(req_file):
            yield event.plain_result("检测到依赖文件，正在后台执行 pip install...")
            try:
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "-r",
                    "requirements.txt",
                    cwd=target_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                stdout, stderr = await process.communicate()
                if process.returncode != 0:
                    yield event.plain_result(
                        f"⚠️ 依赖安装出现错误，可能会影响插件运行：\n{stderr.decode('utf-8', errors='ignore')}"
                    )
                else:
                    yield event.plain_result("✅ 依赖安装完成！")
            except Exception as e:
                yield event.plain_result(f"⚠️ 依赖自动安装异常：{str(e)}")
        else:
            yield event.plain_result("无需额外安装依赖。")

        # 4. 热重载生效
        yield event.plain_result(
            f"🎉 插件 {plugin_info['display_name']} 下载及依赖安装完毕！\n"
            f"正在通过内部框架自动将其进行热重载并应用更改..."
        )

        # 使用最底层的星级管理器 (StarManager / PluginManager) 实现热重载，无需用户去执行命令。
        try:
            if hasattr(self.context, "_star_manager"):
                # 如果传入插件名，那么只重载该特定插件，如果不传则全部重载
                success, err = await self.context._star_manager.reload(repo_name)
                if success:
                    yield event.plain_result("✅ 热重载触发成功！新插件现已生效。")
                else:
                    yield event.plain_result(
                        f"⚠️ 热重载触发完毕，但可能存在异常或该插件仍需全盘刷新：{err}"
                    )
            else:
                yield event.plain_result(
                    "⚠️ 当前版本似乎不支持后台静默重载，请发送 /plugin reload 使新插件生效。"
                )
        except Exception as e:
            yield event.plain_result(
                f"⚠️ 本地安全重载API调用发生内部错误: {e}\n请手动发送 /plugin reload"
            )
