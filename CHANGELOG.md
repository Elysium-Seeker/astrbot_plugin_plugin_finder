# Changelog

所有对本项目的显著变更都会记录在此。


## v1.1.18 - 2026-04-02

- 修复安装阶段 plugin_name 为空时的兜底逻辑：支持最近搜索唯一候选自动补全
- 多候选场景改为 INSTALL_BLOCKED 并返回候选列表，避免误装
- 发布脚本改为 git add -A，避免代码改动漏提交
- 修复 release_push.ps1 在 PowerShell 下的版本解析稳定性
## v1.1.17 - 2026-04-02

- 新增发布准备脚本：自动同步 metadata.yaml 与 main.py 版本，确保 AstrBot 可识别更新
- 新增标准 CHANGELOG.md，并在每次发布时自动写入更新条目
- 新增一键发布脚本 release_push.ps1：自动提交、打 tag、推送
