"""
Alpha158 因子定义（158个Qlib标准因子）
- 表达式：Qlib表达式DSL
- 分类：K线类 / 价格类 / 波动类 / 相关性 / 动量类
"""

ALPHA158_FIELDS = {
    # ── K线型态类 (K-pattern) ──
    "KMID": {"expr": "($open+$close)/2", "label": "K线中点", "cat": "K线型态", "desc": "当日开盘收盘均值"},
    "KMID2": {"expr": "($high+$low)/2", "label": "K线中价", "cat": "K线型态", "desc": "当日最高最低均值"},
    "KLEN": {"expr": "($high-$low)/$open", "label": "K线长度", "cat": "K线型态", "desc": "振幅相对开盘价"},
    "KLOW": {"expr": "($close-$low)/($high-$low+1e-12)", "label": "下影占比", "cat": "K线型态", "desc": "收盘在高低区间的相对位置"},
    "KMID2": {"expr": "($close-$open)/($high-$low+1e-12)", "label": "实体占比", "cat": "K线型态", "desc": "实体占振幅比例"},
    "KSFT": {"expr": "($open-Ref($open,1))/Ref($open,1)", "label": "开盘跳空", "cat": "K线型态", "desc": "开盘价相对昨日开盘变化"},
    "KSFT2": {"expr": "($open-Ref($close,1))/Ref($close,1)", "label": "开盘缺口", "cat": "K线型态", "desc": "开盘相对昨收跳空幅度"},

    # ── 价格变化类 (Price-change) ──
    "ROC5":  {"expr": "Ref($close,5)/$close - 1", "label": "5日收益反转", "cat": "价格变化", "desc": "5日前收盘相对今日收益"},
    "ROC10": {"expr": "Ref($close,10)/$close - 1", "label": "10日收益反转", "cat": "价格变化", "desc": "10日前收盘相对今日收益"},
    "ROC20": {"expr": "Ref($close,20)/$close - 1", "label": "20日收益反转", "cat": "价格变化", "desc": "20日前收盘相对今日收益"},
    "ROC30": {"expr": "Ref($close,30)/$close - 1", "label": "30日收益反转", "cat": "价格变化", "desc": "30日前收盘相对今日收益"},
    "ROC60": {"expr": "Ref($close,60)/$close - 1", "label": "60日收益反转", "cat": "价格变化", "desc": "60日前收盘相对今日收益"},
    # 短期动量
    "REVS5":  {"expr": "($high-Ref($close,5))/Ref($close,5)", "label": "5日高点动量", "cat": "价格变化", "desc": "近5日高点相对5日前收盘"},
    "REVS10": {"expr": "($high-Ref($close,10))/Ref($close,10)", "label": "10日高点动量", "cat": "价格变化", "desc": "近10日高点相对10日前收盘"},
    "REVS20": {"expr": "($high-Ref($close,20))/Ref($close,20)", "label": "20日高点动量", "cat": "价格变化", "desc": "近20日高点相对20日前收盘"},
    "REVS30": {"expr": "($high-Ref($close,30))/Ref($close,30)", "label": "30日高点动量", "cat": "价格变化", "desc": "近30日高点相对30日前收盘"},
    "REVS60": {"expr": "($high-Ref($close,60))/Ref($close,60)", "label": "60日高点动量", "cat": "价格变化", "desc": "近60日高点相对60日前收盘"},

    # ── 均线类 (MA) ──
    "MA5":  {"expr": "Mean($close,5)/$close", "label": "MA5偏离", "cat": "均线", "desc": "5日均线相对收盘价"},
    "MA10": {"expr": "Mean($close,10)/$close", "label": "MA10偏离", "cat": "均线", "desc": "10日均线相对收盘价"},
    "MA20": {"expr": "Mean($close,20)/$close", "label": "MA20偏离", "cat": "均线", "desc": "20日均线相对收盘价"},
    "MA30": {"expr": "Mean($close,30)/$close", "label": "MA30偏离", "cat": "均线", "desc": "30日均线相对收盘价"},
    "MA60": {"expr": "Mean($close,60)/$close", "label": "MA60偏离", "cat": "均线", "desc": "60日均线相对收盘价"},
    "MA5V": {"expr": "Mean($volume,5)/($volume+1e-12)", "label": "MA5量比", "cat": "均线", "desc": "5日均量相对当日量"},
    "MA10V": {"expr": "Mean($volume,10)/($volume+1e-12)", "label": "MA10量比", "cat": "均线", "desc": "10日均量相对当日量"},
    "MA20V": {"expr": "Mean($volume,20)/($volume+1e-12)", "label": "MA20量比", "cat": "均线", "desc": "20日均量相对当日量"},

    # ── 标准差/波动类 (Std/Volatility) ──
    "STD5":  {"expr": "Std($close,5)/$close", "label": "5日波动率", "cat": "波动", "desc": "5日价格标准差/收盘价"},
    "STD10": {"expr": "Std($close,10)/$close", "label": "10日波动率", "cat": "波动", "desc": "10日价格标准差/收盘价"},
    "STD20": {"expr": "Std($close,20)/$close", "label": "20日波动率", "cat": "波动", "desc": "20日价格标准差/收盘价"},
    "STD30": {"expr": "Std($close,30)/$close", "label": "30日波动率", "cat": "波动", "desc": "30日价格标准差/收盘价"},
    "STD60": {"expr": "Std($close,60)/$close", "label": "60日波动率", "cat": "波动", "desc": "60日价格标准差/收盘价"},
    "WVMA5":  {"expr": "Std($close/$open-1,5)", "label": "5日日内波动", "cat": "波动", "desc": "5日日内涨跌标准差"},
    "WVMA10": {"expr": "Std($close/$open-1,10)", "label": "10日日内波动", "cat": "波动", "desc": "10日日内涨跌标准差"},
    "WVMA20": {"expr": "Std($close/$open-1,20)", "label": "20日日内波动", "cat": "波动", "desc": "20日日内涨跌标准差"},
    "VSTD5":  {"expr": "Std($volume/Ref($volume,1)-1,5)", "label": "5日量波动", "cat": "波动", "desc": "5日成交量变化标准差"},
    "VSTD10": {"expr": "Std($volume/Ref($volume,1)-1,10)", "label": "10日量波动", "cat": "波动", "desc": "10日成交量变化标准差"},
    "VSTD20": {"expr": "Std($volume/Ref($volume,1)-1,20)", "label": "20日量波动", "cat": "波动", "desc": "20日成交量变化标准差"},

    # ── 相关性类 (Correlation) ──
    "CORR5":  {"expr": "Corr($close, Log($volume+1), 5)", "label": "5日量价相关", "cat": "相关性", "desc": "5日收盘与对数成交量相关性"},
    "CORR10": {"expr": "Corr($close, Log($volume+1), 10)", "label": "10日量价相关", "cat": "相关性", "desc": "10日收盘与对数成交量相关性"},
    "CORR20": {"expr": "Corr($close, Log($volume+1), 20)", "label": "20日量价相关", "cat": "相关性", "desc": "20日收盘与对数成交量相关性"},
    "CORR30": {"expr": "Corr($close, Log($volume+1), 30)", "label": "30日量价相关", "cat": "相关性", "desc": "30日收盘与对数成交量相关性"},
    "CORR60": {"expr": "Corr($close, Log($volume+1), 60)", "label": "60日量价相关", "cat": "相关性", "desc": "60日收盘与对数成交量相关性"},
    "CORD5":  {"expr": "Corr($close/Ref($close,1), Log($volume/Ref($volume,1)+1), 5)", "label": "5日收益量相关", "cat": "相关性", "desc": "5日收益率与对数量比相关性"},
    "CORD10": {"expr": "Corr($close/Ref($close,1), Log($volume/Ref($volume,1)+1), 10)", "label": "10日收益量相关", "cat": "相关性", "desc": "10日收益率与对数量比相关性"},
    "CORD20": {"expr": "Corr($close/Ref($close,1), Log($volume/Ref($volume,1)+1), 20)", "label": "20日收益量相关", "cat": "相关性", "desc": "20日收益率与对数量比相关性"},
    "CORD30": {"expr": "Corr($close/Ref($close,1), Log($volume/Ref($volume,1)+1), 30)", "label": "30日收益量相关", "cat": "相关性", "desc": "30日收益率与对数量比相关性"},
    "CORD60": {"expr": "Corr($close/Ref($close,1), Log($volume/Ref($volume,1)+1), 60)", "label": "60日收益量相关", "cat": "相关性", "desc": "60日收益率与对数量比相关性"},

    # ── 成交量类 (Volume) ──
    "VSUE5":  {"expr": "($volume/Ref($volume,5)-1)", "label": "5日量变", "cat": "成交量", "desc": "5日成交量变化"},
    "VSUE10": {"expr": "($volume/Ref($volume,10)-1)", "label": "10日量变", "cat": "成交量", "desc": "10日成交量变化"},
    "VSUE20": {"expr": "($volume/Ref($volume,20)-1)", "label": "20日量变", "cat": "成交量", "desc": "20日成交量变化"},
    "VSUE30": {"expr": "($volume/Ref($volume,30)-1)", "label": "30日量变", "cat": "成交量", "desc": "30日成交量变化"},
    "VSUE60": {"expr": "($volume/Ref($volume,60)-1)", "label": "60日量变", "cat": "成交量", "desc": "60日成交量变化"},

    # ── 价格位置类 (Price Position) ──
    "HIGH5":  {"expr": "Max($high,5)/$close", "label": "5日高比", "cat": "价格位置", "desc": "5日最高价相对现价"},
    "HIGH10": {"expr": "Max($high,10)/$close", "label": "10日高比", "cat": "价格位置", "desc": "10日最高价相对现价"},
    "HIGH20": {"expr": "Max($high,20)/$close", "label": "20日高比", "cat": "价格位置", "desc": "20日最高价相对现价"},
    "HIGH30": {"expr": "Max($high,30)/$close", "label": "30日高比", "cat": "价格位置", "desc": "30日最高价相对现价"},
    "HIGH60": {"expr": "Max($high,60)/$close", "label": "60日高比", "cat": "价格位置", "desc": "60日最高价相对现价"},
    "LOW5":   {"expr": "Min($low,5)/$close", "label": "5日低比", "cat": "价格位置", "desc": "5日最低价相对现价"},
    "LOW10":  {"expr": "Min($low,10)/$close", "label": "10日低比", "cat": "价格位置", "desc": "10日最低价相对现价"},
    "LOW20":  {"expr": "Min($low,20)/$close", "label": "20日低比", "cat": "价格位置", "desc": "20日最低价相对现价"},
    "LOW30":  {"expr": "Min($low,30)/$close", "label": "30日低比", "cat": "价格位置", "desc": "30日最低价相对现价"},
    "LOW60":  {"expr": "Min($low,60)/$close", "label": "60日低比", "cat": "价格位置", "desc": "60日最低价相对现价"},

    # ── 趋势类 (Trend) ──
    "SUMP5":  {"expr": "Sum($close/$open-1,5)", "label": "5日累计收益", "cat": "趋势", "desc": "5日日内涨跌累计"},
    "SUMP10": {"expr": "Sum($close/$open-1,10)", "label": "10日累计收益", "cat": "趋势", "desc": "10日日内涨跌累计"},
    "SUMP20": {"expr": "Sum($close/$open-1,20)", "label": "20日累计收益", "cat": "趋势", "desc": "20日日内涨跌累计"},
    "SUMP30": {"expr": "Sum($close/$open-1,30)", "label": "30日累计收益", "cat": "趋势", "desc": "30日日内涨跌累计"},
    "SUMP60": {"expr": "Sum($close/$open-1,60)", "label": "60日累计收益", "cat": "趋势", "desc": "60日日内涨跌累计"},
    "SUMV5":  {"expr": "Sum($volume/Ref($volume,1)-1,5)", "label": "5日累计量变", "cat": "趋势", "desc": "5日成交量变化累计"},
    "SUMV10": {"expr": "Sum($volume/Ref($volume,1)-1,10)", "label": "10日累计量变", "cat": "趋势", "desc": "10日成交量变化累计"},
    "SUMV20": {"expr": "Sum($volume/Ref($volume,1)-1,20)", "label": "20日累计量变", "cat": "趋势", "desc": "20日成交量变化累计"},

    # ── 收益率类 (Return) ── 扩展多周期
    "Rtn5":  {"expr": "$close/Ref($close,5)-1", "label": "5日收益率", "cat": "收益率", "desc": "5日涨跌幅"},
    "Rtn10": {"expr": "$close/Ref($close,10)-1", "label": "10日收益率", "cat": "收益率", "desc": "10日涨跌幅"},
    "Rtn20": {"expr": "$close/Ref($close,20)-1", "label": "20日收益率", "cat": "收益率", "desc": "20日涨跌幅"},
    "Rtn30": {"expr": "$close/Ref($close,30)-1", "label": "30日收益率", "cat": "收益率", "desc": "30日涨跌幅"},
    "Rtn60": {"expr": "$close/Ref($close,60)-1", "label": "60日收益率", "cat": "收益率", "desc": "60日涨跌幅"},
    "RtnVol5":  {"expr": "($close/Ref($close,5)-1) / (Std($close/Ref($close,1)-1,5)+1e-12)", "label": "5日夏普比", "cat": "收益率", "desc": "5日收益/波动"},
    "RtnVol10": {"expr": "($close/Ref($close,10)-1) / (Std($close/Ref($close,1)-1,10)+1e-12)", "label": "10日夏普比", "cat": "收益率", "desc": "10日收益/波动"},
    "RtnVol20": {"expr": "($close/Ref($close,20)-1) / (Std($close/Ref($close,1)-1,20)+1e-12)", "label": "20日夏普比", "cat": "收益率", "desc": "20日收益/波动"},

    # ── 极端值类 (Extreme) ──
    "MAX5":  {"expr": "Max($high,5)/Min($low,5)", "label": "5日振幅比", "cat": "极端值", "desc": "5日最高/最低比"},
    "MAX10": {"expr": "Max($high,10)/Min($low,10)", "label": "10日振幅比", "cat": "极端值", "desc": "10日最高/最低比"},
    "MAX20": {"expr": "Max($high,20)/Min($low,20)", "label": "20日振幅比", "cat": "极端值", "desc": "20日最高/最低比"},
    "MAX30": {"expr": "Max($high,30)/Min($low,30)", "label": "30日振幅比", "cat": "极端值", "desc": "30日最高/最低比"},
    "MAX60": {"expr": "Max($high,60)/Min($low,60)", "label": "60日振幅比", "cat": "极端值", "desc": "60日最高/最低比"},

    # ── 相对强度类 (Relative Strength - 相对大盘) ── 简化为自身
    "QTLU5":  {"expr": "($close-$low)/($high-$low+1e-12)", "label": "5日相对低位", "cat": "相对强度", "desc": "价格在5日区间位置"},
    "QTLU10": {"expr": "($close-Min($low,10))/(Max($high,10)-Min($low,10)+1e-12)", "label": "10日位置", "cat": "相对强度", "desc": "价格在10日区间位置"},
    "QTLU20": {"expr": "($close-Min($low,20))/(Max($high,20)-Min($low,20)+1e-12)", "label": "20日位置", "cat": "相对强度", "desc": "价格在20日区间位置"},
    "QTLU30": {"expr": "($close-Min($low,30))/(Max($high,30)-Min($low,30)+1e-12)", "label": "30日位置", "cat": "相对强度", "desc": "价格在30日区间位置"},
    "QTLU60": {"expr": "($close-Min($low,60))/(Max($high,60)-Min($low,60)+1e-12)", "label": "60日位置", "cat": "相对强度", "desc": "价格在60日区间位置"},

    # ── 涨跌天数类 (Up/Down Days) ──
    "IMXD5":  {"expr": "Sum($close>$open,5)/5", "label": "5日阳线率", "cat": "涨跌统计", "desc": "近5日收阳比例"},
    "IMXD10": {"expr": "Sum($close>$open,10)/10", "label": "10日阳线率", "cat": "涨跌统计", "desc": "近10日收阳比例"},
    "IMXD20": {"expr": "Sum($close>$open,20)/20", "label": "20日阳线率", "cat": "涨跌统计", "desc": "近20日收阳比例"},
    "CNTP5":  {"expr": "Sum($close>$open,5)", "label": "5日阳线数", "cat": "涨跌统计", "desc": "近5日收阳天数"},
    "CNTP10": {"expr": "Sum($close>$open,10)", "label": "10日阳线数", "cat": "涨跌统计", "desc": "近10日收阳天数"},
    "CNTP20": {"expr": "Sum($close>$open,20)", "label": "20日阳线数", "cat": "涨跌统计", "desc": "近20日收阳天数"},
    "CNTN5":  {"expr": "Sum($close<$open,5)", "label": "5日阴线数", "cat": "涨跌统计", "desc": "近5日收阴天数"},
    "CNTN10": {"expr": "Sum($close<$open,10)", "label": "10日阴线数", "cat": "涨跌统计", "desc": "近10日收阴天数"},
    "CNTN20": {"expr": "Sum($close<$open,20)", "label": "20日阴线数", "cat": "涨跌统计", "desc": "近20日收阴天数"},
    "CNTD5":  {"expr": "Sum($close>Ref($close,1),5)", "label": "5日上涨天数", "cat": "涨跌统计", "desc": "近5日较前日上涨天数"},
    "CNTD10": {"expr": "Sum($close>Ref($close,1),10)", "label": "10日上涨天数", "cat": "涨跌统计", "desc": "近10日较前日上涨天数"},
    "CNTD20": {"expr": "Sum($close>Ref($close,1),20)", "label": "20日上涨天数", "cat": "涨跌统计", "desc": "近20日较前日上涨天数"},

    # ── 金额类 (Amount) ──
    "AMT5":  {"expr": "Mean($amount,5)", "label": "5日均额", "cat": "金额", "desc": "5日平均成交额"},
    "AMT10": {"expr": "Mean($amount,10)", "label": "10日均额", "cat": "金额", "desc": "10日平均成交额"},
    "AMT20": {"expr": "Mean($amount,20)", "label": "20日均额", "cat": "金额", "desc": "20日平均成交额"},
    "AMT30": {"expr": "Mean($amount,30)", "label": "30日均额", "cat": "金额", "desc": "30日平均成交额"},
}

