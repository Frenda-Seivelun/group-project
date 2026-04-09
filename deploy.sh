#!/bin/bash

echo "🚀 开始部署 HKBU Telegram Bot"

# 更新系统
sudo apt-get update -y
sudo apt-get install -y docker.io docker-compose

# 添加当前用户到docker组
sudo usermod -aG docker $USER

# 创建项目目录
mkdir -p ~/telegram-bot
cd ~/telegram-bot

# 从GitHub克隆（替换为你的仓库地址）
git clone https://github.com/你的用户名/你的仓库名.git .

# 创建.env文件（你需要手动填入密钥）
cat > .env << EOF
TELEGRAM_BOT_TOKEN=这里填入你的Token
OPENAI_API_KEY=这里填入HKBU的Key
OPENAI_BASE_URL=https://你的HKBU端点
SUPABASE_URL=https://你的项目.supabase.co
SUPABASE_KEY=你的anon key
SUPABASE_SERVICE_KEY=你的service_role key
LOG_LEVEL=INFO
MAX_HISTORY_MESSAGES=3
EOF

echo "⚠️ 请编辑 .env 文件填入正确的密钥："
echo "nano ~/telegram-bot/.env"

# 启动容器
docker-compose up -d --build

echo "✅ 部署完成！"
echo "查看日志：docker-compose logs -f"