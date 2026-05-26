# 运行与测试指南（Windows + MySQL）

本文档用于从零开始初始化数据库、运行系统并完成基础测试与安全验证。

## 1. 环境准备

- Python 3.12
- MySQL 8.x
- 项目目录：`D:\attendance-analysis-system`

## 2. 创建数据库

```sql
CREATE DATABASE attendance_system
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

## 3. 导入结构与模拟数据

按顺序执行：

```bash
mysql -u root -p attendance_system < attendance_system.sql
mysql -u root -p attendance_system < attendance_seed_medium_enterprise.sql
```

## 4. 创建虚拟环境并安装依赖

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 5. 配置环境变量

在项目根目录创建 `.env`，示例：

```env
SECRET_KEY=replace-with-strong-random-secret
DATABASE_URI=mysql+pymysql://root:你的密码@127.0.0.1:3306/attendance_system
HOST=0.0.0.0
PORT=5000
FLASK_DEBUG=False
SESSION_COOKIE_SECURE=False
CORS_ORIGINS=http://127.0.0.1:5000,http://localhost:5000
API_CSRF_PROTECT=True
ENABLE_DEMO_DATA=False
```

## 6. 启动系统

```bash
python app.py
```

浏览器访问：`http://127.0.0.1:5000`

## 7. 基础功能测试

建议按以下顺序：

1. 仪表盘加载是否正常
2. 员工管理分页、筛选是否正常
3. 考勤列表查询（按月）是否正常
4. 请假申请与审批流程是否闭环
5. 备份创建/下载/删除是否正常

## 8. 安全测试

1. 写接口请求应自动带 `X-CSRF-Token`
2. 手工移除 `X-CSRF-Token` 再请求写接口，应返回 403
3. 普通员工访问管理员接口，应返回 403
4. 弱密码（如 `123456`）应被拒绝

## 9. 自动化回归测试

```bash
python -m unittest discover -s tests -p "test_*.py"
```

预期输出：`OK`

## 10. 灰度前核查

上线前请逐项对照：

- `docs/PRODUCTION_CHECKLIST.md`
- HTTPS、数据库最小权限、备份与恢复演练、日志轮转
