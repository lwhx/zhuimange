package matcher

import (
	"regexp"
	"strings"

	"github.com/lwhx/zhuimange/internal/config"
)

var collectionRangePattern = regexp.MustCompile(`(\d+)\s*[-~～到至]\s*(\d+)\s*[集话話期回]`)
var collectionAllPattern = regexp.MustCompile(`[全共]\s*(\d+)\s*[集话話期回]`)

// 注意：Go 的 regexp（RE2）不支持 (?!...) 负向先行断言。
// 这里把"第N集"与"EPN/EPN（但非 EPN-范围）"拆成两段：
//  1. specificEpisodeCnPattern 匹配中文"第N集/话"写法（与范围无关）
//  2. specificEpisodeEnPattern 匹配 EP/E + 数字，再由 hasSpecificEpisodeEn 排除
//     形如 "EP1-"、"E12～" 的范围写法（不在数字后跟范围分隔符才算具体集）。
var specificEpisodeCnPattern = regexp.MustCompile(`第\s*\d+\s*[集话話期回]`)
var specificEpisodeEnPattern = regexp.MustCompile(`[Ee][Pp]?\s*\.?\s*(\d+)`)
var rangeAfterNumberPattern = regexp.MustCompile(`^\s*[-~～到至]`)

// ShouldFilter 判断视频是否应作为合集或非正片过滤。
func ShouldFilter(title string, duration int, cfg *config.Config) bool {
	return IsCollection(title, duration, cfg) || IsNonEpisodeContent(title)
}

// hasSpecificEpisode 判断标题是否包含具体单集信息（非合集范围写法）。
func hasSpecificEpisode(title string) bool {
	if specificEpisodeCnPattern.MatchString(title) {
		return true
	}
	// 匹配 EP/E + 数字，但排除数字后紧跟范围分隔符（如 "EP1-10"）的合集写法
	locs := specificEpisodeEnPattern.FindAllStringSubmatchIndex(title, -1)
	for _, loc := range locs {
		// group 1 是数字子组的起止位置；数字结束后第一个字符若不是范围符号才算具体集
		numEnd := loc[3]
		rest := title[numEnd:]
		if !rangeAfterNumberPattern.MatchString(rest) {
			return true
		}
	}
	return false
}

// IsCollection 检测标题或时长是否符合合集特征。
func IsCollection(title string, duration int, cfg *config.Config) bool {
	lower := strings.ToLower(title)
	hasEp := hasSpecificEpisode(title)
	for _, keyword := range config.CollectionKeywords {
		if strings.Contains(lower, strings.ToLower(keyword)) {
			if hasEp && (keyword == "合集" || keyword == "大合集" || keyword == "合辑") {
				continue
			}
			return true
		}
	}
	if matches := collectionRangePattern.FindStringSubmatch(title); len(matches) == 3 {
		start := atoi(matches[1])
		end := atoi(matches[2])
		if end-start >= 2 {
			return true
		}
	}
	if collectionAllPattern.MatchString(title) {
		return true
	}
	if duration > 0 && duration > cfg.CollectionMaxDuration {
		return !(hasEp && float64(duration) < float64(cfg.CollectionMaxDuration)*1.5)
	}
	return false
}

// IsNonEpisodeContent 检测标题是否为剪辑、解说、预告、音乐等非正片内容。
func IsNonEpisodeContent(title string) bool {
	lower := strings.ToLower(title)
	for _, group := range config.NonEpisodeKeywordGroups {
		for _, keyword := range group {
			if strings.Contains(lower, strings.ToLower(keyword)) {
				return true
			}
		}
	}
	for _, keyword := range config.ExcludeKeywords {
		if strings.Contains(lower, strings.ToLower(keyword)) {
			return true
		}
	}
	return false
}
