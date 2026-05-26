# config/database.py
import os
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# 加载.env文件中的环境变量
load_dotenv()

# 初始化SQLAlchemy实例
db = SQLAlchemy()
# 初始化Migrate实例（用于数据库迁移）
migrate = Migrate()


def init_database(app):
    """初始化数据库和迁移工具"""
    # 从环境变量读取数据库连接信息
    db_uri = os.getenv('DATABASE_URI')
    
    # 毕业设计演示：如果缺少环境变量，提供一个默认的提示或连接
    if not db_uri:
        # 你可以设置一个默认的本地开发数据库连接，或者输出更明确的提示
        print("警告: 未检测到环境变量 DATABASE_URI，系统将尝试连接默认本地数据库。")
        db_uri = 'mysql+pymysql://root:root@localhost:3306/attendance_system'
    
    app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
    # 关闭SQLAlchemy的修改跟踪（提升性能）
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # 初始化db和migrate
    db.init_app(app)
    migrate.init_app(app, db)