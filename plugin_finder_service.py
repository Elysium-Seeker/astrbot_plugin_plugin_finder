import asyncio
import os
import re
import sys
from datetime import datetime
from urllib.parse import urlparse

import httpx
from astrbot.api import logger
from astrbot.api.all import AstrMessageEvent, Context

if __package__:
    from .plugin_finder_config import PluginFinderConfig
else:
    from plugin_finder_config import PluginFinderConfig


class PluginFinderService:
    def __init__(
        self,
        context: Context,
        config: PluginFinderConfig,
        plugins_root: str,
    ):
        self.context = context
        self.config = config
        self.plugins_root = plugins_root
        self._install_lock = asyncio.Lock()
        self._last_install_report = "尚无安装记录。"

    @property
    def direct_install_confirm_phrase(self) -> str:
        return self.config.direct_install_confirm_phrase

    @staticmethod
    def _normalize(name: str) -> str:
        return (name or "").lower().replace("-", "").replace("_", "").replace(" ", "")

    @staticmethod
    def _shorten(text: str, limit: int = 600) -> str:
        if len(text) <= limit:
            return text
        return text[:limit] + " ...[输出过长已截断]"

    @staticmethod
    def _save_report(report_lines: list[str]) -> str:
        return "\n".join(report_lines)

    def _save_and_return(self, report_lines: list[str], message: str) -> str:
        self._last_install_report = self._save_report(report_lines)
        return message

    def get_last_install_report(self, limit: int = 3800) -> str:
        return self._shorten(self._last_install_report, limit=limit)

    def format_runtime_config(self) -> str:
        confirm_phrase_state = "(已设置)" if self.config.direct_install_confirm_phrase else "(未设置，直接安装命令禁用)"
        return (
            f"market_api_url: {self.config.market_api_url}\n"
            f"allowed_market_api_hosts: {', '.join(sorted(self.config.allowed_market_api_hosts))}\n"
            f"git_bin: {self.config.git_bin}\n"
            f"git_timeout_sec: {self.config.git_timeout_sec}\n"
            f"pip_install_requirements: {self.config.pip_install_requirements}\n"
            f"trusted_requirements_plugins: {', '.join(sorted(self.config.trusted_requirements_plugins)) or '(空)'}\n"
            f"pip_timeout_sec: {self.config.pip_timeout_sec}\n"
            f"auto_reload_after_install: {self.config.auto_reload_after_install}\n"
            f"full_reload_fallback: {self.config.full_reload_fallback}\n"
            f"recover_non_git_dir: {self.config.recover_non_git_dir}\n"
            f"allowed_repo_hosts: {', '.join(sorted(self.config.allowed_repo_hosts))}\n"
            f"direct_install_confirm_phrase: {confirm_phrase_state}"
        )

    @staticmethod
    def _iter_market_plugin_items(plugins: dict) -> list[tuple[str, dict]]:
        if not isinstance(plugins, dict):
            logger.warning("市场 API 返回结构异常：顶层不是对象，已忽略。")
            return []

        valid_items: list[tuple[str, dict]] = []
        for key, data in plugins.items():
            if not isinstance(data, dict):
                logger.warning(f"市场项结构异常，已跳过 key={key}")
                continue
            valid_items.append((str(key), data))
        return valid_items

    async def _fetch_market_plugins(self) -> dict:
        """获取官方市场的全部插件数据"""
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(self.config.market_api_url)
                if resp.status_code != 200:
                    logger.warning(
                        f"市场 API 返回异常状态码: {resp.status_code}, url={self.config.market_api_url}"
                    )
                    return {}
                data = resp.json()
                if isinstance(data, dict):
                    return data
                logger.warning("市场 API 返回的 JSON 不是对象类型。")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"拉取市场插件失败: {e}")
            return {}
        return {}

    async def search_plugins(self, search_keyword: str) -> list[dict]:
        search_keyword = (search_keyword or "").strip()
        if not search_keyword:
            return []

        plugins = await self._fetch_market_plugins()
        results = []
        key_lower = search_keyword.lower()
        for key, data in self._iter_market_plugin_items(plugins):
            desc = str(data.get("desc") or "")
            display_name = str(data.get("display_name") or key)
            if (
                key_lower in desc.lower()
                or key_lower in display_name.lower()
                or key_lower in str(key).lower()
            ):
                results.append(
                    {
                        "plugin_name": key,
                        "display_name": display_name,
                        "description": desc,
                        "repo_url": data.get("repo", ""),
                    }
                )

        return results[:5]

    async def _run_cmd(
        self,
        *args: str,
        cwd: str | None = None,
        timeout_sec: int | None = None,
    ) -> tuple[int, str, str]:
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except asyncio.CancelledError:
            raise
        except FileNotFoundError:
            command_name = args[0] if args else ""
            logger.error(f"命令不可用: {command_name}")
            return 127, "", f"命令不存在: {command_name}"
        except Exception as e:
            logger.error(f"启动命令失败: {' '.join(args)}; 错误: {e}")
            return 1, "", f"启动命令失败: {e}"

        timeout_value = timeout_sec if timeout_sec is not None else self.config.git_timeout_sec
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_value,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            logger.warning(f"命令超时: {' '.join(args)}")
            return 124, "", f"命令超时({timeout_value}s): {' '.join(args)}"

        out_text = stdout.decode("utf-8", errors="ignore")
        err_text = stderr.decode("utf-8", errors="ignore")
        return process.returncode, out_text, err_text

    @staticmethod
    def _parse_reload_result(result) -> tuple[bool, str]:
        if isinstance(result, tuple) and len(result) >= 2:
            return bool(result[0]), str(result[1])
        return bool(result), ""

    def _match_plugin_target(
        self,
        plugins: dict,
        plugin_name: str,
    ) -> tuple[str | None, dict | None, list[str]]:
        norm_input = self._normalize(plugin_name)
        exact_matches: list[tuple[str, dict]] = []
        fuzzy_matches: list[tuple[str, dict]] = []

        for key_str, data in self._iter_market_plugin_items(plugins):
            display_name = str(data.get("display_name") or key_str)
            repo_name = str(data.get("repo") or "").rstrip("/").split("/")[-1]

            norm_key = self._normalize(key_str)
            norm_display = self._normalize(display_name)
            norm_repo = self._normalize(repo_name)

            if norm_input in {norm_key, norm_display, norm_repo}:
                exact_matches.append((key_str, data))
            elif norm_input and (
                norm_input in norm_key
                or norm_input in norm_display
                or norm_input in norm_repo
            ):
                fuzzy_matches.append((key_str, data))

        if len(exact_matches) == 1:
            key, data = exact_matches[0]
            return key, data, []

        if len(exact_matches) > 1:
            candidates = [
                f"{k} ({str(d.get('display_name') or k)})" for k, d in exact_matches[:8]
            ]
            return None, None, candidates

        if len(fuzzy_matches) > 0:
            candidates = [
                f"{k} ({str(d.get('display_name') or k)})" for k, d in fuzzy_matches[:8]
            ]
            return None, None, candidates

        return None, None, []

    @staticmethod
    def _normalize_repo_url(repo_url: str) -> str | None:
        repo_url = (repo_url or "").strip()
        if not repo_url:
            return None

        if re.fullmatch(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+(?:\.git)?", repo_url):
            return f"https://github.com/{repo_url}"

        if repo_url.startswith("git@"):
            return repo_url

        parsed = urlparse(repo_url)
        if parsed.scheme in {"http", "https", "ssh", "git"} and parsed.hostname:
            return repo_url

        return None

    @staticmethod
    def _parse_repo_components(repo_url: str) -> tuple[str, str, str] | None:
        repo_url = (repo_url or "").strip()
        if not repo_url:
            return None

        if re.fullmatch(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+(?:\.git)?", repo_url):
            owner, repo = repo_url.split("/", 1)
            host = "github.com"
        elif repo_url.startswith("git@"):
            _, _, ssh_target = repo_url.partition("@")
            host, separator, path = ssh_target.partition(":")
            if not separator:
                return None

            path_segments = [seg for seg in path.split("/") if seg]
            if len(path_segments) != 2:
                return None
            owner, repo = path_segments
        else:
            parsed = urlparse(repo_url)
            if parsed.scheme not in {"http", "https", "ssh", "git"}:
                return None

            host = (parsed.hostname or "").strip().lower()
            path_segments = [seg for seg in (parsed.path or "").split("/") if seg]
            if len(path_segments) != 2:
                return None
            owner, repo = path_segments

        host = host.strip().lower()
        if repo.endswith(".git"):
            repo = repo[:-4]

        if not host or owner in {"", ".", ".."} or repo in {"", ".", ".."}:
            return None
        if not re.fullmatch(r"[a-z0-9.-]+", host):
            return None
        if not re.fullmatch(r"[A-Za-z0-9._-]+", owner):
            return None
        if not re.fullmatch(r"[A-Za-z0-9._-]+", repo):
            return None

        return host, owner, repo

    def _is_allowed_repo_host(self, repo_url: str) -> bool:
        parsed = self._parse_repo_components(repo_url)
        if not parsed:
            return False

        host = parsed[0]
        if host in self.config.allowed_repo_hosts:
            return True
        return any(host.endswith(f".{allowed}") for allowed in self.config.allowed_repo_hosts)

    def _extract_safe_repo_name(self, repo_url: str) -> str | None:
        parsed = self._parse_repo_components(repo_url)
        if not parsed:
            return None

        return parsed[2]

    def _canonical_repo_identity(self, repo_url: str) -> str | None:
        parsed = self._parse_repo_components(repo_url)
        if not parsed:
            return None

        host, owner, repo = parsed
        return f"{host}/{owner.lower()}/{repo.lower()}"

    async def _verify_git_origin(
        self,
        target_dir: str,
        expected_repo_url: str,
        report_lines: list[str],
    ) -> str | None:
        code, out, err = await self._run_cmd(
            self.config.git_bin,
            "config",
            "--get",
            "remote.origin.url",
            cwd=target_dir,
            timeout_sec=self.config.git_timeout_sec,
        )
        report_lines.append(f"git config remote.origin.url 返回码: {code}")
        if code != 0:
            report_lines.append(f"读取 origin 失败: {self._shorten(err)}")
            return "[INSTALL_FAIL] 目标目录的 Git origin 不可读，已阻止在未知仓库上更新。"

        current_origin = (out or "").strip().splitlines()[0] if (out or "").strip() else ""
        report_lines.append(f"当前 origin: {current_origin}")
        expected_id = self._canonical_repo_identity(expected_repo_url)
        current_id = self._canonical_repo_identity(current_origin)
        if not expected_id or not current_id:
            report_lines.append("origin 规范化失败。")
            return "[INSTALL_FAIL] 无法确认目标仓库身份，已阻止更新。"

        if expected_id != current_id:
            report_lines.append(f"origin 不匹配 expected={expected_id}, current={current_id}")
            return "[INSTALL_FAIL] 目标目录仓库来源与待安装插件不一致，已阻止更新。"

        return None

    def _new_install_report(self, plugin_name: str) -> list[str]:
        return [
            f"时间: {datetime.now().isoformat(timespec='seconds')}",
            f"用户输入: {plugin_name}",
            f"插件根目录: {self.plugins_root}",
            f"配置: market_api_url={self.config.market_api_url}, git_bin={self.config.git_bin}",
        ]

    def _resolve_install_target(
        self,
        plugins: dict,
        plugin_name: str,
        report_lines: list[str],
    ) -> tuple[str | None, dict | None, str | None, str | None, str | None, str | None]:
        target_key, target_data, candidates = self._match_plugin_target(
            plugins,
            plugin_name,
        )

        if not target_data:
            if candidates:
                report_lines.append("匹配存在歧义，已阻止自动安装。")
                report_lines.append(f"候选项: {', '.join(candidates)}")
                return (
                    None,
                    None,
                    None,
                    None,
                    None,
                    "[INSTALL_FAIL] 未找到唯一精确匹配，为避免误装已终止。"
                    "\n请使用 search 返回的完整 plugin_name 进行安装。"
                    f"\n候选项: {', '.join(candidates)}",
                )

            report_lines.append("市场匹配失败。")
            return (
                None,
                None,
                None,
                None,
                None,
                f"[INSTALL_FAIL] 安装失败：在市场中未找到名为 {plugin_name} 的合法插件。",
            )

        raw_repo_url = str(target_data.get("repo") or "").strip()
        if not raw_repo_url:
            report_lines.append(f"匹配成功但 repo 为空，插件键: {target_key}")
            return (
                None,
                None,
                None,
                None,
                None,
                f"[INSTALL_FAIL] 安装失败：插件 {target_key} 缺少仓库地址。",
            )

        repo_url = self._normalize_repo_url(raw_repo_url)
        if not repo_url:
            report_lines.append(f"仓库地址格式不支持: {raw_repo_url}")
            return (
                None,
                None,
                None,
                None,
                None,
                "[INSTALL_FAIL] 仓库地址格式不合法，已阻止安装。",
            )

        if not self._is_allowed_repo_host(repo_url):
            report_lines.append(f"仓库域名不在白名单内: {repo_url}")
            return (
                None,
                None,
                None,
                None,
                None,
                "[INSTALL_FAIL] 仓库地址不在可信域名白名单内，已阻止安装。",
            )

        repo_name = self._extract_safe_repo_name(repo_url)
        if not repo_name:
            report_lines.append(f"仓库名不合法: {repo_url}")
            return (
                None,
                None,
                None,
                None,
                None,
                "[INSTALL_FAIL] 仓库地址解析失败或仓库名不安全，已阻止安装。",
            )

        plugins_root_abs = os.path.abspath(self.plugins_root)
        target_dir = os.path.abspath(os.path.join(self.plugins_root, repo_name))
        try:
            if os.path.commonpath([plugins_root_abs, target_dir]) != plugins_root_abs:
                report_lines.append(
                    f"路径越界风险: plugins_root={plugins_root_abs}, target={target_dir}"
                )
                return (
                    None,
                    None,
                    None,
                    None,
                    None,
                    "[INSTALL_FAIL] 插件目录安全校验失败，已阻止安装。",
                )
        except Exception as e:
            report_lines.append(f"目录安全校验异常: {e}")
            return (
                None,
                None,
                None,
                None,
                None,
                "[INSTALL_FAIL] 插件目录安全校验异常，已阻止安装。",
            )

        report_lines.append(f"匹配插件键: {target_key}")
        report_lines.append(f"仓库地址: {repo_url}")
        report_lines.append(f"目标目录: {target_dir}")
        return target_key, target_data, repo_url, repo_name, target_dir, None

    async def _verify_repo_reachable(
        self,
        event: AstrMessageEvent,
        repo_url: str,
        report_lines: list[str],
    ) -> str | None:
        await event.send(event.plain_result(f"🔎 验证仓库可达性: {repo_url}"))
        code, out, err = await self._run_cmd(
            self.config.git_bin,
            "ls-remote",
            repo_url,
            timeout_sec=self.config.git_timeout_sec,
        )
        report_lines.append(f"git ls-remote 返回码: {code}")
        if code != 0:
            report_lines.append(f"git ls-remote 错误: {self._shorten(err)}")
            return f"[INSTALL_FAIL] 无法访问仓库地址，错误信息: {self._shorten(err)}"
        return None

    async def _sync_plugin_repo(
        self,
        event: AstrMessageEvent,
        repo_url: str,
        target_dir: str,
        report_lines: list[str],
    ) -> str | None:
        try:
            if os.path.exists(target_dir) and not os.path.isdir(
                os.path.join(target_dir, ".git")
            ):
                if self.config.recover_non_git_dir:
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
                    return (
                        "[INSTALL_FAIL] 目标目录存在但不是 Git 仓库，无法 pull。"
                        "\n可在配置中开启 recover_non_git_dir 自动恢复。"
                    )

            if os.path.exists(target_dir):
                origin_error = await self._verify_git_origin(target_dir, repo_url, report_lines)
                if origin_error:
                    return origin_error

                await event.send(event.plain_result("📦 目录已存在，执行 git pull 更新..."))
                code, out, err = await self._run_cmd(
                    self.config.git_bin,
                    "pull",
                    cwd=target_dir,
                    timeout_sec=self.config.git_timeout_sec,
                )
                report_lines.append(f"git pull 返回码: {code}")
                if code != 0:
                    report_lines.append(f"git pull 错误: {self._shorten(err)}")
                    return f"[INSTALL_FAIL] git pull 失败: {self._shorten(err)}"
            else:
                await event.send(event.plain_result("📥 目录不存在，执行 git clone..."))
                code, out, err = await self._run_cmd(
                    self.config.git_bin,
                    "clone",
                    "--depth",
                    "1",
                    "--single-branch",
                    "--no-tags",
                    repo_url,
                    target_dir,
                    timeout_sec=self.config.git_timeout_sec,
                )
                report_lines.append(f"git clone 返回码: {code}")
                if code != 0:
                    report_lines.append(f"git clone 错误: {self._shorten(err)}")
                    return f"[INSTALL_FAIL] Git Clone 失败: {self._shorten(err)}"
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Git 阶段异常: {e}")
            report_lines.append(f"Git 阶段异常: {e}")
            return f"[INSTALL_FAIL] 安装中发生本地异常: {e}"

        return None

    def _verify_plugin_structure(
        self,
        target_dir: str,
        report_lines: list[str],
    ) -> str | None:
        if not os.path.isdir(target_dir):
            report_lines.append("目标目录不存在，疑似 clone 未实际落盘。")
            return "[INSTALL_FAIL] 目录校验失败：仓库目录不存在。"

        metadata_file = os.path.join(target_dir, "metadata.yaml")
        report_lines.append(f"metadata.yaml 是否存在: {os.path.exists(metadata_file)}")
        if not os.path.exists(metadata_file):
            return "[INSTALL_FAIL] 插件目录缺少 metadata.yaml，WebUI 不会识别此目录为插件。"

        return None

    async def _install_plugin_requirements(
        self,
        event: AstrMessageEvent,
        target_dir: str,
        plugin_key: str,
        report_lines: list[str],
    ) -> str | None:
        def _scan_requirements_for_policy(path: str) -> tuple[bool, list[str]]:
            pinned_requirement_pattern = re.compile(
                r"^[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?==[^\s;]+(?:\s*;\s*.+)?$"
            )
            violations: list[str] = []
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    for raw_line in f:
                        line = raw_line.strip()
                        if not line or line.startswith("#"):
                            continue
                        lowered = line.lower()
                        if line.startswith("-"):
                            violations.append(line)
                            continue
                        if " @ " in line or lowered.startswith("git+") or "://" in lowered:
                            violations.append(line)
                            continue
                        if not pinned_requirement_pattern.fullmatch(line):
                            violations.append(line)
            except OSError as e:
                return False, [f"读取 requirements.txt 失败: {e}"]

            return len(violations) == 0, violations[:5]

        req_file = os.path.join(target_dir, "requirements.txt")
        if self.config.pip_install_requirements and os.path.exists(req_file):
            if plugin_key not in self.config.trusted_requirements_plugins:
                report_lines.append(
                    "requirements.txt 存在，但该插件不在 trusted_requirements_plugins 白名单，已跳过自动安装。"
                )
                return (
                    "[INSTALL_PARTIAL] 已下载插件代码，但出于供应链安全考虑，"
                    "该插件不在依赖自动安装白名单，已跳过 pip install。"
                    "\n请人工确认后手动安装依赖，并执行 /plugin reload。"
                )

            requirements_safe, violations = _scan_requirements_for_policy(req_file)
            if not requirements_safe:
                report_lines.append(
                    "requirements.txt 未通过安全策略校验: "
                    f"{'; '.join(violations)}"
                )
                return (
                    "[INSTALL_PARTIAL] 已下载插件代码，但 requirements.txt 未通过自动安装安全策略。"
                    "\n当前仅允许固定版本(==)依赖，并禁止 URL/本地路径/额外 index 参数。"
                    "\n请人工审计依赖后手动安装，并执行 /plugin reload。"
                )

            try:
                await event.send(
                    event.plain_result(
                        "⚠ 将安装第三方依赖（来自 requirements.txt），请确认来源可信。"
                    )
                )
                await event.send(event.plain_result("🧩 检测到 requirements.txt，执行 pip install..."))
                code, out, err = await self._run_cmd(
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "-r",
                    "requirements.txt",
                    cwd=target_dir,
                    timeout_sec=self.config.pip_timeout_sec,
                )
                report_lines.append(f"pip install 返回码: {code}")
                if code != 0:
                    report_lines.append(f"pip install 错误: {self._shorten(err)}")
                    return f"[INSTALL_FAIL] 依赖安装失败: {self._shorten(err)}"
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"pip 阶段异常: {e}")
                report_lines.append(f"pip 阶段异常: {e}")
                return f"[INSTALL_FAIL] 依赖安装异常: {e}"
        elif not self.config.pip_install_requirements:
            report_lines.append("配置已关闭 pip_install_requirements，跳过依赖安装。")
        else:
            report_lines.append("无 requirements.txt，跳过依赖安装。")

        return None

    async def _reload_after_install(
        self,
        event: AstrMessageEvent,
        repo_name: str,
        target_dir: str,
        target_key: str,
        target_data: dict,
        report_lines: list[str],
    ) -> str:
        def _resolve_reload_manager():
            for attr in ("star_manager", "plugin_manager"):
                manager_obj = getattr(self.context, attr, None)
                if manager_obj is not None and hasattr(manager_obj, "reload"):
                    return manager_obj, f"context.{attr}"

            return None, ""

        reload_success = False
        reload_errors = []
        if not self.config.auto_reload_after_install:
            report_lines.append("配置已关闭 auto_reload_after_install，跳过热重载。")
            return self._save_and_return(
                report_lines,
                "[INSTALL_PARTIAL] 代码已下载并可在重启后显示。"
                "\n当前配置关闭了自动热重载，请手动执行 /plugin reload 或重启 AstrBot。"
                "\n如需审计明细，可发送 /查看安装日志",
            )

        try:
            manager, manager_source = _resolve_reload_manager()
            if manager is not None:
                report_lines.append(f"重载管理器来源: {manager_source}")
                await event.send(event.plain_result("🔄 正在刷新插件列表..."))

                try:
                    result = await manager.reload(repo_name)
                    reload_success, reload_err = self._parse_reload_result(result)
                    report_lines.append(f"reload({repo_name}) 结果: {result}")
                    if not reload_success and reload_err:
                        reload_errors.append(reload_err)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning(f"定向热重载异常 repo={repo_name}: {e}")
                    reload_errors.append(f"reload({repo_name}) 异常: {e}")
                    report_lines.append(f"reload({repo_name}) 异常: {e}")

                if not reload_success and self.config.full_reload_fallback:
                    try:
                        result = await manager.reload()
                        reload_success, reload_err = self._parse_reload_result(result)
                        report_lines.append(f"reload() 结果: {result}")
                        if not reload_success and reload_err:
                            reload_errors.append(reload_err)
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        logger.warning(f"全量热重载异常: {e}")
                        reload_errors.append(f"reload() 异常: {e}")
                        report_lines.append(f"reload() 异常: {e}")
                elif not reload_success:
                    report_lines.append("已禁用 full_reload_fallback，跳过全量重载。")

                if reload_success:
                    report_lines.append("安装与热重载成功。")
                    return self._save_and_return(
                        report_lines,
                        "[INSTALL_OK] 已真实执行 git/pip 命令并完成热重载。"
                        f"\n插件: {target_data.get('display_name', target_key)}"
                        f"\n目录: {target_dir}"
                        "\n如需审计明细，可发送 /查看安装日志",
                    )

                report_lines.append("安装完成但热重载失败。")
                return self._save_and_return(
                    report_lines,
                    "[INSTALL_PARTIAL] 代码已下载，但热重载失败。"
                    f"\n错误: {self._shorten('; '.join(reload_errors))}"
                    "\n请手动执行 /plugin reload 后在 WebUI 查看。"
                    "\n如需审计明细，可发送 /查看安装日志",
                )

            report_lines.append("当前版本未找到可用重载管理器（公开 API 或兼容回退均不可用）。")
            return self._save_and_return(
                report_lines,
                "[INSTALL_PARTIAL] 代码已下载，但当前版本未找到可用的公开重载管理器。"
                "\n请手动执行 /plugin reload 后在 WebUI 查看。",
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"热重载阶段异常: {e}")
            report_lines.append(f"热重载阶段异常: {e}")
            return self._save_and_return(
                report_lines,
                f"[INSTALL_PARTIAL] 下载完成，但应用刷新时出错: {e}",
            )

    async def install_plugin_tool(
        self,
        event: AstrMessageEvent,
        plugin_name: str,
        has_user_confirmed: bool,
    ) -> str:
        plugin_name = (plugin_name or "").strip()
        if not plugin_name:
            return "[INSTALL_FAIL] 插件名为空，请提供 search 返回的完整 plugin_name。"

        if not has_user_confirmed:
            report_lines = [
                f"时间: {datetime.now().isoformat(timespec='seconds')}",
                f"用户输入: {plugin_name}",
                "用户未确认安装，流程终止。",
            ]
            return self._save_and_return(
                report_lines,
                "[INSTALL_BLOCKED] 执行已被拒绝：请先向用户询问并确认安装，再调用此工具。",
            )

        report_lines = self._new_install_report(plugin_name)

        if self._install_lock.locked():
            report_lines.append("检测到安装互斥锁占用，已快速失败避免工具调用排队超时。")
            return self._save_and_return(
                report_lines,
                "[INSTALL_BUSY] 当前已有安装任务在执行，为避免 60 秒工具超时，本次请求未排队。"
                "\n请等待上一任务完成后重试，或使用 /查看安装日志 查看进度。",
            )

        await event.send(
            event.plain_result(
                f"⏳ 收到确认，开始为您安装插件：{plugin_name}，请稍候..."
            )
        )

        plugins = await self._fetch_market_plugins()
        if not plugins:
            report_lines.append("市场 API 拉取失败或返回为空。")
            return self._save_and_return(
                report_lines,
                "[INSTALL_FAIL] 无法访问官方市场 API，请稍后重试。",
            )

        target_key, target_data, repo_url, repo_name, target_dir, error = self._resolve_install_target(
            plugins,
            plugin_name,
            report_lines,
        )
        if error:
            return self._save_and_return(report_lines, error)

        if (
            target_key is None
            or target_data is None
            or repo_url is None
            or repo_name is None
            or target_dir is None
        ):
            report_lines.append("内部状态异常：安装目标解析结果不完整。")
            return self._save_and_return(
                report_lines,
                "[INSTALL_FAIL] 安装目标解析异常，请稍后重试。",
            )

        async with self._install_lock:
            report_lines.append("已进入安装互斥区：执行 clone/pull、依赖安装和热重载。")

            metadata_file = os.path.join(target_dir, "metadata.yaml")
            if os.path.isdir(target_dir) and os.path.exists(metadata_file):
                if os.path.isdir(os.path.join(target_dir, ".git")):
                    origin_error = await self._verify_git_origin(target_dir, repo_url, report_lines)
                    if origin_error:
                        return self._save_and_return(report_lines, origin_error)

                report_lines.append("检测到插件目录已存在且包含 metadata.yaml，已跳过重复安装。")
                return self._save_and_return(
                    report_lines,
                    "[INSTALL_SKIPPED] 检测到该插件已安装，已跳过重复安装。"
                    f"\n插件: {target_data.get('display_name', target_key)}"
                    f"\n目录: {target_dir}"
                    "\n如需刷新加载状态，请手动执行 /plugin reload。",
                )

            error = await self._sync_plugin_repo(event, repo_url, target_dir, report_lines)
            if error:
                return self._save_and_return(report_lines, error)

            error = self._verify_plugin_structure(target_dir, report_lines)
            if error:
                return self._save_and_return(report_lines, error)

            error = await self._install_plugin_requirements(event, target_dir, target_key, report_lines)
            if error:
                return self._save_and_return(report_lines, error)

            return await self._reload_after_install(
                event,
                repo_name,
                target_dir,
                target_key,
                target_data,
                report_lines,
            )
