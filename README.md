<div align="center">

# AstrBot Plugin Finder
  
![Moe Counter](https://count.getloli.com/get/@astrbot_plugin_plugin_finder?theme=booru-helltaker)

[![AstrBot](https://img.shields.io/badge/AstrBot-Plugin-blue)](https://github.com/AstrBotDevs/AstrBot)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

</div>

在对话中自行查询、校验、下载并安装 AstrBot 官方平台插件的**全自动插件管家**！彻底告别打开终端、手动 Clone、敲黑框敲依赖的时代！

## ✨ 特性

- 🔍 **官方白名单校验**：对接官方 `https://plugins.astrbot.app/` 市场 API，只允许安装市场内列出的插件，防止潜在的恶意挂马仓库。
- 📦 **自动依赖托管**：拉取代买后会自动识别目录中的 `requirements.txt` 并在后台通过宿主的 python 可执行文件完成依赖安装。
- 🔄 **自动热重载生效**：支持利用 AstrBot 底层原生 `star_manager` 在内存中做到全程静默热重载替换（需框架版本较新），亦或是智能引导用户发送系统命令，**安装即用**。
- 🤖 **原生对话交互**：通过聊天平台（QQ、微信等）输入指令即可完成整个部署流。

## 📥 安装

由于此插件是帮助你“安装插件”的工具，所以首次部署该插件依然需要在 Web 面板或终端中添加。

### 方式一：克隆（推荐）
在你的 AstrBot `data/plugins/` 目录下执行：
```bash
git clone https://github.com/Elysium-Seeker/astrbot_plugin_plugin_finder.git
```
然后重启 AstrBot 或者使用 Web 面板热重载。

### 方式二：依赖包文件
本插件依赖于 `httpx`，安装时请确保你的 AstrBot 环境中已包含，如没有则执行：
```bash
pip install httpx
```

## 🚀 使用方法

对机器人发送：
```text
/安装插件 <插件名或关键字>
```

**示例演示：**

1. 用户：`/安装插件 网易云`
2. 机器人：`正在官方市场中搜索 [网易云] ...`
3. 机器人：`✅ 找到官方插件：网易云音乐 (astrbot_plugin_cloudmusic) 正在执行下载...`
4. 机器人：`📦 源码下载成功！正在检查依赖(requirements.txt)...`
5. 机器人：`✅ 依赖安装完成！`
6. 机器人：`🎉 热重载触发成功！新插件现已生效。`

## 💬 常见问题

**Q: 只有管理员能执行这个命令吗？**
A: 命令装饰器对接的是原生对话框架。如果希望它只能由管理员操作，推荐使用 AstrBot 自带的权限组功能锁死 `/安装插件` 指令。

**Q: 为什么提示 Git 下载失败？**
A: 宿主机中必须已安装全局变量可调用的 `git` 命令。

## 📜 协议
MIT License
