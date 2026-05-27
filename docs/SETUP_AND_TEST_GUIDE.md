# 运行和测试流程

本文档用于从空数据库开始搭建、导入虚拟数据、启动系统并完成基础验收测试。

## 1. 环境准备

推荐环境：

- Windows 10/11 或 Linux
- Python 3.10+
- MySQL 8.0+
- Git

进入项目目录：

```powershell
cd D:\attendance-analysis-system
```

创建并启用虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

安装依赖：

```powershell
pip install -r requirements.txt
```

## 2. 创建数据库

MySQL 8.0 推荐：

```sql
CREATE DATABASE attendance_system
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_0900_ai_ci;
```

如果数据库版本不支持 `utf8mb4_0900_ai_ci`，使用：

```sql
CREATE DATABASE attendance_system
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;
```

## 3. 导入 SQL

先导入结构：

```powershell
mysql -u root -p attendance_system < attendance_system.sql
```

再导入虚拟中型企业数据：

```powershell
mysql -u root -p attendance_system < attendance_seed_medium_enterprise.sql
```

导入后可检查核心数据量：

```sql
SELECT COUNT(*) FROM department;
SELECT COUNT(*) FROM employee;
SELECT COUNT(*) FROM attendance_record;
SELECT COUNT(*) FROM user;
```

## 4. 配置环境变量

复制示例文件：

```powershell
copy .env.example .env
```

至少修改：

```env
SECRET_KEY=replace-with-a-long-random-secret
DATABASE_URI=mysql+pymysql://attendance_user:your_password@127.0.0.1:3306/attendance_system
```

本地测试可以先使用本机 MySQL 账号。灰度和生产环境必须使用独立数据库账号，并只授予所需权限。

如果想快速体验内置演示数据，把 `ENABLE_DEMO_DATA` 设为 `true`；如果要导入 `attendance_seed_medium_enterprise.sql`，保持该值为 `false`。SQL 种子账号示例为 `admin / mgr_2 / u1013`，初始密码分别是 `admin123 / manager123 / employee123`。

## 5. 启动系统

```powershell
python app.py
```

浏览器访问：

```text
http://127.0.0.1:5000
```

## 6. 自动化测试

运行单元测试：

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

运行语法检查：

```powershell
python -m py_compile app.py api\backup_api.py api\employee_management_api.py api\import_api.py utils\security.py utils\audit.py utils\file_security.py utils\decorators.py utils\session_auth.py
```

## 7. 手工验收流程

建议按以下顺序测试：

1. 登录管理员账号，确认仪表盘可打开。
2. 查看部门、员工和账号列表，确认分页、搜索和状态筛选正常。
3. 新增一名测试员工，确认弱密码会被拒绝，强密码可以提交。
4. 查看考勤记录和异常记录，确认缺勤、迟到、早退等状态可展示。
5. 查看部门统计页面，确认图表有数据且无前端报错。
6. 提交一条请假申请，再使用管理员账号审批。
7. 导入一份小规模 Excel 测试文件，导入前先备份数据库。
8. 验证数据备份接口或手工数据库备份流程。

## 8. 灰度使用要求

灰度试运行建议持续 2 到 4 周，并满足以下要求后再扩大范围：

- 选择 1 到 2 个部门先试用，不直接替代原考勤系统。
- 每日导入真实考勤副本，不导入唯一原始数据。
- 每周抽样核对迟到、早退、缺勤、请假和加班口径。
- 所有异常结论先由 HR 或管理员人工复核。
- 明确管理员、部门经理、员工三类角色的权限边界。
- 保留导入文件、导入日志、异常处理记录和数据库备份。
- 出现统计口径偏差时，先修规则，再重新计算历史样本。

## 9. 生产前最低要求

系统用于生产前，至少完成：

- 删除或重置全部演示账号密码。
- 替换 `.env` 中所有示例密钥和数据库密码。
- 使用 HTTPS 访问，并配置安全 Cookie。
- 配置数据库自动备份和恢复演练。
- 建立导入失败回滚、异常复核和权限变更流程。
- 对管理员、经理和员工的核心流程完成验收。
