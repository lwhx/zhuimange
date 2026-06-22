package config

// 业务字典：国漫别名库、排除关键词、画质关键词、同音字映射。
// 这些数据从 Python 版逐条迁移（config.py + matcher/preprocessor.py + scorer.py），
// 作为评分与匹配的业务知识沉淀。

// DonghuaAliases 国漫内置别名库，初始化时灌入 global_aliases 表。
// 迁移自 Python config.py:94-113。
var DonghuaAliases = map[string][]string{
	"斗破苍穹":    {"斗破苍穹动画", "Battle Through the Heavens", "BTTH", "斗破"},
	"斗罗大陆":    {"斗罗大陆动画", "Soul Land", "斗罗"},
	"完美世界":    {"完美世界动画", "Perfect World"},
	"吞噬星空":    {"吞噬星空动画", "Swallowed Star"},
	"仙逆":      {"仙逆动画", "Renegade Immortal"},
	"凡人修仙传":   {"凡人修仙传动画", "A Record of a Mortal's Journey to Immortality", "凡人"},
	"一念永恒":    {"一念永恒动画", "A Will Eternal"},
	"遮天":      {"遮天动画", "Shrouding the Heavens"},
	"武动乾坤":    {"武动乾坤动画", "Martial Universe"},
	"武庚纪":     {"武庚纪动画", "Legend of Hei"},
	"画江湖之不良人": {"不良人", "Drawing Jianghu"},
	"秦时明月":    {"秦时明月动画", "Qin's Moon"},
	"少年歌行":    {"少年歌行动画", "The Young Brewmaster's Adventure"},
	"眷思量":     {"眷思量动画"},
	"百炼成神":    {"百炼成神动画"},
	"万界独尊":    {"万界独尊动画"},
	"元龙":      {"元龙动画"},
	"师兄啊师兄":   {"师兄啊师兄动画"},
}

// ExcludeKeywords 全局非正片排除词。
// 迁移自 Python config.py:116-124。
var ExcludeKeywords = []string{
	"预告", "PV", "CM", "宣传", "先行", "特别篇花絮",
	"合集", "全集", "混剪", "剪辑", "cut",
	"解说", "评价", "吐槽", "盘点", "react", "reaction",
	"教程", "教学", "攻略",
	"AMV", "MAD", "同人",
	"片尾曲", "片头曲", "OP", "ED", "OST", "BGM",
	"拉片", "分析", "科普",
}

// CollectionKeywords 合集检测关键词。
// 迁移自 Python matcher/collection_filter.py。
var CollectionKeywords = []string{
	"合集", "全集", "连续播放", "一口气", "一口气看完",
	"1-", "1～", "大合集", "合辑", "联播", "马拉松", "连播",
}

// NonEpisodeKeywordGroups 非正片内容检测词组（剪辑/解说/预告/音乐/有声小说）。
// 迁移自 Python matcher/collection_filter.py，逐条对齐不漏词。
var NonEpisodeKeywordGroups = [][]string{
	// 剪辑类
	{"剪辑", "混剪", "cut", "名场面", "高能", "高燃", "高光", "催泪", "感动", "燃向", "踩点"},
	// 解说类
	{"解说", "解析", "详解", "评价", "吐槽", "盘点", "分析", "科普", "讲解", "拉片", "react", "reaction", "反应", "影评"},
	// 预告类
	{"预告", "pv", "cm", "宣传", "先行", "预热", "片花", "花絮", "特别篇", "trailer", "preview", "teaser"},
	// 音乐类
	{"音乐", "ost", "bgm", "op", "ed", "片头", "片尾", "片头曲", "片尾曲", "主题曲", "插曲", "amv", "mad", "同人"},
	// 有声/评书类
	{"有声小说", "听书", "说书", "小说朗读", "原著朗读", "广播剧", "书场", "评书", "音频"},
}

// QualityBonusKeywords 画质加分关键词及其分值。
// 迁移自 Python matcher/scorer.py:15-23。
var QualityBonusKeywords = map[string]float64{
	"4k":    10,
	"2160p": 10,
	"蓝光":    8,
	"1080p": 6,
	"超清":    5,
	"高清":    4,
	"720p":  2,
}
