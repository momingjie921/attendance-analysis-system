# Attendance Analysis System

基于 Flask + SQLAlchemy 的考勤管理与分析系统，支持多角色登录、考勤导入、异常分析、请假管理和数据备份恢复。

## 技术栈

- Python 3.12
- Flask
- SQLAlchemy
- MySQL 5.7+
- Pandas
- ECharts

## 项目结构

- `app.py`: 应用入口与路由注册
- `api/`: 业务接口（导入、备份、统计、管理）
- `models/`: 数据模型定义
- `utils/`: 工具函数与通用装饰器
- `templates/`: 页面模板
- `static/`: 静态资源
- `config/`: 数据库与配置初始化

## 快速开始

1. 安装依赖

```bash
pip install -r requirements.txt
```

2. 配置环境变量（在项目根目录创建 `.env`）

```env
SECRET_KEY=replace-with-a-strong-random-string
DATABASE_URI=mysql+pymysql://username:password@localhost:3306/attendance_system
CORS_ORIGINS=http://localhost:5000,http://127.0.0.1:5000
ENABLE_DEMO_DATA=false
FLASK_DEBUG=False
HOST=0.0.0.0
PORT=5000
```

3. 启动

```bash
python app.py
```

访问地址：`http://localhost:5000`

## 安全说明

- 必须配置 `SECRET_KEY`，不要使用弱密钥。
- 生产环境请设置 `FLASK_DEBUG=False`。
- `CORS_ORIGINS` 仅填写可信前端域名，不要使用开放通配配置。
- 生产环境建议保持 `ENABLE_DEMO_DATA=false`，避免自动创建演示账号。
- 导入、备份、恢复、删除接口属于高权限操作，建议只对管理员/经理开放并配合审计日志。
- 备份文件包含敏感数据（含用户密码哈希），请妥善保存并限制访问权限。

## 默认演示账号

系统初始化会创建演示账号（用于本地演示）：

- `admin / admin123`
- `tech_manager / manager123`
- `zhangsan / employee123`

首次部署后请立即修改默认密码，或在初始化逻辑中移除演示账号。
