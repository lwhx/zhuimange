"""
追漫阁 - 文本预处理器
"""
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 尝试导入 OpenCC 用于繁简转换
try:
    from opencc import OpenCC
    _converter = OpenCC('t2s')
    HAS_OPENCC = True
except ImportError:
    HAS_OPENCC = False
    logger.warning("OpenCC 未安装，繁简转换将被跳过")

# 同音字/常见错别字/繁简变体映射
HOMOPHONE_MAP: dict[str, str] = {
    # 繁体字映射
    "鬥": "斗",
    "羅": "罗",
    "蒼": "苍",
    "穹": "穹",
    "靈": "灵",
    "劍": "剑",
    "尊": "尊",
    "萬": "万",
    "獨": "独",
    "廣": "广",
    "戰": "战",
    "天": "天",
    "龍": "龙",
    "神": "神",
    "國": "国",
    "樣": "样",
    "魔": "魔",
    "王": "王",
    "修": "修",
    "傳": "传",
    "永": "永",
    "恆": "恒",
    # 常见同音字替换（UP主规避版权）
    "斗破": "斗破",
    "豆破": "斗破",
    "窗穹": "苍穹",
    "尊上": "尊",
    "凡人": "凡人",
    "吃星空": "吞噬星空",
    "仙尼": "仙逆",
    "完美": "完美",
    # 缺字/变体常见
    "斗破苍": "斗破苍穹",
    "斗罗": "斗罗大陆",
    "吞噬": "吞噬星空",
    "完美世": "完美世界",
    "凡人修仙": "凡人修仙传",
}

# 需要移除的标点和特殊字符
PUNCT_PATTERN = re.compile(r'[【】\[\]()（）《》<>「」『』\-_—·•.,，。！!？?:：;；""\'''""&＆/\\|]')
# 空白字符归一化
WHITESPACE_PATTERN = re.compile(r'\s+')
# 集数提取
EPISODE_PATTERNS = [
    re.compile(r'第\s*(\d+)\s*[集话話期回]'),
    re.compile(r'[Ee][Pp]?\s*\.?\s*(\d+)'),
    re.compile(r'#\s*(\d+)'),
    re.compile(r'(\d+)\s*[集话話期回]'),
    re.compile(r'[第]\s*([一二三四五六七八九十百千]+)\s*[集话話期回]'),
]

# 中文数字映射
CN_NUM_MAP = {
    '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
    '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
    '百': 100, '千': 1000,
}


def cn_num_to_int(cn_str: str) -> int:
    """将中文数字转换为阿拉伯数字"""
    result = 0
    temp = 0
    for char in cn_str:
        if char in CN_NUM_MAP:
            val = CN_NUM_MAP[char]
            if val >= 10:
                if temp == 0:
                    temp = 1
                result += temp * val
                temp = 0
            else:
                temp = val
    result += temp
    return result


def traditional_to_simplified(text: str) -> str:
    """繁体转简体"""
    if HAS_OPENCC:
        return _converter.convert(text)
    return text


def replace_homophones(text: str) -> str:
    """替换同音字/常见错别字"""
    for src, dst in HOMOPHONE_MAP.items():
        text = text.replace(src, dst)
    return text


def normalize_text(text: str) -> str:
    """
    文本归一化处理

    1. 繁体转简体
    2. 同音字替换
    3. 去标点
    4. 空白归一化
    5. 小写
    """
    text = traditional_to_simplified(text)
    text = replace_homophones(text)
    text = PUNCT_PATTERN.sub(' ', text)
    text = WHITESPACE_PATTERN.sub(' ', text).strip()
    text = text.lower()
    return text


def extract_episode_number(text: str) -> Optional[int]:
    """
    从文本中提取集数

    Returns:
        集数号，未找到返回 None
    """
    for pattern in EPISODE_PATTERNS:
        match = pattern.search(text)
        if match:
            num_str = match.group(1)
            # 检查是否为中文数字
            if re.match(r'^[一二三四五六七八九十百千]+$', num_str):
                return cn_num_to_int(num_str)
            try:
                return int(num_str)
            except ValueError:
                continue
    return None


def extract_season_number(text: str) -> Optional[int]:
    """从文本中提取季数"""
    patterns = [
        re.compile(r'第\s*(\d+)\s*季'),
        re.compile(r'[Ss](?:eason)?\s*(\d+)'),
        re.compile(r'第\s*([一二三四五六七八九十]+)\s*季'),
    ]
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            num_str = match.group(1)
            if re.match(r'^[一二三四五六七八九十]+$', num_str):
                return cn_num_to_int(num_str)
            try:
                return int(num_str)
            except ValueError:
                continue
    return None
