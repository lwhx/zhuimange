"""
追漫阁 - 模糊匹配算法
"""
import logging
from typing import Optional
from app import config

logger = logging.getLogger(__name__)


def edit_distance(s1: str, s2: str) -> int:
    """
    计算两个字符串的编辑距离（Levenshtein Distance）

    Args:
        s1: 字符串1
        s2: 字符串2

    Returns:
        编辑距离
    """
    m, n = len(s1), len(s2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i - 1] == s2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])

    return dp[m][n]


def ngram_similarity(s1: str, s2: str, n: int = 2) -> float:
    """
    计算 N-gram 相似度

    Args:
        s1: 字符串1
        s2: 字符串2
        n: N-gram 大小

    Returns:
        相似度 (0.0 - 1.0)
    """
    if not s1 or not s2:
        return 0.0

    def get_ngrams(text: str, size: int) -> set:
        return {text[i:i + size] for i in range(len(text) - size + 1)}

    ngrams1 = get_ngrams(s1, n)
    ngrams2 = get_ngrams(s2, n)

    if not ngrams1 or not ngrams2:
        return 0.0

    intersection = ngrams1 & ngrams2
    union = ngrams1 | ngrams2

    return len(intersection) / len(union)


def exact_match(s1: str, s2: str) -> bool:
    """精确匹配（忽略空格和大小写）"""
    return s1.strip().lower() == s2.strip().lower()


def contains_match(title: str, query: str) -> bool:
    """包含匹配"""
    return query.lower() in title.lower() or title.lower() in query.lower()


def subsequence_match_ratio(title: str, query: str) -> float:
    """
    子序列匹配比例：检测 query 中有多少字符按顺序出现在 title 中
    用于处理 UP主缺字情况（如 "斗破苍" → "斗破苍穹"）

    Returns:
        匹配比例 0.0 - 1.0
    """
    if not query or not title:
        return 0.0
    q = query.lower()
    t = title.lower()
    qi = 0
    for ch in t:
        if qi < len(q) and ch == q[qi]:
            qi += 1
    return qi / len(q)


def partial_char_match_ratio(title: str, query: str) -> float:
    """
    字符重叠比例：计算 query 每个字符在 title 中出现的比例
    用于处理同音字替换后仍有不匹配的情况

    Returns:
        重叠比例 0.0 - 1.0
    """
    if not query or not title:
        return 0.0
    q = query.lower()
    t = title.lower()
    matched = sum(1 for ch in q if ch in t)
    return matched / len(q)


def fuzzy_match_score(source_title: str, target_title: str,
                      aliases: Optional[list[str]] = None) -> float:
    """
    综合模糊匹配评分

    Args:
        source_title: 源标题（视频标题，已预处理）
        target_title: 目标标题（动漫名称，已预处理）
        aliases: 动漫别名列表

    Returns:
        匹配分数 (0.0 - 100.0)
    """
    all_titles = [target_title]
    if aliases:
        all_titles.extend([a.lower().strip() for a in aliases])

    best_score = 0.0

    for title in all_titles:
        if not title:
            continue

        score = 0.0

        # 1. 精确匹配 → 满分
        if exact_match(source_title, title):
            return 100.0

        # 2. 包含匹配 → 高分
        if contains_match(source_title, title):
            score = max(score, 85.0)

        # 3. 子序列匹配（匄配缺字情况）
        subseq_ratio = subsequence_match_ratio(source_title, title)
        if subseq_ratio >= 0.8:
            subseq_score = subseq_ratio * 80
            score = max(score, subseq_score)

        # 4. 字符重叠匹配（同音字/变体字）
        char_ratio = partial_char_match_ratio(source_title, title)
        if char_ratio >= 0.7:
            char_score = char_ratio * 70
            score = max(score, char_score)

        # 5. 编辑距离评分
        dist = edit_distance(source_title, title)
        max_len = max(len(source_title), len(title))
        if max_len > 0:
            edit_score = max(0, (1 - dist / max_len)) * 70
            score = max(score, edit_score)

        # 6. N-gram 相似度评分
        ngram_n = config.FUZZY_NGRAM_SIZE
        sim = ngram_similarity(source_title, title, ngram_n)
        ngram_score = sim * 75
        score = max(score, ngram_score)

        best_score = max(best_score, score)

    return round(best_score, 2)
