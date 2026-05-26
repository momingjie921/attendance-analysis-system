# 生产部署检查清单

## 1. API 鉴权与 CSRF

- 确保 `API_CSRF_PROTECT=True`
- 前端调用所有 `POST/PUT/PATCH/DELETE /api/*` 接口时，先请求 `GET /api/csrf-token`
- 前端在后续写操作请求头中携带 `X-CSRF-Token: <token>`
- 确保跨域仅允许可信来源（`CORS_ORIGINS`）

## 2. 运维与部署基线

- 全站启用 HTTPS（Nginx/Traefik/Apache 反向代理）
- `SESSION_COOKIE_SECURE=True`
- `FLASK_DEBUG=False`
- `ENABLE_DEMO_DATA=False`
- 数据库使用最小权限账号（不要用 root）
- 备份目录权限最小化，仅运维和服务账号可读写
- 备份文件按周期加密并做异地存储
- 配置日志轮转（按天或按大小）

## 3. 上线前最小回归测试

- 登录成功/失败路径
- 权限越权访问验证（普通员工访问管理员接口应返回 403）
- 导入接口（成功、格式错误、权限不足）
- 备份创建/下载/删除/恢复（至少在测试库演练一次）
- 密码重置与强度校验

## 4. 上线后监控建议

- 监控 4xx/5xx 比例
- 监控数据库连接数与慢查询
- 每日检查审计日志中高风险操作（备份恢复、密码重置）
