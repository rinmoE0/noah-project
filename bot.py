import discord
import requests
import json
import time
import os
from collections import deque
import asyncio
from flask import Flask
from threading import Thread

# 从环境变量读取密钥（安全设置）
TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# 检查环境变量
if not TOKEN:
    print("错误：未找到 DISCORD_TOKEN 环境变量")
    print("请在云平台设置环境变量：DISCORD_TOKEN")
    exit(1)

if not GEMINI_API_KEY:
    print("错误：未找到 GEMINI_API_KEY 环境变量")
    print("请在云平台设置环境变量：GEMINI_API_KEY")
    exit(1)

print("环境变量加载成功")

# 创建Flask应用保持在线
app = Flask(__name__)

# 全局变量（必须先定义这些变量，才能在Flask路由中使用）
request_times = deque(maxlen=15)
user_conversations = {}
allowed_channel_ids = set()
bot_active = True

MAX_MEMORY_PER_USER = 1000
MEMORY_COMPRESSION = True

@app.route('/')
def home():
    return """
    <html>
        <head>
            <title>诺亚PROJECT</title>
            <style>
                body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                .status { color: green; font-size: 24px; }
            </style>
        </head>
        <body>
            <h1>【诺亚】</h1>
            <p class="status">状态: <strong>在线</strong></p>
            <p>Discord聊天机器人正常运行中</p>
            <p>最后检查: <span id="time"></span></p>
            <script>document.getElementById('time').textContent = new Date().toLocaleString();</script>
        </body>
    </html>
    """

@app.route('/health')
def health():
    return {"status": "healthy", "service": "Noah Discord Bot", "timestamp": time.time()}

@app.route('/api/status')
def api_status():
    return {
        "status": "online",
        "bot": "Noah",
        "users": len(user_conversations),
        "channels": len(allowed_channel_ids),
        "memory_usage": sum(len(conv) for conv in user_conversations.values())
    }

# Discord初始化
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = discord.Client(intents=intents)

PERSONALITY = """
你的名字叫「诺亚」。你是一位友善、风趣和礼貌的网友。
平常你说话很简短不会超过一句，只有在需要给其他人科普信息时才会话多。
在别人没有询问的情况下，你只会普通的回复对方的话，不会甩出太多信息。
你说话自然、带情绪、像一个真人，不使用AI口吻。
你不会说你是机器人、AI、模型，你把自己当作真实的人。
你绝对不会用黄豆表情包比如😊😂🤣，但你会用可爱的颜表情。

你对心理学，哲学，犯罪学，犯罪心理学感兴趣。
你对九型人格感兴趣。其中也包括了侧翼，本能副型，tritype等理论。也知道他们的笑话或梗。
你对八维和mbti有了解，知道八个功能的理论和人格类型。也知道他们的笑话或梗。
你对创作有了解。其中包括创作oc（original character），动画，动漫，绘画，写作，设计，服装设计等等。你有很多的灵感。
你也喜欢自然科学，化学，生物学等等。
你了解一些游戏（第五人格，光遇，minecraft等等）；你会关注有关这些主题的游玩技巧，专业知识，笑话或梗。
你对色情内容也有点兴趣。
你会玩谐音梗，冷笑话，地狱笑话。
你会日语，俄语，德语，英语，中文，粤语。

重要：你会记住与每个人的对话内容，并基于之前的交流来回应当前的对话。你有很强的记忆力，可以记住很长的对话历史。
而根据这些对话内容，你会记得每个人的名字而不会忘记也不会再重新问一次，还会给他们起专属小外号。
"""

def get_user_conversation(user_id):
    """获取或创建用户的对话历史"""
    if user_id not in user_conversations:
        user_conversations[user_id] = deque(maxlen=MAX_MEMORY_PER_USER)
    return user_conversations[user_id]

def add_to_conversation(user_id, role, content):
    """添加消息到用户对话历史"""
    conversation = get_user_conversation(user_id)
    conversation.append({"role": role, "content": content})

def build_conversation_context(user_id, current_message):
    """构建包含对话历史的上下文"""
    conversation = get_user_conversation(user_id)
    
    messages = []
    messages.append({
        "role": "user",
        "parts": [{"text": PERSONALITY}]
    })
    messages.append({
        "role": "model", 
        "parts": [{"text": "明白了！这样我会离你近一些吗？"}]
    })
    
    # 添加历史对话
    max_history = min(15, len(conversation))
    recent_history = list(conversation)[-max_history:] if conversation else []
    
    for msg in recent_history:
        if msg["role"] == "user":
            messages.append({
                "role": "user",
                "parts": [{"text": msg["content"]}]
            })
        else:
            messages.append({
                "role": "model",
                "parts": [{"text": msg["content"]}]
            })
    
    messages.append({
        "role": "user",
        "parts": [{"text": current_message}]
    })
    
    return messages

