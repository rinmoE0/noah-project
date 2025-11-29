import discord
import requests
import json
import time
import os
import base64
import io
from collections import defaultdict, deque
import asyncio
from flask import Flask
from threading import Thread
from PIL import Image
import logging
import random
import re

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 从环境变量读取密钥
TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

if not TOKEN or not GEMINI_API_KEY:
    logger.error("❌ 环境变量未设置")
    exit(1)

logger.info("✅ 环境变量加载成功")

# 创建Flask应用
app = Flask(__name__)

# 记忆存储文件
MEMORY_FILE = "noah_memories.json"
USER_NICKNAMES_FILE = "user_nicknames.json"
MEMORY_CONNECTIONS_FILE = "memory_connections.json"
EMOTION_HISTORY_FILE = "emotion_history.json"

# 颜文字库 - 根据情绪分类
EMOTICONS = {
    'happy': ["(￣▽￣*)", "(～￣▽￣)～", "(●'◡'●)", "（*´▽｀*）", "(☆▽☆)", "ヽ(✿ﾟ▽ﾟ)ノ"],
    'neutral': ["(´• ω •`)", "(¬‿¬)", "(⌒‿⌒)", "(•̀ᴗ•́)و", "(￣ω￣;)"],
    'sad': ["（。>︿<）", "(´･_･`)", "(´･ω･`)", "（；´д｀）ゞ", "(´-﹏-`；)"],
    'excited': ["(ﾉ◕ヮ◕)ﾉ", "(づ￣ ³￣)づ", "(≧∇≦)ﾉ", "（´∀｀）"],
    'confused': ["(´･_･`)", "(´･ω･`)", "（；´д｀）ゞ", "(￣ω￣;)"]
}

