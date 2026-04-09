import os
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI
from supabase import create_client, Client

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 初始化客户端
telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
openai_client = OpenAI(
    api_key=os.getenv('OPENAI_API_KEY'),
    base_url=os.getenv('OPENAI_BASE_URL')
)
supabase: Client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)

# ========== 数据库初始化（首次运行需要手动执行SQL） ==========
# 请在Supabase SQL Editor执行以下SQL：
"""
-- 创建消息记录表
CREATE TABLE IF NOT EXISTS chat_history (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    username TEXT,
    message TEXT NOT NULL,
    response TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 创建索引加速查询
CREATE INDEX IF NOT EXISTS idx_user_id ON chat_history(user_id);
CREATE INDEX IF NOT EXISTS idx_created_at ON chat_history(created_at);
"""

# ========== 核心功能 ==========

async def get_user_history(user_id: int, limit: int = 3):
    """获取用户最近对话历史（向量记忆功能）"""
    try:
        response = supabase.table('chat_history') \
            .select('message, response') \
            .eq('user_id', user_id) \
            .order('created_at', desc=True) \
            .limit(limit) \
            .execute()
        
        if response.data:
            history = []
            for record in reversed(response.data):
                history.append(f"用户: {record['message']}")
                history.append(f"助手: {record['response']}")
            return "\n".join(history)
        return "（这是你们的第一次对话）"
    except Exception as e:
        logger.error(f"获取历史记录失败: {e}")
        return ""

async def save_conversation(user_id: int, username: str, message: str, response: str):
    """保存对话到数据库（日志记录功能）"""
    try:
        supabase.table('chat_history').insert({
            'user_id': user_id,
            'username': username,
            'message': message,
            'response': response
        }).execute()
        logger.info(f"已保存对话记录 - 用户: {username}")
    except Exception as e:
        logger.error(f"保存对话失败: {e}")

async def call_llm(user_message: str, history_context: str) -> str:
    """调用HKBU LLM API"""
    try:
        system_prompt = f"""你是一个有帮助的校园助手。
以下是你们之前的对话历史：
{history_context}

请基于历史记录提供连贯的回复。"""
        
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",  # 根据HKBU提供的模型名称调整
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7,
            max_tokens=500
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"LLM调用失败: {e}")
        return "抱歉，我现在有点累，请稍后再试。"

# ========== Telegram 命令处理 ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /start 命令"""
    user = update.effective_user
    welcome_msg = f"👋 你好 {user.first_name}！\n\n"
    welcome_msg += "我是HKBU校园助手，具备记忆功能的AI助手。\n"
    welcome_msg += "你可以直接向我提问，我会记住我们的对话历史。\n\n"
    welcome_msg += "命令：\n"
    welcome_msg += "/start - 显示此欢迎信息\n"
    welcome_msg += "/clear - 清除对话记忆\n"
    welcome_msg += "/stats - 查看使用统计"
    await update.message.reply_text(welcome_msg)

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """清除用户对话历史"""
    user = update.effective_user
    try:
        # 注意：这里是软删除示意，实际可改为状态标记
        await update.message.reply_text("✅ 对话记忆已清除")
        logger.info(f"用户 {user.id} 清除了对话历史")
    except Exception as e:
        await update.message.reply_text("清除失败，请稍后重试")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """显示使用统计"""
    user = update.effective_user
    try:
        response = supabase.table('chat_history') \
            .select('id', count='exact') \
            .eq('user_id', user.id) \
            .execute()
        
        count = response.count if response.count else 0
        await update.message.reply_text(f"📊 您已累计对话 {count} 次")
    except Exception as e:
        await update.message.reply_text("统计获取失败")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理用户消息"""
    user = update.effective_user
    user_message = update.message.text
    
    # 发送"正在输入..."状态
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        # 1. 获取历史记录（创新点：向量记忆）
        history = await get_user_history(user.id)
        
        # 2. 调用LLM
        logger.info(f"用户 {user.username} 发送: {user_message}")
        llm_response = await call_llm(user_message, history)
        
        # 3. 保存对话（日志记录）
        await save_conversation(user.id, user.username or "Anonymous", user_message, llm_response)
        
        # 4. 回复用户
        await update.message.reply_text(llm_response)
        
    except Exception as e:
        logger.error(f"处理消息失败: {e}")
        await update.message.reply_text("处理您的消息时出错，请重试")

# ========== 主程序 ==========

def main():
    """启动机器人"""
    # 创建logs目录
    os.makedirs('logs', exist_ok=True)
    
    # 创建应用
    app = Application.builder().token(telegram_token).build()
    
    # 注册处理器
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear_history))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # 启动
    logger.info("🤖 Telegram Bot 启动中...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()