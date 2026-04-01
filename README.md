<div align="center">

# AstrBot Plugin Finder
  
![Moe Counter](https://count.getloli.com/get/@astrbot_plugin_plugin_finder?theme=booru-helltaker)

[![AstrBot](https://img.shields.io/badge/AstrBot-Plugin-blue)](https://github.com/AstrBotDevs/AstrBot)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

</div>

基于 LLM 函数调用（Function Calling）的**全自然语言对话式插件管家**！彻底告别打开终端、手动 Clone、敲黑框敲依赖的时代！

## ✨ 特性

- 🔍 **官方白名单校验**：对接官方 `https://plugins.astrbot.app/` 市场 API，只允许安装市场内列出的插件，防止潜在的恶意挂马仓库。
- 📦 **自动依赖托管**：拉取代买后会自动识别目录中的 `requirements.txt` 并在后台通过宿主的 python 可执行文件完成依赖安装。
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
/直接安装插件 <插件名或关键字>
```

## 💬 常见问题

**Q: 只有管理员能执行这个命令吗？**
A: 命令装饰器对接的是原生对话框架。如果希望它只能由管理员操作，推荐使用 AstrBot 自带的权限组功能锁死 `/安装插件` 指令。

**Q: 为什么提示 Git 下载失败？**
A: 宿主机中必须已安装全局变量可调用的 `git` 命令。

## 📜 协议
MIT License
