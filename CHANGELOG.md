# 更新日志

本文档记录项目的重要变更。

## [2026-05-26] 安全与文档修复

### 修复内容

- 修复 `api/employee_management_api.py` 的密码处理逻辑：
  - 修复错误的 `password_hash` 赋值路径。
  - 用户密码更新与重置统一改为 `set_password(...)`。

- 加固 `api/backup_api.py` 的备份文件访问安全：
  - 新增备份文件名与路径校验函数。
  - 恢复、删除、下载接口统一使用安全路径解析，防止路径穿越。

- 增强 `api/import_api.py` 的权限控制：
  - `POST /api/import/analyze` 增加角色鉴权（`admin`、`manager`）。
  - `POST /api/import/attendance` 增加角色鉴权（`admin`、`manager`）。

- 优化 `app.py` 的默认安全配置：
  - 移除固定默认 `SECRET_KEY`。
  - 未配置 `SECRET_KEY` 时，启动时临时生成随机密钥并记录告警日志。
  - CORS 改为从 `CORS_ORIGINS` 读取允许来源白名单。

### 文档变更

- 重写 `README.md`，与当前实现保持一致：
  - 统一运行环境说明。
  - 补充 `.env` 配置示例（含 `CORS_ORIGINS`）。
  - 增加部署与安全注意事项。

### 影响范围

- 账号管理与密码重置流程
- 数据导入接口调用权限
- 备份恢复/下载/删除接口安全性
- 应用启动配置与跨域访问策略
