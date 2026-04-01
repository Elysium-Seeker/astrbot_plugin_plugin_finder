<div align="center">

# AstrBot Plugin Finder
  
![Moe Counter](https://count.getloli.com/get/@astrbot_plugin_plugin_finder?theme=booru-helltaker)

[![AstrBot](https://img.shields.io/badge/AstrBot-Plugin-blue)](https://github.com/AstrBotDevs/AstrBot)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

</div>

基于 LLM 函数调用（Function Calling）的**全自然语言对话式插件管家**！彻底告别打开终端、手动 Clone、敲黑框敲依赖的时代！

## 🆕 最近更新

- `v1.1.13`：新增“已安装跳过”机制：目标插件目录已存在且包含 `metadata.yaml` 时，不再重复执行 clone/pull/pip，直接返回 `[INSTALL_SKIPPED]`。
- `v1.1.12`：针对 `install_astrbot_plugin` 60 秒超时优化：移除安装前重复的 `git ls-remote` 探测、`git clone` 改为浅克隆（`--depth 1 --single-branch --no-tags`）、安装锁占用时改为快速失败并提示重试（避免排队超时）。
- `v1.1.11`：修复自动安装工具 `handler parameter mismatch`：补齐 llm_tool 标准 Args 参数定义，安装与搜索工具改为缺参/别名参数兼容解析（避免模型侧参数名偏差导致调用失败）。
- `v1.1.10`：继续根据最新评论加固：入口与服务层统一透传 `asyncio.CancelledError`、高风险命令增加管理员权限、配置展示不再泄露确认词、`git_bin` 与超时配置增加安全边界、安装锁缩小到本地变更阶段并新增 requirements 安全策略校验。
- `v1.1.9`：修复最新评论问题：为关键入口补异常兜底、搜索结果改为稳定 JSON 输出、布尔配置解析回退语义修正、仓库 URL 规范化支持 ssh/git 形态、安装报告写入统一受锁保护，并移除对私有 `_star_manager` 的依赖。
- `v1.1.8`：根据最新 issue 审核意见追加加固：移除导入回退劫持风险、market API 域名白名单约束、已有仓库 origin 校验、依赖自动安装默认关闭并增加插件白名单、命令参数规范化与数据结构健壮性修复。
- `v1.1.7`：彻底拆分主流程，核心安装逻辑迁移到独立模块；安装阶段改为仅允许唯一精确匹配，模糊匹配只返回候选，避免误装。
- `v1.1.6`：根据 issue 审核要求补齐安全与可观测性修复：增加仓库域名白名单、仓库名与目录边界校验、命令不存在兜底日志、直接安装确认词保护。
- `v1.1.5`：重构安装主流程，拆分为多个私有阶段方法，在不改变现有安装行为的前提下提升可读性与可维护性。

## ✨ 特性

- 🔍 **官方白名单校验**：对接官方 `https://plugins.astrbot.app/` 市场 API，只允许安装市场内列出的插件，防止潜在的恶意挂马仓库。
- 📦 **可控依赖托管**：可按配置识别并安装 `requirements.txt`，默认关闭自动安装，并支持按插件白名单启用。
- 🔄 **自动热重载生效**：支持利用 AstrBot 底层原生 `star_manager` 在内存中做到全程静默热重载替换（需框架版本较新），亦或是智能引导用户发送系统命令，**安装即用**。
- 🤖 **原生自然语言交互**：直接与 Bot 交流“我想装个天气的插件”、“有没有什么好玩的插件”等，大模型会自动搜索、匹配、推荐并征求您同意后再调用安装程序。同时支持传统的强制命令模式。

## 🚀 使用方法

### 方式一：自然语言交互（推荐）
得益于工具调用能力（LLM Tool Calling），您可以直接向机器人提出您的需求：
1. **用户**：`bot，我想装一个看天气的插件。`
2. **机器人**：`为您找到了这款 astrbot_plugin_weather 天气插件... 是否需要为您现在安装？`
3. **用户**：`是的，安装吧`
4. **机器人**：`⏳ 收到确认，开始为您安装插件：astrbot_plugin_weather... 
安装完成且后台热重载已生效！`

### 方式二：跳过确认，直接命令安装
如果您非常明确要安装的具体插件也可以：
```text
/直接安装插件 <插件名或关键字> <确认词>
```

该命令仅管理员可用，且默认禁用（`direct_install_confirm_phrase` 为空）。
请先在配置中设置一个高强度确认词，再使用，例如：

```text
/直接安装插件 astrbot_plugin_weather 9d7f!MySecurePhrase
```

## 💬 常见问题

**Q: 为什么没有自动安装 requirements.txt？**
A: 出于供应链安全考虑，`pip_install_requirements` 默认关闭。即使开启，也只有在 `trusted_requirements_plugins` 白名单内的插件才会自动安装依赖。

**Q: 只有管理员能执行这个命令吗？**
A: `直接安装插件` 和 `查看插件配置` 已内置管理员权限校验；自然语言检索/安装工具仍按对话链路工作，但安装动作仍要求显式确认。

**Q: 为什么提示 Git 下载失败？**
A: 宿主机中必须已安装全局变量可调用的 `git` 命令。

## 📜 协议
MIT License
