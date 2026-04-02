# Changelog

所有对本项目的显著变更都会记录在此。


## v1.1.23 - 2026-04-02

- 增强自动重载管理器兼容：新增 context._star_manager 与类级 _star_manager 回退
- 补充嵌套上下文路径检测（context/_context/core_lifecycle）提升管理器发现率
- 兼容同步/异步 reload 调用，避免因调用形态差异导致热重载失败
## v1.1.22 - 2026-04-02

- 修复 agent 调用工具传参被过度过滤的问题：搜索关键词增加宽松回退策略
- 修复安装参数提取：plugin_name 允许普通文本回退并交由服务层匹配
- 恢复 llm_tool 的 Args 风格文档并明确 has_user_confirmed 类型，提升参数识别稳定性
## v1.1.21 - 2026-04-02

- 修复发布脚本：提交前自动清理 __pycache__，防止缓存文件被误提交
- 新增 .gitignore 忽略 __pycache__/ 与 *.pyc
- 清理上一版误入库的 __pycache__ 缓存文件
## v1.1.20 - 2026-04-02

- 修复 search_astrbot_plugin 参数提取：支持 kwargs 深层结构和嵌套 JSON
- 新增搜索关键词事件文本兜底，降低参数丢失时的失败概率
- 修复递归提取会污染键名的问题：仅提取值并过滤保留字段
- 同步加固 plugin_name 提取在嵌套结构下的稳定性
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
