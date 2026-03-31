# 使用官方 Python 3.11 轻量级镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量，防止 Python 生成 .pyc 文件和缓冲输出
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 安装依赖
RUN pip install --no-cache-dir requests

# 复制脚本
COPY update_metadata.py .

# 设置默认命令
CMD ["python", "update_metadata.py"]
