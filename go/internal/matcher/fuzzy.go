package matcher

import "math"

// FuzzyMatchScore 对视频标题和动漫标题、别名进行综合模糊匹配评分。
func FuzzyMatchScore(sourceTitle string, targetTitle string, aliases []string, ngramSize int) float64 {
	if sourceTitle == "" || targetTitle == "" {
		return 0
	}
	candidates := append([]string{targetTitle}, aliases...)
	bestScore := 0.0
	for _, candidate := range candidates {
		title := NormalizeText(candidate)
		if title == "" {
			continue
		}
		if exactMatch(sourceTitle, title) {
			return 100
		}
		score := 0.0
		if containsMatch(sourceTitle, title) {
			score = math.Max(score, 85)
		}
		if ratio := subsequenceMatchRatio(sourceTitle, title); ratio >= 0.8 {
			score = math.Max(score, ratio*80)
		}
		if ratio := partialCharMatchRatio(sourceTitle, title); ratio >= 0.7 {
			score = math.Max(score, ratio*70)
		}
		maxLength := maxIntRuneLen(sourceTitle, title)
		if maxLength > 0 {
			editScore := math.Max(0, 1-float64(editDistance(sourceTitle, title))/float64(maxLength)) * 70
			score = math.Max(score, editScore)
		}
		score = math.Max(score, ngramSimilarity(sourceTitle, title, ngramSize)*75)
		bestScore = math.Max(bestScore, score)
	}
	return math.Round(bestScore*100) / 100
}

// editDistance 计算 Levenshtein 编辑距离。
func editDistance(left string, right string) int {
	leftRunes := []rune(left)
	rightRunes := []rune(right)
	rows := len(leftRunes) + 1
	cols := len(rightRunes) + 1
	dp := make([][]int, rows)
	for row := range dp {
		dp[row] = make([]int, cols)
		dp[row][0] = row
	}
	for col := 0; col < cols; col++ {
		dp[0][col] = col
	}
	for row := 1; row < rows; row++ {
		for col := 1; col < cols; col++ {
			if leftRunes[row-1] == rightRunes[col-1] {
				dp[row][col] = dp[row-1][col-1]
			} else {
				dp[row][col] = 1 + minInt(dp[row-1][col], minInt(dp[row][col-1], dp[row-1][col-1]))
			}
		}
	}
	return dp[len(leftRunes)][len(rightRunes)]
}

// ngramSimilarity 计算 N-gram Jaccard 相似度。
func ngramSimilarity(left string, right string, size int) float64 {
	if left == "" || right == "" {
		return 0
	}
	if size <= 0 {
		size = 2
	}
	leftSet := ngrams(left, size)
	rightSet := ngrams(right, size)
	if len(leftSet) == 0 || len(rightSet) == 0 {
		return 0
	}
	intersection := 0
	for item := range leftSet {
		if rightSet[item] {
			intersection++
		}
	}
	union := len(leftSet) + len(rightSet) - intersection
	return float64(intersection) / float64(union)
}

// exactMatch 判断标题是否精确匹配。
func exactMatch(left string, right string) bool {
	return left != "" && right != "" && left == right
}

// containsMatch 判断标题是否互相包含。
func containsMatch(title string, query string) bool {
	return title != "" && query != "" && (contains(title, query) || contains(query, title))
}

// subsequenceMatchRatio 计算子序列匹配比例。
func subsequenceMatchRatio(title string, query string) float64 {
	titleRunes := []rune(title)
	queryRunes := []rune(query)
	if len(titleRunes) == 0 || len(queryRunes) == 0 {
		return 0
	}
	index := 0
	for _, item := range titleRunes {
		if index < len(queryRunes) && item == queryRunes[index] {
			index++
		}
	}
	return float64(index) / float64(len(queryRunes))
}

// partialCharMatchRatio 计算字符重叠比例。
func partialCharMatchRatio(title string, query string) float64 {
	if title == "" || query == "" {
		return 0
	}
	titleSet := map[rune]bool{}
	for _, item := range title {
		titleSet[item] = true
	}
	matched := 0
	total := 0
	for _, item := range query {
		total++
		if titleSet[item] {
			matched++
		}
	}
	return float64(matched) / float64(total)
}

// ngrams 生成文本 N-gram 集合。
func ngrams(text string, size int) map[string]bool {
	runes := []rune(text)
	result := map[string]bool{}
	for index := 0; index+size <= len(runes); index++ {
		result[string(runes[index:index+size])] = true
	}
	return result
}
