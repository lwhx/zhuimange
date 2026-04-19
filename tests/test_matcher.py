"""
匹配算法单元测试
"""
from app.core.matcher.preprocessor import (
    normalize_text, extract_episode_number, cn_num_to_int,
)
from app.core.matcher.fuzzy_matcher import (
    exact_match, contains_match, edit_distance, ngram_similarity,
    subsequence_match_ratio, partial_char_match_ratio, fuzzy_match_score,
)
from app.core.matcher.collection_filter import is_collection, is_non_episode_content, should_filter


class TestPreprocessor:
    """文本预处理器测试"""

    def test_normalize_text_removes_punctuation(self):
        result = normalize_text("【斗破苍穹】第1集")
        assert "【" not in result
        assert "】" not in result

    def test_normalize_text_lowercase(self):
        result = normalize_text("Perfect World")
        assert result == "perfect world"

    def test_extract_episode_number_arabic(self):
        assert extract_episode_number("斗破苍穹第5集") == 5
        assert extract_episode_number("斗破苍穹第12集") == 12

    def test_extract_episode_number_ep_format(self):
        assert extract_episode_number("完美世界 EP05") == 5
        assert extract_episode_number("完美世界 EP12") == 12

    def test_extract_episode_number_hash(self):
        assert extract_episode_number("仙逆 #3") == 3

    def test_extract_episode_number_chinese(self):
        assert extract_episode_number("斗罗大陆第二集") == 2
        assert extract_episode_number("斗罗大陆第十集") == 10
        assert extract_episode_number("斗罗大陆第二十三集") == 23

    def test_extract_episode_number_none(self):
        assert extract_episode_number("斗破苍穹预告") is None
        assert extract_episode_number("") is None

    def test_cn_num_to_int(self):
        assert cn_num_to_int("一") == 1
        assert cn_num_to_int("十") == 10
        assert cn_num_to_int("二十三") == 23
        assert cn_num_to_int("一百") == 100


class TestFuzzyMatcher:
    """模糊匹配测试"""

    def test_exact_match(self):
        assert exact_match("斗破苍穹", "斗破苍穹") is True
        assert exact_match("斗破苍穹", "斗罗大陆") is False

    def test_exact_match_ignore_case_space(self):
        assert exact_match("  Perfect World  ", "perfect world") is True

    def test_contains_match(self):
        assert contains_match("斗破苍穹第5集", "斗破苍穹") is True
        assert contains_match("斗破苍穹", "斗破") is True

    def test_edit_distance(self):
        assert edit_distance("", "") == 0
        assert edit_distance("abc", "abc") == 0
        assert edit_distance("abc", "abd") == 1

    def test_ngram_similarity(self):
        sim = ngram_similarity("斗破苍穹", "斗破苍穹")
        assert sim == 1.0
        sim = ngram_similarity("", "test")
        assert sim == 0.0

    def test_subsequence_match_ratio(self):
        ratio = subsequence_match_ratio("斗破苍穹动画", "斗破苍穹")
        assert ratio >= 0.8

    def test_partial_char_match_ratio(self):
        ratio = partial_char_match_ratio("斗破苍穹动画", "斗破苍穹")
        assert ratio >= 0.7

    def test_fuzzy_match_score_exact(self):
        score = fuzzy_match_score("斗破苍穹", "斗破苍穹")
        assert score == 100.0

    def test_fuzzy_match_score_with_aliases(self):
        score = fuzzy_match_score("BTTH", "斗破苍穹", aliases=["BTTH"])
        assert score > 0

    def test_fuzzy_match_score_empty(self):
        score = fuzzy_match_score("", "斗破苍穹")
        assert score == 0.0


class TestCollectionFilter:
    """合集过滤器测试"""

    def test_is_collection_keyword(self):
        assert is_collection("斗破苍穹合集") is True
        assert is_collection("斗破苍穹全集") is True

    def test_is_collection_range(self):
        assert is_collection("斗破苍穹 1-10集") is True
        assert is_collection("斗破苍穹 1～5集") is True

    def test_is_collection_specific_ep_not_filtered(self):
        # 标题有具体集数时不应被"合集"关键词误过滤
        assert is_collection("斗破苍穹合集 第5集") is False

    def test_is_collection_duration(self):
        assert is_collection("斗破苍穹", duration=7200) is True
        assert is_collection("斗破苍穹第5集", duration=1500) is False

    def test_is_non_episode_content_commentary(self):
        assert is_non_episode_content("斗破苍穹解说") is True
        assert is_non_episode_content("斗破苍穹混剪") is True

    def test_is_non_episode_content_preview(self):
        assert is_non_episode_content("斗破苍穹预告") is True
        assert is_non_episode_content("斗破苍穹PV") is True

    def test_is_non_episode_content_music(self):
        assert is_non_episode_content("斗破苍穹OP") is True
        assert is_non_episode_content("斗破苍穹BGM") is True

    def test_should_filter_normal(self):
        assert should_filter("斗破苍穹第5集", duration=1500) is False

    def test_should_filter_collection(self):
        assert should_filter("斗破苍穹合集", duration=0) is True
