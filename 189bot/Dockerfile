# 使用 Python 3.11 Slim 版本作为基础镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 复制依赖文件和应用文件
COPY requirements.txt .
COPY . /app

# 安装必要的系统库和 Python 依赖
# libsqlite3-dev 用于确保 Python 的 sqlite3 模块编译完整
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        libc6-dev \
        libsqlite3-dev \
        netcat-openbsd \
    # 安装 Python 依赖
    && pip install --no-cache-dir -r requirements.txt \
    # 清理不必要的系统文件
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# 暴露 Flask 默认端口
EXPOSE 5000

# 容器启动时运行 Flask 应用
CMD ["python", "app.py"]
