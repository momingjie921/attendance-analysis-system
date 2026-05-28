# 常见问题排查

## 中文显示异常

数据库和连接均应使用 `utf8mb4`。MySQL 8.0 推荐：

```sql
SHOW VARIABLES LIKE 'character_set%';
SHOW VARIABLES LIKE 'collation%';
```

如果终端显示乱码，优先确认文件本身为 UTF-8，再检查终端编码。GitHub 可正常显示 UTF-8 文档。

如果页面中的员工姓名、部门名称或图表标签显示为 `???`，通常不是前端编码问题，而是数据库中已经写入了问号占位数据。常见原因是曾经导入过旧版种子数据，或通过不支持 UTF-8 的终端方式生成 / 导入了数据。

可以先检查数据库原始值：

```sql
SELECT dept_id, dept_name FROM department LIMIT 5;
SELECT emp_id, emp_name FROM employee LIMIT 5;
```

如果查询结果本身就是 `???`，请备份当前数据库后，重新导入最新版 `attendance_seed_medium_enterprise.sql`。最新版种子脚本使用中文虚拟部门、中文虚拟员工姓名、中文节假日和中文异常说明，适合国内演示和测试。

## 数据库连接失败

检查 `.env` 中的连接串：

```env
DATABASE_URI=mysql+pymysql://attendance_user:your_password@127.0.0.1:3306/attendance_system
```

常见原因：

- MySQL 服务未启动
- 数据库名不存在
- 用户名或密码错误
- 数据库用户没有访问权限
- 本机端口不是 3306

如果启动时报下面类似错误：

```text
Access denied for user 'root'@'localhost' (using password: YES)
```

通常说明 `.env` 没有创建，或 `DATABASE_URI` 中的用户名、密码和本机 MySQL 不一致。先用 MySQL 客户端验证账号：

```powershell
mysql -u root -p attendance_system
```

确认能登录后，再把 `.env` 中的连接串改成同一组账号密码，例如：

```env
DATABASE_URI=mysql+pymysql://root:你的MySQL密码@127.0.0.1:3306/attendance_system
```

注意不要把真实密码写入 `.env.example`、`.env.production.example` 或提交到 GitHub。

## SQL 导入失败

先确认数据库为空或已备份。结构脚本和数据脚本需要按顺序导入：

```powershell
mysql -u root -p attendance_system < attendance_system.sql
mysql -u root -p attendance_system < attendance_seed_medium_enterprise.sql
```

如果提示排序规则不支持，说明 MySQL 版本较低，可创建数据库时使用 `utf8mb4_unicode_ci`。

## 登录或提交接口失败

检查：

- 是否正确登录
- 浏览器 Cookie 是否被禁用
- `.env` 中 `SECRET_KEY` 是否发生过变化
- 生产环境是否正确配置 HTTPS 和安全 Cookie
- 前端请求是否携带 CSRF 令牌

## 新增员工失败

系统会拒绝弱密码。建议初始密码至少包含大小写字母和数字，例如 `TempPass123`，并要求员工首次登录后修改。

## 图表没有数据

检查是否导入了虚拟数据或真实考勤数据：

```sql
SELECT COUNT(*) FROM attendance_record;
SELECT COUNT(*) FROM abnormal_attendance;
```

如果表中有数据但页面为空，检查浏览器控制台和后端日志中的接口错误。

## 生产环境不能启动 Debug

生产环境必须设置：

```env
FLASK_DEBUG=False
```

Debug 模式只允许本地开发使用。
