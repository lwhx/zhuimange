// Package matcher 提供视频源标题预处理、模糊匹配、过滤和综合评分能力。
package matcher

import (
	"regexp"
	"strconv"
	"strings"
	"unicode"

	"github.com/longbridgeapp/opencc"
)

// t2sConverter 繁简转换器（与 Python 版 OpenCC('t2s') 对齐）。
// 初始化失败时降级为不转换，保证服务可用。
var t2sConverter *opencc.OpenCC

func init() {
	c, err := opencc.New("t2s")
	if err != nil {
		// 降级：记录到 stderr 但不阻塞启动
		t2sConverter = nil
		return
	}
	t2sConverter = c
}

// homophoneMap 同音字/常见错别字/缺字映射。
// 注意：繁简转换已由 OpenCC 完成，此处只保留 OpenCC 不处理的
// UP 主规避版权用的同音字、缺字、变体写法。
// 映射键必须是"原文里会出现的错误写法"，不能是正确词的子串，
// 否则会在已正确的文本上重复替换（如 "斗破苍" 会命中 "斗破苍穹"）。
var homophoneMap = map[string]string{
	// 常见同音字替换（UP 主规避版权）
	"豆破":  "斗破",
	"窗穹":  "苍穹",
	"吃星空": "吞噬星空",
	"仙尼":  "仙逆",
}

var episodePatterns = []*regexp.Regexp{
	regexp.MustCompile(`第\s*(\d+)\s*[集话話期回]`),
	regexp.MustCompile(`[Ee][Pp]?\s*\.?\s*(\d+)`),
	regexp.MustCompile(`#\s*(\d+)`),
	regexp.MustCompile(`(\d+)\s*[集话話期回]`),
	regexp.MustCompile(`[第]\s*([一二三四五六七八九十百千]+)\s*[集话話期回]`),
}

// NormalizeText 对标题执行繁简转换、同音字替换、去标点、空白归一和小写处理。
func NormalizeText(text string) string {
	// 1. 繁体转简体（与 Python 版 OpenCC('t2s') 对齐）
	if t2sConverter != nil {
		if converted, err := t2sConverter.Convert(text); err == nil {
			text = converted
		}
	}
	// 2. 同音字/常见错别字替换
	for source, target := range homophoneMap {
		text = strings.ReplaceAll(text, source, target)
	}
	// 3. 去标点 + 空白归一 + 小写
	var builder strings.Builder
	lastSpace := false
	for _, item := range text {
		if unicode.IsLetter(item) || unicode.IsDigit(item) || unicode.Is(unicode.Han, item) {
			builder.WriteRune(unicode.ToLower(item))
			lastSpace = false
			continue
		}
		if !lastSpace {
			builder.WriteRune(' ')
			lastSpace = true
		}
	}
	return strings.TrimSpace(builder.String())
}

// ExtractEpisodeNumber 从标题中提取集数，未识别时返回 false。
func ExtractEpisodeNumber(text string) (int, bool) {
	for _, pattern := range episodePatterns {
		matches := pattern.FindStringSubmatch(text)
		if len(matches) < 2 {
			continue
		}
		if value, ok := parseNumber(matches[1]); ok {
			return value, true
		}
	}
	return 0, false
}

// parseNumber 解析阿拉伯数字或中文数字。
func parseNumber(value string) (int, bool) {
	if number, err := strconv.Atoi(value); err == nil {
		return number, true
	}
	result := 0
	temp := 0
	matched := false
	for _, item := range value {
		unit, ok := cnNumberMap[item]
		if !ok {
			return 0, false
		}
		matched = true
		if unit >= 10 {
			if temp == 0 {
				temp = 1
			}
			result += temp * unit
			temp = 0
		} else {
			temp = unit
		}
	}
	return result + temp, matched
}

var cnNumberMap = map[rune]int{'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10, '百': 100, '千': 1000}