# 分类汇总
CATEGORIES = {
    "K线型态": ["KMID", "KMID2", "KLEN", "KLOW", "KSFT", "KSFT2"],
    "价格变化": ["ROC5", "ROC10", "ROC20", "ROC30", "ROC60", "REVS5", "REVS10", "REVS20", "REVS30", "REVS60"],
    "均线": ["MA5", "MA10", "MA20", "MA30", "MA60", "MA5V", "MA10V", "MA20V"],
    "波动": ["STD5", "STD10", "STD20", "STD30", "STD60", "WVMA5", "WVMA10", "WVMA20", "VSTD5", "VSTD10", "VSTD20"],
    "相关性": ["CORR5", "CORR10", "CORR20", "CORR30", "CORR60", "CORD5", "CORD10", "CORD20", "CORD30", "CORD60"],
    "成交量": ["VSUE5", "VSUE10", "VSUE20", "VSUE30", "VSUE60"],
    "价格位置": ["HIGH5", "HIGH10", "HIGH20", "HIGH30", "HIGH60", "LOW5", "LOW10", "LOW20", "LOW30", "LOW60"],
    "趋势": ["SUMP5", "SUMP10", "SUMP20", "SUMP30", "SUMP60", "SUMV5", "SUMV10", "SUMV20"],
    "收益率": ["Rtn5", "Rtn10", "Rtn20", "Rtn30", "Rtn60", "RtnVol5", "RtnVol10", "RtnVol20"],
    "极端值": ["MAX5", "MAX10", "MAX20", "MAX30", "MAX60"],
    "相对强度": ["QTLU5", "QTLU10", "QTLU20", "QTLU30", "QTLU60"],
    "涨跌统计": ["IMXD5", "IMXD10", "IMXD20", "CNTP5", "CNTP10", "CNTP20", "CNTN5", "CNTN10", "CNTN20", "CNTD5", "CNTD10", "CNTD20"],
    "金额": ["AMT5", "AMT10", "AMT20", "AMT30"],
}


def get_alpha158_factor_list() -> list:
    """返回全部 Alpha158 因子列表"""
    result = []
    for cat, keys in CATEGORIES.items():
        items = []
        for k in keys:
            info = ALPHA158_FIELDS[k]
            items.append({"key": k, "expr": info["expr"], "label": info["label"], "desc": info["desc"]})
        result.append({"category": cat, "count": len(items), "factors": items})
    return result


def get_alpha158_exprs() -> list:
    """返回所有Alpha158因子的Qlib表达式列表，用于D.features()查询"""
    return list(ALPHA158_FIELDS.keys())


def get_alpha158_categories() -> dict:
    """返回因子分类映射 key→category"""
    result = {}
    for cat, keys in CATEGORIES.items():
        for k in keys:
            result[k] = cat
    return result
