# 考勤数据分析系统

这是一个基于 Flask、MySQL 和 ECharts 的考勤数据分析系统，适合用于小型企业或中小企业的考勤数据查看、异常分析、请假审批、部门统计和数据导入验证。

> 当前仓库包含结构化建表 SQL 和虚拟中型企业种子数据，可用于本地演示、验收测试和灰度试运行。虚拟数据不包含真实员工隐私信息。

## 功能范围

- 员工、部门、账号和角色管理
- 考勤记录查询、异常识别和统计分析
- 请假申请、审批与记录追踪
- 考勤规则、节假日和系统参数配置
- Excel 数据导入、导出与备份接口
- 登录鉴权、密码强度校验、CSRF 防护和审计日志
- 中型企业模拟数据，便于测试仪表盘和列表页面

## 技术栈

- 后端：Python 3.10+、Flask、SQLAlchemy、PyMySQL
- 数据库：MySQL 8.0+
- 前端：Jinja2、原生 JavaScript、ECharts、Font Awesome
- 测试：unittest

## 目录说明

```text
api/                                   API 蓝图
config/                                数据库与配置
models/                                SQLAlchemy 数据模型
utils/                                 安全、审计、分页、导入等工具
templates/                             页面模板
static/                                静态资源
tests/                                 自动化测试
docs/                                  部署、测试和上线说明
attendance_system.sql                  数据库结构脚本
attendance_seed_medium_enterprise.sql  虚拟中型企业演示数据
```

## 快速启动

1. 创建 MySQL 数据库，推荐字符集和排序规则：

```sql
CREATE DATABASE attendance_system
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_0900_ai_ci;
```

MySQL 5.7 或不支持 `utf8mb4_0900_ai_ci` 时，可使用：

```sql
CREATE DATABASE attendance_system
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;
```

2. 导入结构和虚拟数据：

```powershell
mysql -u root -p attendance_system < attendance_system.sql
mysql -u root -p attendance_system < attendance_seed_medium_enterprise.sql
```

3. 创建本地环境变量文件：

```powershell
copy .env.example .env
```

按本机 MySQL 用户名、密码和端口修改 `.env` 中的 `DATABASE_URI`。生产环境必须替换 `SECRET_KEY`，不要使用示例值。

4. 安装依赖并启动：

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

默认访问地址为 `http://127.0.0.1:5000`。

## 测试账号

虚拟数据中的账号仅用于本地演示和测试。首次进入灰度或生产环境前，应重置全部演示账号密码。

- 管理员：`admin`
- 部门经理：`mgr_2` 至 `mgr_12`
- 普通员工：`u1013` 起

## 文档

- [运行和测试流程](docs/SETUP_AND_TEST_GUIDE.md)
- [生产上线检查清单](docs/PRODUCTION_CHECKLIST.md)
- [常见问题排查](docs/TROUBLESHOOTING.md)
- [更新记录](CHANGELOG.md)

## 上线建议

当前系统经过最小上线改造后，可以用于中小企业灰度试运行，但建议先以只读分析、并行核对、人工复核的方式运行 2 到 4 周。正式替代现有考勤流程前，需要确认考勤规则、异常判定、请假口径、数据备份、权限分配和日志留存均满足企业内部要求。

生产环境请重点完成：

- 使用独立数据库账号，授予最小权限
- 替换所有示例密钥、邮箱授权码和演示账号密码
- 启用 HTTPS、反向代理、CSRF、防火墙和备份策略
- 建立导入前备份、导入后抽样核对和异常复核流程
- 对管理员、经理和员工角色进行权限验收

## 版权与数据说明

仓库中的 SQL 种子数据为虚拟数据，仅用于开发、演示和测试。不要将真实员工数据、真实邮箱授权码、数据库密码或生产配置提交到 GitHub。