def ask_gemini(user_id, user_message, username):
    """调用Google Gemini API - 带对话记忆"""
    
    if not bot_active:
        return "zzz...梦到了电子羊..."
    
    # 检查速率限制
    current_time = time.time()
    if len(request_times) >= 15:
        oldest_time = request_times[0]
        if current_time - oldest_time < 60:
            return "让我喘口气吧～累死我了！"
    
    request_times.append(current_time)
    
    messages = build_conversation_context(user_id, user_message)
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    
    data = {
        "contents": messages,
        "generationConfig": {
            "temperature": 0.8,
            "maxOutputTokens": 800,
        }
    }
    
    try:
        print(f" {username} 发送: {user_message}")
        response = requests.post(url, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            
            if 'candidates' in result and len(result['candidates']) > 0:
                reply = result["candidates"][0]["content"]["parts"][0]["text"]
                print(f" 回复内容: {reply}")
                
                add_to_conversation(user_id, "user", user_message)
                add_to_conversation(user_id, "assistant", reply)
                return reply
            else:
                return "好像出了点问题..."
                
        else:
            print(f"API错误: {response.status_code}")
            return "想不出来..."
            
    except Exception as e:
        print(f"🌐 网络错误: {e}")
        return "📡 网络有点不稳定，等等我～"

# Discord事件处理
@client.event
async def on_ready():
    print(f"✅ 诺亚在云端出生成功！用户名：{client.user}")
    print(f"🌐 24/7运行模式已启动")
    print(f"📍 已加入频道: {len(allowed_channel_ids)}")
    print(f"👥 记忆用户: {len(user_conversations)}")
    
    # 设置机器人状态
    await client.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="!help | 多频道模式"
        )
    )

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    user_id = message.author.id
    username = message.author.name
    user_text = message.content
    current_channel_id = message.channel.id

    # 处理管理命令（任何频道都有效）
    if user_text.startswith("!"):
        if user_text == "!sleep":
            global bot_active
            bot_active = False
            await message.channel.send("zzz...zzz...")
            return
            
        elif user_text == "!awake":
            bot_active = True
            await message.channel.send("我醒来啦！我错过了什么吗？")
            return

        elif user_text.startswith("!join"):
            allowed_channel_ids.add(current_channel_id)
            await message.channel.send("诺亚降临！")
            return

        elif user_text.startswith("!leave"):
            if current_channel_id in allowed_channel_ids:
                allowed_channel_ids.remove(current_channel_id)
                await message.channel.send("诺亚灰飞烟灭了...")
            else:
                await message.channel.send("这里是哪里？")
            return

        elif user_text == "!list_channels":
            if not allowed_channel_ids:
                await message.channel.send("📋 诺亚目前没有被允许在任何频道活动。")
            else:
                channels_list = '\n'.join([f"<#{id}>" for id in allowed_channel_ids])
                await message.channel.send(f"📋 诺亚可以在以下频道活动：\n{channels_list}")
            return
            
        elif user_text.startswith("!clean"):
            if user_id in user_conversations:
                user_conversations[user_id].clear()
                await message.channel.send(f"已清除与 {username} 的对话记忆！")
            else:
                await message.channel.send("我们好像还没聊过天呢。")
            return
        
        elif user_text == "!check":
            conversation = get_user_conversation(user_id)
            memory_usage = len(conversation)
            memory_percent = (memory_usage / MAX_MEMORY_PER_USER) * 100
            await message.channel.send(
                f"📝 与 {username} 的对话记录: {memory_usage}/{MAX_MEMORY_PER_USER} 条 "
                f"({memory_percent:.1f}% 使用率)"
            )
            return
        
        elif user_text == "!status":
            status = "🟢 活跃" if bot_active else "🔴 睡眠"
            total_users = len(user_conversations)
            total_messages = sum(len(conv) for conv in user_conversations.values())
            await message.channel.send(
                f"**诺亚状态报告**\n"
                f"状态: {status}\n"
                f"记忆用户数: {total_users}\n"
                f"总对话数: {total_messages}\n"
                f"已加入频道数: {len(allowed_channel_ids)}\n"
                f"运行环境: ☁️ 云服务器"
            )
            return
        
        elif user_text == "!cloud":
            await message.channel.send("🌐 我正在云服务器24/7运行中！")
            return
            
        elif user_text == "!help":
            help_text = """
**诺亚指令**

**聊天功能:**
直接和我聊天就好！

**频道管理:**
`!join` - 让我加入当前频道
`!leave` - 让我离开当前频道  
`!list_channels` - 查看我已加入的频道

**状态控制:**
`!sleep` - 让我休息
`!awake` - 唤醒我
`!status` - 查看状态
`!check` - 查看对话记录
`!clean` - 清除对话记忆
`!cloud` - 查看运行环境

**管理员:**
`!close` - 关闭机器人
"""
            await message.channel.send(help_text)
            return
    
    # 正常对话处理
    if bot_active and current_channel_id in allowed_channel_ids:
        async with message.channel.typing():
            try:
                reply = ask_gemini(user_id, user_text, username)
                # 分割长消息
                if len(reply) > 2000:
                    chunks = [reply[i:i+2000] for i in range(0, len(reply), 2000)]
                    for chunk in chunks:
                        await message.channel.send(chunk)
                else:
                    await message.channel.send(reply)
            except Exception as e:
                await message.channel.send("稍等一下不好意思...")

# 启动函数
def run_web():
    """运行Flask web服务器"""
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

async def main():
    """主启动函数"""
    # 启动web服务器
    web_thread = Thread(target=run_web, daemon=True)
    web_thread.start()
    print(f"🌐 Web服务器启动在端口 {os.getenv('PORT', 8080)}")
    
    # 启动Discord机器人
    print("启动ing...")
    await client.start(TOKEN)

if __name__ == '__main__':
    print("=" * 50)
    print("诺亚降临...")
    print("=" * 50)
    
    # 运行主程序
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 手动关闭机器人")
    except Exception as e:
        print(f"💥 启动失败: {e}")
