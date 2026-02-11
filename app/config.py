"""
追漫阁 - 配置文件
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ==================== 基础配置 ====================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_PATH = os.getenv("DATABASE_PATH", os.path.join(BASE_DIR, "data", "tracker.db"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
TZ = os.getenv("TZ", "Asia/Shanghai")
SECRET_KEY = os.getenv("SECRET_KEY", "zhuimange-secret-key-change-in-production")

# ==================== TMDB 配置 ====================
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
TMDB_BASE_URL = os.getenv("TMDB_BASE_URL", "https://api.themoviedb.org/3")
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
TMDB_LANGUAGE = os.getenv("TMDB_LANGUAGE", "zh-CN")

# ==================== Invidious 配置 ====================
INVIDIOUS_URL = os.getenv("INVIDIOUS_URL", "https://invidious.snopyta.org")
INVIDIOUS_API_TIMEOUT = int(os.getenv("INVIDIOUS_API_TIMEOUT", "30"))
INVIDIOUS_FALLBACK_URLS = [
    "https://invidious.snopyta.org",
    "https://yewtu.be",
    "https://invidious.kavin.rocks",
]

# ==================== 匹配算法参数 ====================
MATCH_THRESHOLD = int(os.getenv("MATCH_THRESHOLD", "50"))
MATCH_RECOMMEND_THRESHOLD = int(os.getenv("MATCH_RECOMMEND_THRESHOLD", "70"))
MAX_SEARCH_RESULTS = int(os.getenv("MAX_SEARCH_RESULTS", "50"))
SEARCH_KEYWORDS_LIMIT = int(os.getenv("SEARCH_KEYWORDS_LIMIT", "5"))
FUZZY_EDIT_DISTANCE_MAX = int(os.getenv("FUZZY_EDIT_DISTANCE_MAX", "2"))
FUZZY_NGRAM_SIZE = int(os.getenv("FUZZY_NGRAM_SIZE", "2"))
FUZZY_MIN_SIMILARITY = float(os.getenv("FUZZY_MIN_SIMILARITY", "0.6"))
COLLECTION_MAX_DURATION = int(os.getenv("COLLECTION_MAX_DURATION", "3600"))

# ==================== 评分权重 ====================
SCORE_WEIGHT_TITLE = 0.40
SCORE_WEIGHT_EPISODE = 0.30
SCORE_WEIGHT_CHANNEL = 0.15
SCORE_WEIGHT_RECENCY = 0.15

# ==================== 国漫别名库 ====================
DONGHUA_ALIASES: dict[str, list[str]] = {
    "斗破苍穹": ["斗破苍穹动画", "Battle Through the Heavens", "BTTH", "斗破"],
    "斗罗大陆": ["斗罗大陆动画", "Soul Land", "斗罗"],
    "完美世界": ["完美世界动画", "Perfect World"],
    "吞噬星空": ["吞噬星空动画", "Swallowed Star"],
    "仙逆": ["仙逆动画", "Renegade Immortal"],
    "凡人修仙传": ["凡人修仙传动画", "A Record of a Mortal's Journey to Immortality", "凡人"],
    "一念永恒": ["一念永恒动画", "A Will Eternal"],
    "遮天": ["遮天动画", "Shrouding the Heavens"],
    "武动乾坤": ["武动乾坤动画", "Martial Universe"],
    "武庚纪": ["武庚纪动画", "Legend of Hei"],
    "画江湖之不良人": ["不良人", "Drawing Jianghu"],
    "秦时明月": ["秦时明月动画", "Qin's Moon"],
    "少年歌行": ["少年歌行动画", "The Young Brewmaster's Adventure"],
    "眷思量": ["眷思量动画"],
    "百炼成神": ["百炼成神动画"],
    "万界独尊": ["万界独尊动画"],
    "元龙": ["元龙动画"],
    "师兄啊师兄": ["师兄啊师兄动画"],
}

# ==================== 排除关键词 ====================
EXCLUDE_KEYWORDS: list[str] = [
    "预告", "PV", "CM", "宣传", "先行", "特别篇花絮",
    "合集", "全集", "混剪", "剪辑", "cut",
    "解说", "评价", "吐槽", "盘点", "react", "reaction",
    "教程", "教学", "攻略",
    "AMV", "MAD", "同人",
    "片尾曲", "片头曲", "OP", "ED", "OST", "BGM",
    "拉片", "分析", "科普",
]

# ==================== 缓存配置 ====================
SOURCE_CACHE_DAYS = 7
SYNC_LOG_KEEP_DAYS = 90

# ==================== Telegram 推送 ====================
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")