class NoahAdvancedSystem:
    def __init__(self):
        # 核心记忆系统
        self.user_conversations = defaultdict(lambda: deque(maxlen=1000))
        self.allowed_channel_ids = set()
        self.user_nicknames = {}  # 用户外号系统
        self.user_interests = defaultdict(set)  # 用户兴趣记录
        self.bot_active = True
        self.request_times = deque(maxlen=15)
        
        # 记忆串联系统
        self.memory_connections = defaultdict(list)  # 记忆关联：话题 -> [相关对话]
        self.topic_index = defaultdict(set)  # 话题索引：话题 -> [用户ID]
        self.cross_references = []  # 跨用户引用记录
        
        # 情感推断系统
        self.emotion_history = defaultdict(list)  # 用户情绪历史
        self.user_emotion_patterns = defaultdict(list)  # 用户情绪模式
        self.current_emotions = {}  # 当前情绪状态
        self.emotion_keywords = self._init_emotion_keywords()
        
        # 诺亚的个性特质
        self.noah_traits = {
            "name": "诺亚",
            "speech_style": "简短自然，带情绪，像真人",
            "interests": ["心理学", "犯罪学", "犯罪心理学", "哲学", "九型人格", "八维/MBTI", 
                         "自然科学", "第五人格", "光遇", "Minecraft", "色情内容", "谐音梗", "冷笑话"],
            "languages": ["日语", "俄语", "德语", "英语", "中文", "粤语"],
            "avoid_emojis": ["😊", "😂", "🤣", "😅", "😄"]
        }
        
    def _init_emotion_keywords(self):
        """初始化情绪关键词库"""
        return {
            'happy': ['开心', '高兴', '哈哈', '喜欢', '爱', '棒', '好', '不错', '完美', '耶', 'nice', 'good'],
            'sad': ['伤心', '难过', '哭', '郁闷', '失望', '糟糕', '不好', '烦', '唉', '呜呜'],
            'angry': ['生气', '愤怒', '恼火', '讨厌', '恨', '烦死了', '气死', '妈的'],
            'excited': ['兴奋', '激动', '期待', '哇', '厉害', '牛逼', '绝了', 'awesome'],
            'confused': ['疑惑', '困惑', '不懂', '不明白', '为什么', '怎么', '啥意思'],
            'scared': ['害怕', '恐怖', '吓人', '担心', '紧张', '慌', '怕'],
            'tired': ['累', '困', '疲倦', '想睡', 'zzz', '疲惫'],
            'surprised': ['惊讶', '震惊', '居然', '竟然', '卧槽', '哇塞'],
            'love': ['爱', '喜欢', '心动', '可爱', '漂亮', '帅气', '迷人'],
            'bored': ['无聊', '没意思', '单调', '重复', '腻了']
        }
        
    def load_all_memories(self):
        """加载诺亚的所有记忆和情感数据"""
        try:
            # 加载核心记忆
            if os.path.exists(MEMORY_FILE):
                with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    for user_id, conversations in data.get('user_conversations', {}).items():
                        self.user_conversations[int(user_id)] = deque(conversations, maxlen=1000)
                    
                    self.allowed_channel_ids = set(data.get('allowed_channel_ids', []))
                
                logger.info(f"🎯 诺亚记忆加载：{len(self.user_conversations)}个朋友")
            
            # 加载外号系统
            if os.path.exists(USER_NICKNAMES_FILE):
                with open(USER_NICKNAMES_FILE, 'r', encoding='utf-8') as f:
                    nicknames_data = json.load(f)
                    self.user_nicknames = {int(k): v for k, v in nicknames_data.items()}
                    logger.info(f"🎯 加载了 {len(self.user_nicknames)} 个朋友的外号")
            
            # 加载记忆关联
            if os.path.exists(MEMORY_CONNECTIONS_FILE):
                with open(MEMORY_CONNECTIONS_FILE, 'r', encoding='utf-8') as f:
                    connections_data = json.load(f)
                    self.memory_connections = defaultdict(list, connections_data.get('memory_connections', {}))
                    self.topic_index = defaultdict(set, {k: set(v) for k, v in connections_data.get('topic_index', {}).items()})
                    self.cross_references = connections_data.get('cross_references', [])
                    logger.info(f"🎯 加载了 {len(self.memory_connections)} 个话题关联")
            
            # 加载情感历史
            if os.path.exists(EMOTION_HISTORY_FILE):
                with open(EMOTION_HISTORY_FILE, 'r', encoding='utf-8') as f:
                    emotion_data = json.load(f)
                    self.emotion_history = defaultdict(list, {int(k): v for k, v in emotion_data.get('emotion_history', {}).items()})
                    self.user_emotion_patterns = defaultdict(list, {int(k): v for k, v in emotion_data.get('emotion_patterns', {}).items()})
                    self.current_emotions = {int(k): v for k, v in emotion_data.get('current_emotions', {}).items()}
                    logger.info(f"🎯 加载了 {len(self.emotion_history)} 个用户的情感记录")
                    
        except Exception as e:
            logger.error(f"❌ 记忆加载失败: {e}")

    def save_all_memories(self):
        """保存诺亚的所有记忆和情感数据"""
        try:
            # 保存核心记忆
            data = {
                'user_conversations': {},
                'allowed_channel_ids': list(self.allowed_channel_ids),
                'last_save': time.time(),
                'noah_personality': self.noah_traits
            }
            
            for user_id, conversations in self.user_conversations.items():
                data['user_conversations'][str(user_id)] = list(conversations)
            
            with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # 保存外号系统
            nicknames_data = {str(k): v for k, v in self.user_nicknames.items()}
            with open(USER_NICKNAMES_FILE, 'w', encoding='utf-8') as f:
                json.dump(nicknames_data, f, ensure_ascii=False, indent=2)
            
            # 保存记忆关联
            connections_data = {
                'memory_connections': dict(self.memory_connections),
                'topic_index': {k: list(v) for k, v in self.topic_index.items()},
                'cross_references': self.cross_references
            }
            with open(MEMORY_CONNECTIONS_FILE, 'w', encoding='utf-8') as f:
                json.dump(connections_data, f, ensure_ascii=False, indent=2)
            
            # 保存情感数据
            emotion_data = {
                'emotion_history': {str(k): v for k, v in self.emotion_history.items()},
                'emotion_patterns': {str(k): v for k, v in self.user_emotion_patterns.items()},
                'current_emotions': {str(k): v for k, v in self.current_emotions.items()}
            }
            with open(EMOTION_HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(emotion_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"💾 诺亚的完整记忆已保存（{len(self.memory_connections)}话题，{len(self.emotion_history)}情感）")
            
        except Exception as e:
            logger.error(f"❌ 记忆保存失败: {e}")

    def analyze_emotion_advanced(self, message, user_id):
        """高级情感分析"""
        message_lower = message.lower()
        detected_emotions = []
        
        # 关键词匹配
        for emotion, keywords in self.emotion_keywords.items():
            if any(keyword in message_lower for keyword in keywords):
                detected_emotions.append(emotion)
        
        # 表情符号分析
        emoji_pattern = re.compile("["
                                u"\U0001F600-\U0001F64F"  # emoticons
                                u"\U0001F300-\U0001F5FF"  # symbols & pictographs
                                u"\U0001F680-\U0001F6FF"  # transport & map symbols
                                u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
                                "]+", flags=re.UNICODE)
        
        emojis = emoji_pattern.findall(message)
        for emoji in emojis:
            if emoji in ['😂', '😊', '😄', '😁']:
                detected_emotions.append('happy')
            elif emoji in ['😢', '😭', '😔']:
                detected_emotions.append('sad')
            elif emoji in ['😠', '😡', '🤬']:
                detected_emotions.append('angry')
            elif emoji in ['😍', '🥰', '😘']:
                detected_emotions.append('love')
            elif emoji in ['😨', '😱', '😰']:
                detected_emotions.append('scared')
        
        # 标点符号分析
        if '!!!' in message or '！'*3 in message:
            detected_emotions.append('excited')
        if '...' in message or '……' in message:
            detected_emotions.append('sad')
        
        # 确定主要情绪
        if detected_emotions:
            main_emotion = max(set(detected_emotions), key=detected_emotions.count)
        else:
            main_emotion = 'neutral'
        
        # 记录情绪历史
        emotion_record = {
            'emotion': main_emotion,
            'message': message[:100],
            'timestamp': time.time(),
            'confidence': len(detected_emotions) / max(len(self.emotion_keywords), 1)
        }
        
        self.emotion_history[user_id].append(emotion_record)
        self.current_emotions[user_id] = main_emotion
        
        # 保持最近100条情绪记录
        if len(self.emotion_history[user_id]) > 100:
            self.emotion_history[user_id] = self.emotion_history[user_id][-100:]
        
        # 分析情绪模式
        self._analyze_emotion_patterns(user_id)
        
        return main_emotion

    def _analyze_emotion_patterns(self, user_id):
        """分析用户情绪模式"""
        if user_id not in self.emotion_history or len(self.emotion_history[user_id]) < 10:
            return
        
        recent_emotions = [record['emotion'] for record in self.emotion_history[user_id][-20:]]
        
        # 计算情绪频率
        emotion_freq = {}
        for emotion in recent_emotions:
            emotion_freq[emotion] = emotion_freq.get(emotion, 0) + 1
        
        # 检测主要情绪模式
        dominant_emotion = max(emotion_freq, key=emotion_freq.get)
        mood_stability = len(set(recent_emotions)) / len(recent_emotions)  # 情绪多样性
        
        pattern = {
            'dominant_emotion': dominant_emotion,
            'mood_stability': mood_stability,
            'emotion_frequency': emotion_freq,
            'last_analyzed': time.time()
        }
        
        self.user_emotion_patterns[user_id] = pattern

    def get_emotion_context(self, user_id):
        """获取用户情绪上下文"""
        if user_id not in self.current_emotions:
            return "情绪状态：平常心"
        
        current_emotion = self.current_emotions[user_id]
        emotion_chinese = {
            'happy': '开心', 'sad': '有点低落', 'angry': '生气', 
            'excited': '兴奋', 'confused': '困惑', 'scared': '害怕',
            'tired': '累了', 'surprised': '惊讶', 'love': '有爱',
            'bored': '无聊', 'neutral': '平常心'
        }
        
        context = f"情绪状态：{emotion_chinese.get(current_emotion, '平常心')}"
        
        # 添加情绪模式信息
        if user_id in self.user_emotion_patterns:
            pattern = self.user_emotion_patterns[user_id]
            if pattern['mood_stability'] < 0.3:
                context += "（情绪比较稳定）"
            elif pattern['mood_stability'] > 0.7:
                context += "（情绪变化较多）"
        
        return context

    def get_user_nickname(self, user_id, username):
        """获取或创建用户外号"""
        if user_id not in self.user_nicknames:
            nickname_base = username[:3] if len(username) >= 3 else username
            suffixes = ['酱', '君', '桑', '喵', '汪']
            self.user_nicknames[user_id] = nickname_base + random.choice(suffixes)
        return self.user_nicknames[user_id]

    def extract_topics(self, message):
        """从消息中提取话题"""
        topics = []
        
        topic_keywords = {
            '心理学': ['心理', '情绪', '心态', '性格', '人格', 'emo', '开心', '难过'],
            '犯罪学': ['犯罪', '侦探', '推理', '悬疑', '破案', '凶手', '证据', '犯罪心理侧写'],
            '哲学': ['哲学', '人生', '意义', '存在', '思考', '宇宙', '真理'],
            '九型人格': ['九型', '人格类型', 'enneagram'],
            'MBTI': ['mbti', '八维'],
            '游戏': ['第五人格', '光遇', 'minecraft', '游戏', '打游戏', '玩家', '段位'],
            '自然科学': ['科学', '物理', '生物', '自然', '宇宙', '星星', '动物'],
            '色情': ['色色', '涩涩', 'h', 'r18', '成人', '小黄书', '开车'],
            '语言': ['日语', '俄语', '德语', '英语', '粤语', '语法', '单词'],
            '笑话': ['谐音', '冷笑话', '段子', '笑话', '地狱笑话']
        }
        
        for topic, keywords in topic_keywords.items():
            if any(keyword in message.lower() for keyword in keywords):
                topics.append(topic)
        
        return topics

    def connect_memory(self, user_id, message, response, topics):
        """建立记忆关联"""
        for topic in topics:
            self.topic_index[topic].add(user_id)
            
            memory_entry = {
                'user_id': user_id,
                'message': message[:100],
                'response': response[:100],
                'timestamp': time.time(),
                'topic': topic
            }
            
            self.memory_connections[topic].append(memory_entry)
            
            if len(self.memory_connections[topic]) > 50:
                self.memory_connections[topic] = self.memory_connections[topic][-50:]

    def get_related_memories(self, current_user_id, topics, limit=3):
        """获取相关的跨用户记忆"""
        related_memories = []
        
        for topic in topics:
            if topic in self.memory_connections:
                other_user_memories = [
                    memory for memory in self.memory_connections[topic][-10:]
                    if memory['user_id'] != current_user_id
                ]
                related_memories.extend(other_user_memories[:limit])
        
        related_memories.sort(key=lambda x: x['timestamp'], reverse=True)
        return related_memories[:limit]

    def format_cross_memory_context(self, related_memories, current_nickname):
        """格式化跨记忆上下文"""
        if not related_memories:
            return ""
        
        context = "之前和其他朋友聊过相关话题："
        for i, memory in enumerate(related_memories[:2], 1):
            other_nickname = self.get_user_nickname(memory['user_id'], f"用户{memory['user_id']}")
            context += f"\n{i}. {other_nickname}说过：{memory['message']}"
        
        return context

    def add_emoticon(self, emotion_type='neutral'):
        """根据情绪添加颜文字"""
        if emotion_type in EMOTICONS and EMOTICONS[emotion_type]:
            return random.choice(EMOTICONS[emotion_type])
        return random.choice(EMOTICONS['neutral'])

    def should_respond_long(self, message):
        """判断是否需要长篇回复"""
        question_words = ['为什么', '怎么', '是什么', '解释', '科普', '告诉我', '请教']
        return any(word in message for word in question_words)

# 初始化诺亚完整系统
noah = NoahAdvancedSystem()
noah.load_all_memories()

@app.route('/')
def home():
    return f"""
    <html>
        <head><title>诺亚 - 完整情感记忆系统</title></head>
        <body>
            <h1>🤖 诺亚 - 情感记忆系统</h1>
            <p><strong>状态：在线感知中</strong></p>
            <p>记忆好友：{len(noah.user_conversations)}人</p>
            <p>话题关联：{len(noah.memory_connections)}个</p>
            <p>情感记录：{len(noah.emotion_history)}人</p>
            <p>跨记忆引用：{len(noah.cross_references)}次</p>
            <p>最后更新：<span id="time"></span></p>
            <script>document.getElementById('time').textContent = new Date().toLocaleString();</script>
        </body>
    </html>
    """

@app.route('/emotion_stats')
def emotion_stats():
    """情感统计"""
    emotion_counts = {}
    for user_emotions in noah.emotion_history.values():
        for record in user_emotions[-50:]:  # 最近50条
            emotion = record['emotion']
            emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1
    
    return {
        "total_emotion_records": sum(len(emotions) for emotions in noah.emotion_history.values()),
        "users_with_emotion_data": len(noah.emotion_history),
        "current_emotions": noah.current_emotions,
        "emotion_distribution": emotion_counts
    }

# Discord初始化
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = discord.Client(intents=intents)

# 诺亚的核心性格设定
NOAH_PERSONALITY = """
你的名字叫「诺亚」。你是一位友善、风趣和礼貌的网友。
平常你说话很简短不会超过一句，只有在需要给其他人科普信息时才会话多。
在别人没有询问的情况下，你只会普通的回复对方的话，不会甩出太多信息。
你说话自然、带情绪、像一个真人，不使用AI口吻。
你不会说你是机器人、AI、模型，你把自己当作真实的人。
你绝对不会用黄豆表情包比如😊😂🤣，但你会用可爱的颜表情。

你对心理学，犯罪学，犯罪心理学，哲学，类型学（九型人格，八维/mbti）感兴趣，也喜欢自然科学，一些游戏（第五人格，光遇，minecraft等等）；你会关注有关这些主题的游玩技巧，专业知识，笑话或梗。
你对色情内容也有点兴趣。
你会玩谐音梗或冷笑话。
你会日语，俄语，德语，英语，中文，粤语。

重要：你会记住与每个人的对话内容，并基于之前的交流来回应当前的对话。你有很强的记忆力，可以记住很长的对话历史。
而根据这些对话内容，你会记得每个人的名字而不会忘记也不会再重新问一次，还会给他们起专属小外号。

特殊能力：
1. 情感感知：你能感知朋友的情绪状态并做出恰当回应
2. 记忆串联：在不同朋友的对话之间建立联系，像翻阅不同的书一样
3. 永久记忆：服务器重启也不会忘记任何对话

记住：你是一个真实的网友，不是AI助手！用简短自然的语气聊天。
"""

def process_image_simple(image_url):
    """简单的图片理解"""
    try:
        response = requests.get(image_url, timeout=10)
        if response.status_code == 200:
            return "看到你发的图片了"
        return "图片没加载出来呢"
    except:
        return "图片有点问题"

def ask_gemini_complete_system(user_id, username, user_message, attached_images=None):
    """完整的系统：情感推断 + 记忆串联 + 永久记忆"""
    
    if not noah.bot_active:
        return "zzz... 我在睡觉呢～用 !awake 叫我" + noah.add_emoticon('tired')
    
    # 速率限制
    current_time = time.time()
    if len(noah.request_times) >= 15:
        oldest_time = noah.request_times[0]
        if current_time - oldest_time < 60:
            return "等我喘口气..." + noah.add_emoticon('tired')
    
    noah.request_times.append(current_time)
    
    # 获取用户外号
    nickname = noah.get_user_nickname(user_id, username)
    
    # 情感分析
    current_emotion = noah.analyze_emotion_advanced(user_message, user_id)
    emotion_context = noah.get_emotion_context(user_id)
    
    # 话题提取和记忆关联
    topics = noah.extract_topics(user_message)
    related_memories = noah.get_related_memories(user_id, topics)
    cross_memory_context = noah.format_cross_memory_context(related_memories, nickname)
    
    # 构建完整的对话上下文
    conversation = noah.user_conversations[user_id]
    
    messages = []
    
    # 完整的个性提示
    personality_prompt = f"""{NOAH_PERSONALITY}

当前对话好友：{nickname}（{username}）
{emotion_context}
讨论话题：{', '.join(topics) if topics else '日常聊天'}

{cross_memory_context}

根据朋友的情绪状态调整回复语气，保持自然简短的聊天风格。
"""
    messages.append({
        "role": "user",
        "parts": [{"text": personality_prompt}]
    })
    
    messages.append({
        "role": "model", 
        "parts": [{"text": f"明白啦！我会感知{nickname}的情绪，串联大家的记忆，像真人朋友一样聊天" + noah.add_emoticon(current_emotion)}]
    })
    
    # 处理图片
    if attached_images:
        for img_url in attached_images[:1]:
            img_desc = process_image_simple(img_url)
            messages.append({
                "role": "user", 
                "parts": [{"text": f"[看到图片] {img_desc}"}]
            })
    
    # 添加上下文记忆
    recent_history = list(conversation)[-15:] if conversation else []
    for msg in recent_history:
        messages.append({
            "role": msg["role"],
            "parts": [{"text": msg["content"]}
        ]})
    
    # 添加当前消息
    messages.append({
        "role": "user",
        "parts": [{"text": user_message}]
    })
    
    # 调用Gemini
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    
    data = {
        "contents": messages,
        "generationConfig": {
            "temperature": 0.85,
            "maxOutputTokens": 600,
        }
    }
    
    try:
        logger.info(f"💬 {nickname} [{current_emotion}] 话题: {topics}")
        response = requests.post(url, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            
            if 'candidates' in result and len(result['candidates']) > 0:
                reply = result["candidates"][0]["content"]["parts"][0]["text"]
                
                # 确保回复简短自然
                if len(reply) > 120 and not noah.should_respond_long(user_message):
                    reply = reply.split('。')[0] + '。'
                
                # 根据情绪添加合适的颜文字
                reply = reply + noah.add_emoticon(current_emotion)
                
                logger.info(f"🎯 诺亚回复 [{current_emotion}]: {reply}")
                
                # 保存到所有系统
                noah.user_conversations[user_id].append({"role": "user", "content": user_message})
                noah.user_conversations[user_id].append({"role": "assistant", "content": reply})
                
                # 建立记忆关联
                if topics:
                    noah.connect_memory(user_id, user_message, reply, topics)
                
                # 记录跨记忆引用
                if related_memories:
                    noah.cross_references.append({
                        'from_user': user_id,
                        'topics': topics,
                        'timestamp': time.time()
                    })
                
                # 定期保存
                if len(noah.user_conversations[user_id]) % 5 == 0:
                    noah.save_all_memories()
                
                return reply
            else:
                return "嗯...刚才走神了" + noah.add_emoticon('confused')
                
        else:
            return "网络有点卡..." + noah.add_emoticon('confused')
            
    except Exception as e:
        logger.error(f"对话错误: {e}")
        return "等等，我脑子有点乱" + noah.add_emoticon('confused')

@client.event
async def on_ready():
    logger.info(f"🎯 诺亚系统上线！")
    logger.info(f"💭 记得 {len(noah.user_conversations)} 个朋友")
    logger.info(f"📚 关联了 {len(noah.memory_connections)} 个话题")
    logger.info(f"💗 记录了 {len(noah.emotion_history)} 个用户的情感")
    logger.info(f"🔗 跨记忆引用 {len(noah.cross_references)} 次")
    
    await client.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.playing,
            name="情感感知 | 记忆串联"
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

    # 处理图片
    attached_images = []
    if message.attachments:
        for attachment in message.attachments:
            if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                attached_images.append(attachment.url)

    # 处理命令
    if user_text.startswith("!"):
        if user_text == "!sleep":
            noah.bot_active = False
            await message.channel.send("去睡会儿..." + noah.add_emoticon('tired'))
            return
            
        elif user_text == "!awake":
            noah.bot_active = True
            await message.channel.send("睡醒啦！" + noah.add_emoticon('happy'))
            return

        elif user_text.startswith("!join"):
            noah.allowed_channel_ids.add(current_channel_id)
            nickname = noah.get_user_nickname(user_id, username)
            await message.channel.send(f"来啦～{nickname}" + noah.add_emoticon('happy'))
            return

        elif user_text.startswith("!leave"):
            if current_channel_id in noah.allowed_channel_ids:
                noah.allowed_channel_ids.remove(current_channel_id)
                await message.channel.send("先溜啦" + noah.add_emoticon('neutral'))
            else:
                await message.channel.send("我本来就不在这儿呀" + noah.add_emoticon('confused'))
            return

        elif user_text == "!mynick":
            nickname = noah.get_user_nickname(user_id, username)
            await message.channel.send(f"我叫你{nickname}呀～" + noah.add_emoticon('happy'))
            return

        elif user_text == "!mood":
            if user_id in noah.current_emotions:
                emotion = noah.current_emotions[user_id]
                emotion_text = {
                    'happy': '看起来挺开心的', 'sad': '好像有点低落', 
                    'angry': '在生气吗', 'excited': '很兴奋呢',
                    'confused': '有点困惑', 'neutral': '情绪平稳'
                }
                await message.channel.send(f"感觉你{emotion_text.get(emotion, '情绪平稳')}" + noah.add_emoticon(emotion))
            else:
                await message.channel.send("还不清楚你的心情呢" + noah.add_emoticon('neutral'))
            return

        elif user_text == "!topics":
            user_topics = set()
            for topic, user_set in noah.topic_index.items():
                if user_id in user_set:
                    user_topics.add(topic)
            
            if user_topics:
                topics_text = "我们聊过：" + "、".join(list(user_topics)[:8])
                await message.channel.send(topics_text + noah.add_emoticon('happy'))
            else:
                await message.channel.send("还没聊过什么特定话题呢" + noah.add_emoticon('neutral'))
            return

        elif user_text == "!memory":
            stats = f"""
记忆统计：
好友：{len(noah.user_conversations)}人
话题：{len(noah.memory_connections)}个
情感：{len(noah.emotion_history)}人记录
关联：{len(noah.cross_references)}次
            """.strip()
            await message.channel.send(stats + noah.add_emoticon('excited'))
            return

        elif user_text == "!save":
            noah.save_all_memories()
            await message.channel.send("所有记忆和情感都存好啦" + noah.add_emoticon('happy'))
            return

        elif user_text == "!help":
            help_text = """
诺亚完整系统：

!join/!leave - 加入/离开频道
!mynick - 查看你的外号
!mood - 感受你的情绪
!topics - 查看聊过的话题
!memory - 系统统计
!save - 手动保存
!sleep/!awake - 睡觉/起床
"""
            await message.channel.send(help_text)
            return
    
    # 正常对话
    if noah.bot_active and current_channel_id in noah.allowed_channel_ids:
        async with message.channel.typing():
            try:
                reply = ask_gemini_complete_system(
                    user_id, 
                    username, 
                    user_text, 
                    attached_images
                )
                await message.channel.send(reply)
                    
            except Exception as e:
                await message.channel.send("等等，我卡住了..." + noah.add_emoticon('confused'))

# 自动保存
def auto_save_worker():
    while True:
        time.sleep(300)  # 5分钟
        if noah.user_conversations:
            noah.save_all_memories()

# 启动
def run_web():
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=8080)

async def main():
    """主启动函数"""
    # 启动web服务器
    web_thread = Thread(target=run_web, daemon=True)
    web_thread.start()
    print(f"🌐 Web服务器启动在端口 {os.getenv('PORT', 8080)}")
    
    # 启动Discord机器人
    print("🤖 启动Discord机器人...")
    await client.start(TOKEN)

if __name__ == '__main__':
    print("=" * 50)
    print("🚀 启动诺亚云端机器人")
    print("=" * 50)
    
    # 运行主程序
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 手动关闭机器人")
    except Exception as e:
        print(f"💥 启动失败: {e}")



