import os
import sys
import asyncio
from datetime import datetime
import httpx
from astrbot.api.all import Context, AstrMessageEvent
from astrbot.api.event.filter import command, llm_tool
from astrbot.api.star import register, Star


@register(
    "astrbot_plugin_plugin_finder",
    "插件发现者",
    "支持用户使用自然语言或者命令在官方市场检索、发现、确认并自动安装、热重载 AstrBot 插件。",
    "1.1.2",
)
class PluginFinder(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.plugin_config = config or {}
        self.market_api_url = str(
            self._cfg("market_api_url", "https://api.soulter.top/astrbot/plugins")
        ).strip() or "https://api.soulter.top/astrbot/plugins"
        self.git_bin = str(self._cfg("git_bin", "git")).strip() or "git"
        self.pip_install_requirements = self._as_bool(
            self._cfg("pip_install_requirements", True),
            True,
        )
        self.auto_reload_after_install = self._as_bool(
            self._cfg("auto_reload_after_install", True),
            True,
        )
        self.full_reload_fallback = self._as_bool(
            self._cfg("full_reload_fallback", True),
            True,
        )
        self.recover_non_git_dir = self._as_bool(
            self._cfg("recover_non_git_dir", True),
            True,
        )
        self.git_timeout_sec = self._as_int(self._cfg("git_timeout_sec", 120), 120)
        self.pip_timeout_sec = self._as_int(self._cfg("pip_timeout_sec", 600), 600)
        self._last_install_report = "尚无安装记录。"

        # 确定插件根目录
        current_plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self.plugins_root = os.path.dirname(current_plugin_dir)

    def _cfg(self, key: str, default):
        try:
            if isinstance(self.plugin_config, dict):
                return self.plugin_config.get(key, default)
            if hasattr(self.plugin_config, "get"):
                return self.plugin_config.get(key, default)
            return default
        except Exception:
            return default

    @staticmethod
    def _as_bool(value, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        if isinstance(value, (int, float)):
            return bool(value)
        return default

    @staticmethod
    def _as_int(value, default: int) -> int:
        try:
            parsed = int(value)
            return parsed if parsed > 0 else default
        except Exception:
            return default

    async def _fetch_market_plugins(self) -> dict:
        """获取官方市场的全部插件数据"""
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(self.market_api_url)
                if resp.status_code == 200 and isinstance(resp.json(), dict):
                    return resp.json()
        except Exception:
            return {}
        return {}

    @staticmethod
    def _normalize(name: str) -> str:
        return (name or "").lower().replace("-", "").replace("_", "").replace(" ", "")

    @staticmethod
    def _shorten(text: str, limit: int = 600) -> str:
        if len(text) <= limit:
            return text
        return text[:limit] + " ...[输出过长已截断]"

    async def _run_cmd(
        self,
        *args: str,
        cwd: str | None = None,
        timeout_sec: int | None = None,
    ) -> tuple[int, str, str]:
        process = await asyncio.create_subprocess_exec(
            *args,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        timeout_value = timeout_sec if timeout_sec is not None else self.git_timeout_sec
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_value,
            )
        except TimeoutError:
            process.kill()
            await process.communicate()
            return 124, "", f"命令超时({timeout_value}s): {' '.join(args)}"
        out_text = stdout.decode("utf-8", errors="ignore")
        err_text = stderr.decode("utf-8", errors="ignore")
        return process.returncode, out_text, err_text

    @staticmethod
    def _parse_reload_result(result) -> tuple[bool, str]:
        if isinstance(result, tuple) and len(result) >= 2:
            return bool(result[0]), str(result[1])
        return bool(result), ""

    @llm_tool(name="search_astrbot_plugin")
    async def search_plugin(self, event: AstrMessageEvent, search_keyword: str):
        """当用户想要查找、安装某种功能的插件时，使用此工具去官方市场搜索。
        根据返回的结果，向用户简单推荐最符合的一个或几个插件（包含其基本功能介绍）。
        请务必在回答的最后明确询问用户：“找到了这些插件，是否需要为您安装？”（请使用真实查询到的名称，不要自己编造）。
        禁止在未调用 install_astrbot_plugin 前向用户声称“已经安装成功”。
        """
        plugins = await self._fetch_market_plugins()
        results = []
        for key, data in plugins.items():
            desc = str(data.get("desc") or "")
            display_name = str(data.get("display_name") or key)
            if (
                search_keyword.lower() in desc.lower()
                or search_keyword.lower() in display_name.lower()
                or search_keyword.lower() in str(key).lower()
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
        plugin_name 请提供在 search 工具中获得的完整插件名称（如 astrbot-plugin-xxx）。
        【极其重要】：如果用户没有明确同意安装，必须将 has_user_confirmed 设置为 False！
        如果由于任何原因你不确定用户是否同意，也设为 False！
        """
        report_lines = [
            f"时间: {datetime.now().isoformat(timespec='seconds')}",
            f"用户输入: {plugin_name}",
            f"插件根目录: {self.plugins_root}",
            f"配置: market_api_url={self.market_api_url}, git_bin={self.git_bin}",
        ]

        if not has_user_confirmed:
            report_lines.append("用户未确认安装，流程终止。")
            self._last_install_report = "\n".join(report_lines)
            return "[INSTALL_BLOCKED] 执行已被拒绝：请先向用户询问并确认安装，再调用此工具。"

        # 执行耗时操作时可以先利用 yield 发送提示，但 llm_tool 中我们也可以借助于 event.send
        await event.send(
            event.plain_result(
                f"⏳ 收到确认，开始为您安装插件：{plugin_name}，请稍候..."
            )
        )

        # 1. 在市场中校验以获取正确的 repo 和 name
        plugins = await self._fetch_market_plugins()
        if not plugins:
            report_lines.append("市场 API 拉取失败或返回为空。")
            self._last_install_report = "\n".join(report_lines)
            return "[INSTALL_FAIL] 无法访问官方市场 API，请稍后重试。"

        target_data = None
        target_key = None
        norm_plugin_name = self._normalize(plugin_name)

        # 尝试精确匹配（无视连接符大小写）
        for key, data in plugins.items():
            norm_key = self._normalize(key)
            norm_repo = self._normalize(str(data.get("repo") or "").split("/")[-1])
            if norm_plugin_name == norm_key or norm_plugin_name == norm_repo:
                target_data = data
                target_key = key
                break

        if not target_data:
            # 尝试宽松匹配
            for key, data in plugins.items():
                norm_key = self._normalize(key)
                norm_display = self._normalize(str(data.get("display_name") or ""))
                if (
                    norm_plugin_name in norm_key
                    or norm_plugin_name in norm_display
                    or norm_key in norm_plugin_name
                ):
                    target_data = data
                    target_key = key
                    break

        if not target_data:
            report_lines.append("市场匹配失败。")
            self._last_install_report = "\n".join(report_lines)
            return f"[INSTALL_FAIL] 安装失败：在市场中未找到名为 {plugin_name} 的合法插件。"

        repo_url = str(target_data.get("repo") or "").strip()
        if not repo_url:
            report_lines.append(f"匹配成功但 repo 为空，插件键: {target_key}")
            self._last_install_report = "\n".join(report_lines)
            return f"[INSTALL_FAIL] 安装失败：插件 {target_key} 缺少仓库地址。"

        if not repo_url.startswith("http"):
            repo_url = f"https://github.com/{repo_url}"

        repo_name = repo_url.rstrip("/").split("/")[-1]
        target_dir = os.path.join(self.plugins_root, repo_name)
        report_lines.append(f"匹配插件键: {target_key}")
        report_lines.append(f"仓库地址: {repo_url}")
        report_lines.append(f"目标目录: {target_dir}")

        # 2. 先验证仓库可达，避免模型“说安装了但其实没执行”
        await event.send(event.plain_result(f"🔎 验证仓库可达性: {repo_url}"))
        code, out, err = await self._run_cmd(
            self.git_bin,
            "ls-remote",
            repo_url,
            timeout_sec=self.git_timeout_sec,
        )
        report_lines.append(f"git ls-remote 返回码: {code}")
        if code != 0:
            report_lines.append(f"git ls-remote 错误: {self._shorten(err)}")
            self._last_install_report = "\n".join(report_lines)
            return f"[INSTALL_FAIL] 无法访问仓库地址，错误信息: {self._shorten(err)}"

        # 3. Git Clone / Pull，严格检查返回码
        try:
            if os.path.exists(target_dir) and not os.path.isdir(
                os.path.join(target_dir, ".git")
            ):
                if self.recover_non_git_dir:
                    backup_dir = (
                        f"{target_dir}__backup_"
                        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    )
                    os.rename(target_dir, backup_dir)
                    report_lines.append(
                        f"目标目录不是 git 仓库，已自动备份到: {backup_dir}"
                    )
                else:
                    report_lines.append("目标目录存在但不是 git 仓库，且未启用自动恢复。")
                    self._last_install_report = "\n".join(report_lines)
                    return (
                        "[INSTALL_FAIL] 目标目录存在但不是 Git 仓库，无法 pull。"
                        "\n可在配置中开启 recover_non_git_dir 自动恢复。"
                    )

            if os.path.exists(target_dir):
                await event.send(event.plain_result("📦 目录已存在，执行 git pull 更新..."))
                code, out, err = await self._run_cmd(
                    self.git_bin,
                    "pull",
                    cwd=target_dir,
                    timeout_sec=self.git_timeout_sec,
                )
                report_lines.append(f"git pull 返回码: {code}")
                if code != 0:
                    report_lines.append(f"git pull 错误: {self._shorten(err)}")
                    self._last_install_report = "\n".join(report_lines)
                    return f"[INSTALL_FAIL] git pull 失败: {self._shorten(err)}"
            else:
                await event.send(event.plain_result("📥 目录不存在，执行 git clone..."))
                code, out, err = await self._run_cmd(
                    self.git_bin,
                    "clone",
                    repo_url,
                    target_dir,
                    timeout_sec=self.git_timeout_sec,
                )
                report_lines.append(f"git clone 返回码: {code}")
                if code != 0:
                    report_lines.append(f"git clone 错误: {self._shorten(err)}")
                    self._last_install_report = "\n".join(report_lines)
                    return f"[INSTALL_FAIL] Git Clone 失败: {self._shorten(err)}"
        except Exception as e:
            report_lines.append(f"Git 阶段异常: {e}")
            self._last_install_report = "\n".join(report_lines)
            return f"[INSTALL_FAIL] 安装中发生本地异常: {e}"

        # 4. 下载后二次校验，确保 WebUI 可发现
        if not os.path.isdir(target_dir):
            report_lines.append("目标目录不存在，疑似 clone 未实际落盘。")
            self._last_install_report = "\n".join(report_lines)
            return "[INSTALL_FAIL] 目录校验失败：仓库目录不存在。"

        metadata_file = os.path.join(target_dir, "metadata.yaml")
        report_lines.append(f"metadata.yaml 是否存在: {os.path.exists(metadata_file)}")
        if not os.path.exists(metadata_file):
            self._last_install_report = "\n".join(report_lines)
            return "[INSTALL_FAIL] 插件目录缺少 metadata.yaml，WebUI 不会识别此目录为插件。"

        # 5. 安装依赖，严格检查返回码
        req_file = os.path.join(target_dir, "requirements.txt")
        if self.pip_install_requirements and os.path.exists(req_file):
            try:
                await event.send(event.plain_result("🧩 检测到 requirements.txt，执行 pip install..."))
                code, out, err = await self._run_cmd(
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "-r",
                    "requirements.txt",
                    cwd=target_dir,
                    timeout_sec=self.pip_timeout_sec,
                )
                report_lines.append(f"pip install 返回码: {code}")
                if code != 0:
                    report_lines.append(f"pip install 错误: {self._shorten(err)}")
                    self._last_install_report = "\n".join(report_lines)
                    return f"[INSTALL_FAIL] 依赖安装失败: {self._shorten(err)}"
            except Exception as e:
                report_lines.append(f"pip 阶段异常: {e}")
                self._last_install_report = "\n".join(report_lines)
                return f"[INSTALL_FAIL] 依赖安装异常: {e}"
        elif not self.pip_install_requirements:
            report_lines.append("配置已关闭 pip_install_requirements，跳过依赖安装。")
        else:
            report_lines.append("无 requirements.txt，跳过依赖安装。")

        # 6. 热重载：先定向重载，失败再全量重载
        reload_success = False
        reload_errors = []
        if not self.auto_reload_after_install:
            report_lines.append("配置已关闭 auto_reload_after_install，跳过热重载。")
            self._last_install_report = "\n".join(report_lines)
            return (
                "[INSTALL_PARTIAL] 代码已下载并可在重启后显示。"
                "\n当前配置关闭了自动热重载，请手动执行 /plugin reload 或重启 AstrBot。"
                "\n如需审计明细，可发送 /查看安装日志"
            )

        try:
            if hasattr(self.context, "_star_manager"):
                await event.send(event.plain_result("🔄 正在刷新插件列表..."))
                manager = self.context._star_manager

                try:
                    result = await manager.reload(repo_name)
                    reload_success, reload_err = self._parse_reload_result(result)
                    report_lines.append(f"reload({repo_name}) 结果: {result}")
                    if not reload_success and reload_err:
                        reload_errors.append(reload_err)
                except Exception as e:
                    reload_errors.append(f"reload({repo_name}) 异常: {e}")
                    report_lines.append(f"reload({repo_name}) 异常: {e}")

                if not reload_success and self.full_reload_fallback:
                    try:
                        result = await manager.reload()
                        reload_success, reload_err = self._parse_reload_result(result)
                        report_lines.append(f"reload() 结果: {result}")
                        if not reload_success and reload_err:
                            reload_errors.append(reload_err)
                    except Exception as e:
                        reload_errors.append(f"reload() 异常: {e}")
                        report_lines.append(f"reload() 异常: {e}")
                elif not reload_success:
                    report_lines.append("已禁用 full_reload_fallback，跳过全量重载。")

                if reload_success:
                    report_lines.append("安装与热重载成功。")
                    self._last_install_report = "\n".join(report_lines)
                    return (
                        "[INSTALL_OK] 已真实执行 git/pip 命令并完成热重载。"
                        f"\n插件: {target_data.get('display_name', target_key)}"
                        f"\n目录: {target_dir}"
                        "\n如需审计明细，可发送 /查看安装日志"
                    )

                report_lines.append("安装完成但热重载失败。")
                self._last_install_report = "\n".join(report_lines)
                return (
                    "[INSTALL_PARTIAL] 代码已下载，但热重载失败。"
                    f"\n错误: {self._shorten('; '.join(reload_errors))}"
                    "\n请手动执行 /plugin reload 后在 WebUI 查看。"
                    "\n如需审计明细，可发送 /查看安装日志"
                )
            else:
                report_lines.append("当前版本未暴露 _star_manager。")
                self._last_install_report = "\n".join(report_lines)
                return (
                    "[INSTALL_PARTIAL] 代码已下载，但当前版本不支持静默热重载。"
                    "\n请手动执行 /plugin reload 后在 WebUI 查看。"
                )
        except Exception as e:
            report_lines.append(f"热重载阶段异常: {e}")
            self._last_install_report = "\n".join(report_lines)
            return f"[INSTALL_PARTIAL] 下载完成，但应用刷新时出错: {e}"

    @command("查看安装日志")
    async def show_install_log(self, event: AstrMessageEvent):
        """查看最近一次安装流程的详细日志。"""
        yield event.plain_result(self._shorten(self._last_install_report, limit=3800))

    @command("查看插件配置")
    async def show_plugin_config(self, event: AstrMessageEvent):
        """查看当前插件运行时配置（来自 _conf_schema.json）。"""
        info = (
            f"market_api_url: {self.market_api_url}\n"
            f"git_bin: {self.git_bin}\n"
            f"git_timeout_sec: {self.git_timeout_sec}\n"
            f"pip_install_requirements: {self.pip_install_requirements}\n"
            f"pip_timeout_sec: {self.pip_timeout_sec}\n"
            f"auto_reload_after_install: {self.auto_reload_after_install}\n"
            f"full_reload_fallback: {self.full_reload_fallback}\n"
            f"recover_non_git_dir: {self.recover_non_git_dir}"
        )
        yield event.plain_result(info)

    @command("直接安装插件")
    async def cmd_direct_install(self, event: AstrMessageEvent, plugin_keyword: str):
        """
        通过命令直接强制安装：/直接安装插件 <插件名>
        """
        yield event.plain_result(f"执行直接安装命令: {plugin_keyword}...")
        result = await self.install_plugin_tool(event, plugin_keyword, True)
        yield event.plain_result(result)
