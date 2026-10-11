"""Editorial structure for the dated A-share narrative review, not a new model."""

import copy


CHAPTERS = [
    {"id": "introduction", "title": "引言", "sections": []},
    {"id": "methods", "title": "资料与研究方法", "sections": []},
    {"id": "market", "title": "历史周期与本轮市场结构", "sections": [
        {"id": "history", "title": "历史对照：错位见顶、风格接力与全面转弱"},
        {"id": "regime", "title": "本轮牛市的延续与转弱证据"},
        {"id": "relay", "title": "行业与风格接力的广度"},
    ]},
    {"id": "domestic", "title": "国内货币、信用、盈利与股票资金", "sections": [
        {"id": "money", "title": "银行流动性与货币信用条件"},
        {"id": "macro_transmission", "title": "信用到需求与盈利的传导"},
        {"id": "cycle", "title": "经济景气与盈利周期"},
        {"id": "earnings_quality", "title": "上市公司盈利质量与估值拆解"},
        {"id": "valuation", "title": "估值与杠杆的市场承受力"},
        {"id": "stock_funding", "title": "股票资金、杠杆与供给"},
    ]},
    {"id": "external", "title": "全球金融条件与政策冲击传导", "sections": [
        {"id": "dollar", "title": "美元、美债与全球信用"},
        {"id": "japan", "title": "日元、日债与套利交易"},
        {"id": "fx", "title": "人民币与跨境资产"},
        {"id": "cross_listing", "title": "A/H与中国资产的相对表现"},
        {"id": "commodities", "title": "大宗商品与贵金属"},
        {"id": "shock_types", "title": "外部冲击的分类与行业传导"},
        {"id": "policy", "title": "财政、贸易与国际政治经济"},
        {"id": "policy_delivery", "title": "政策宣布与资金落地"},
    ]},
    {"id": "discussion", "title": "讨论：条件低点、修复路径与策略适用", "sections": [
        {"id": "bottom", "title": "下跌低点的观察锚与压力区间"},
        {"id": "conditional_bottom", "title": "条件低点与修复时间"},
        {"id": "rally", "title": "后续大行情的必要观察条件"},
        {"id": "strategy_value", "title": "环境判断的策略价值"},
    ]},
    {"id": "limitations", "title": "研究局限与证据完整性", "sections": [
        {"id": "limits", "title": "历史反例、数据边界与判断更新"},
        {"id": "gap_audit", "title": "数据回补与剩余证据缺口"},
    ]},
    {"id": "conclusion", "title": "综合结论", "sections": [
        {"id": "synthesis", "title": "多维证据的综合判断及失效条件"},
    ]},
]


def with_review_article(report):
    result = copy.deepcopy(report)
    sections = {s["id"]: s for s in report["sections"]}
    ordered = [s["id"] for c in CHAPTERS for s in c["sections"]]
    if len(ordered) != len(set(ordered)) or set(ordered) != set(sections):
        raise ValueError("Review chapters must include every evidence section exactly once")
    source_ids = {s["id"] for s in report["sources"]}
    required = {"csi", "csi2021", "pbc", "pmi", "dgs10", "dfii10"}
    if not required <= source_ids:
        raise ValueError("Missing sources for review framing")
    synthesis = sections["synthesis"]
    result["review_article"] = {
        "version": "narrative-review-v1",
        "formatted_on": "2026-10-08",
        "title": "A股牛市的延续、转弱与再启动：历史比较与宏观金融证据综述",
        "article_type": "叙述性研究综述",
        "publication_note": "FIT项目研究稿 · 未经同行评审 · 非实时行情报告",
        "evidence_refreshed": False,
        "keywords": ["A股牛熊转换", "风格接力", "货币与信用", "盈利质量", "全球金融条件", "条件情景"],
        "abstract": [
            {"label": "目的", "text": "评价2024年9月以来A股牛市的延续条件与转弱风险，区分主线调整、风格接力与全面转熊，并讨论可能的下跌观察区间及后续行情的恢复条件。"},
            {"label": "方法", "text": "采用叙述性证据综述与描述性历史比较，结合五条宽基的价格结构、行业代表、货币信用、盈利与股票资金，以及全球利率、汇率、信用和商品资料。按原研究截止时间组织已可见信息，分别讨论事实、计算、机制解释和条件情景；不建立牛熊概率模型。"},
            {"label": "结果", "text": "截至2026年9月30日，五条宽基均低于60、120、250日均线，尚未出现类似2021年的指数层面强接力。国内银行资金与已披露盈利仍具韧性，但信用活化、主动风险偏好和盈利扩散偏弱；假期可见的外部利率与能源压力进一步约束估值。价格破坏和宏观缓冲同时存在。"},
            {"label": "结论", "text": synthesis["verdict"] + " 下跌区间仅作为观察锚与压力情景；后续判断应由价格修复、新主线的绝对上涨与证据变化更新，而非由单一指标或历史类比决定。"},
        ],
        "introduction": [
            {"text": "牛市判断的核心困难，在于单一领涨资产的见顶、全市场短期调整与大周期结束并不等价。2021年春节后茅台与沪深300回调，而中证500和中证1000随后出现接力；2020年全面技术破坏后又出现修复。这些历史反例要求同时比较不同风格、时间尺度和金融约束，而不能将某一轮市场叙事直接移植到当前。", "sources": ["csi2021", "csi"]},
            {"text": "本文围绕三个问题展开：本轮牛市的延续依据是否仍成立；在继续调整情景下应观察哪些价格锚与压力刻度；什么证据能够支持修复或使偏弱判断进一步增强。研究对象是全A环境与代表宽基的差异，不将局部行业机会等同于全市场牛市，也不将宏观偏弱等同于股票价格必然下跌。", "sources": []},
        ],
        "method_sections": [
            {"title": "研究设计与证据选择", "text": f"本文是叙述性综述，不是系统性文献综述、元分析或因果识别研究。资料来自本项目已归档的数据快照与{len(report['sources'])}项来源记录，优先采用交易所、央行、统计部门和官方指数资料；行情及商业数据按各自口径注明。历史案例为事后描述性比较，不宣称穷尽所有市场周期或完成预注册检验。"},
            {"title": "信息截止与不同频率的对齐", "text": f"证据截止为{report['as_of_at']}，A股行情截至{report['market_date']}；融资采用前一交易日已披露数据。假期新增外盘资料单列，不能回填至此前A股决策时点。月度数据区分所属期、发布日期与可用时间，新旧M1口径分开；未认证的历史首次发布值不能用于声称严格实时回测。"},
            {"title": "计算口径与历史比较", "text": "均线使用交易日收盘简单平均；本轮回撤以2024年9月18日以后已发生的日内高点为基准。历史共同日期比较与单资产事件统计分别展示，保留反例及未完成的未来窗口。价格指数与未复权股票不含分红；ETF份额、NAV和净现金流不能混用，行业代表不等于个股广度。"},
            {"title": "综合推理与情景边界", "text": "沿价格与接力、国内资金和盈利、外部折现率与成本传导组织证据，同时列出支持、反证及限制；高度相关的价格、融资与风险指标不机械计票。20%、25%、30%的高点回撤及PE/EPS压力只是算术假设，不是校准后的底部预测、发生概率或交易参数。图像估算情绪与缺失风险分不作为官方原值或安全证据。"},
        ],
        "chapters": copy.deepcopy(CHAPTERS),
    }
    return result
