from waitress import serve
from app import app
import os

if __name__ == '__main__':
    # 获取端口配置，默认为 80
    port = int(os.environ.get('PORT', 80))
    print(f"Starting Waitress server on 0.0.0.0:{port}...")
    
    # 生产环境使用 Waitress 运行
    # threads 参数控制并发处理线程数，根据服务器性能调整
    serve(app, host='0.0.0.0', port=port, threads=6)
