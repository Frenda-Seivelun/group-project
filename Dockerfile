FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY bot.py .

RUN mkdir -p /app/logs

# 运行机器人
CMD ["python", "bot.py"]