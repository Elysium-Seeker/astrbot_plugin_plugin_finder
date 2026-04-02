# Changelog

所有对本项目的显著变更都会记录在此。


## v1.1.19 - 2026-04-02

- 加固安装参数读取：支持 kwargs 深层结构与嵌套 JSON 自动提取 plugin_name
- 新增事件文本兜底提取 plugin_name，降低对最近搜索状态的依赖
- 优化插件名为空报错语义，避免误导为强依赖最近搜索记录
- 修正文档中的 release_push.ps1 调用示例为 PowerShell 数组语法
## v1.1.18 - 2026-04-02

- 修复安装阶段 plugin_name 为空时的兜底逻辑：支持最近搜索唯一候选自动补全
- 多候选场景改为 INSTALL_BLOCKED 并返回候选列表，避免误装
- 发布脚本改为 git add -A，避免代码改动漏提交
- 修复 release_push.ps1 在 PowerShell 下的版本解析稳定性
## v1.1.17 - 2026-04-02

- 新增发布准备脚本：自动同步 metadata.yaml 与 main.py 版本，确保 AstrBot 可识别更新
- 新增标准 CHANGELOG.md，并在每次发布时自动写入更新条目
- 新增一键发布脚本 release_push.ps1：自动提交、打 tag、推送
