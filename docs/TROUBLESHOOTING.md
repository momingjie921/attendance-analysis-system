# 常见问题排查

## 中文显示异常

数据库和连接均应使用 `utf8mb4`。MySQL 8.0 推荐：

```sql
SHOW VARIABLES LIKE 'character_set%';
SHOW VARIABLES LIKE 'collation%';
```

如果终端显示乱码，优先确认文件本身为 UTF-8，再检查终端编码。GitHub 可正常显示 UTF-8 文档。

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
