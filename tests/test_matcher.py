import pytest
from app.core.matcher.preprocessor import normalize_text, extract_episode_number
from app.core.matcher.fuzzy_matcher import fuzzy_match_score, edit_distance, ngram_similarity


class TestPreprocessor:
    
    def test_normalize_removes_special_chars(self):
        result = normalize_text("【动漫】标题测试")
        assert "【" not in result
        assert "】" not in result
    
    def test_normalize_normalizes_whitespace(self):
        result = normalize_text("标题   测试")
        assert "   " not in result
    
    def test_normalize_converts_to_lowercase(self):
        result = normalize_text("TITLE Test")
        assert result.islower()
    
    def test_normalize_handles_empty_string(self):
        result = normalize_text("")
        assert result == ""
    
    def test_extract_episode_number_numeric(self):
        assert extract_episode_number("第01集") == 1
        assert extract_episode_number("第12话") == 12
        assert extract_episode_number("EP05") == 5
        assert extract_episode_number("#23") == 23
    
    def test_extract_episode_number_none(self):
        assert extract_episode_number("没有集数的标题") is None


class TestFuzzyMatcher:
    
    def test_exact_match(self):
        title1 = "测试动漫标题"
        title2 = "测试动漫标题"
        
        score = fuzzy_match_score(title1, title2)
        assert score >= 90
    
    def test_partial_match(self):
        title1 = "测试动漫标题"
        title2 = "测试动漫"
        
        score = fuzzy_match_score(title1, title2)
        assert score > 50
    
    def test_no_match(self):
        title1 = "测试标题ABC"
        title2 = "另一个XYZ标题"
        
        score = fuzzy_match_score(title1, title2)
        assert score < 60
    
    def test_match_with_aliases(self):
        title = "测试动漫"
        target = "测试动漫全名"
        aliases = ["测试动漫", "测试"]
        
        score = fuzzy_match_score(title, target, aliases)
        assert score >= 90
    
    def test_edit_distance_identical(self):
        dist = edit_distance("same", "same")
        assert dist == 0
    
    def test_edit_distance_different(self):
        dist = edit_distance("abc", "xyz")
        assert dist == 3
    
    def test_ngram_similarity_identical(self):
        sim = ngram_similarity("test", "test")
        assert sim == 1.0
    
    def test_ngram_similarity_different(self):
        sim = ngram_similarity("abc", "xyz")
        assert sim == 0.0


class TestScorer:
    
    def test_score_video_returns_dict(self):
        from app.core.matcher.scorer import score_video
        video = {
            'title': '测试动漫 第01集',
            'duration': 1440,
            'view_count': 1000,
        }
        result = score_video(video, '测试动漫', 1)
        
        assert isinstance(result, dict)
        assert 'total_score' in result
        assert 'title_score' in result
        assert 'episode_score' in result
    
    def test_score_video_filtered_collection(self):
        from app.core.matcher.scorer import score_video
        video = {
            'title': '测试动漫 1-12集 合集',
            'duration': 7200,
        }
        result = score_video(video, '测试动漫', 1)
        
        assert result['filtered'] is True
        assert result['total_score'] == 0
