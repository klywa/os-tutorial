# 一键更新与编写员审核设计（用户已批准）

用户批准：update-sites单命令更新两站；章节局部插入key-value；annotator仅提议现有正文entry新增/修改/删除；管理员逐条改稿/确认/拒绝。提案仅作者和当前admin可见，淡红diff；其余访客只看正式正文。顶栏右侧显示用户名、当前身份及切换，管理员账号可来回切换，test1/aa2025只能annotator。本地默认admin，可切换调试，确认不自动Git推送。

账号配置v2使用schema_version=2和accounts数组（username/password/role），旧users配置兼容admin。迁移保留密钥、已有账号密码，补不存在test1。移除旧users使不理解角色的旧服务回退时鉴权失败而非升权。公网每请求校验账号角色上限及有效身份。

提案SQLite独立持久：公网/var/lib/os-tutorial/proposals.sqlite3，本地raw/proposals.sqlite3，均不进Git/导出。节点稳定ID、基础节点及插入锚点保证逐项审核只应用差量；冲突409，重复审批幂等；可恢复审批journal协调JSON正式保存与审核状态，公网确认后复用Git同步。SQLite使用一致快照备份处理WAL。

一键更新复用万象棋release，Pokilot干净分支检查、备份、ff-only拉取、安装/迁移/basePath构建、启动及健康失败恢复。互斥防重、中文日志、单站选择，失败不撤销另一站已成功更新。不会实际部署/提交开发改动。

用户追加明确双向模式：本地执行publish-local.ps1自动将本地代码与正式笔记提交/合并校验/推送Git，再到服务器执行update-sites；网站只编辑正式笔记，不提供代码修改入口，确认后自动Git；本地执行pull-local.ps1拉取Git并按需构建、恢复原先运行的本地服务。脚本必须识别本项目后安全关闭，不杀其他Python进程，不覆盖本地未提交改动。本地提案/运行数据/密码仍不上传。

用户追加要求部署文档只写执行脚本的命令及最少成功提示，不再列脚本内部实现或长篇手动操作步骤。
