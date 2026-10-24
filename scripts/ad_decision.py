#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
广告决策助手 —— 新品要不要开 / 出单后要不要拓词

两个入口：
  1. new_product_decision()  新品：该不该开广告、开几个组、bid 多少
  2. expand_decision()       出单后：搜索词该不该拓、该否哪些

判断依据（对齐项目铁律）：
  - 日预算 $4/组；bid 默认 $0.2，有流量 $0.4；首页首行 +30%
  - 每 ASIN 1 自动 + 1 手动；MX 只开自动
  - 链接必须 BUYABLE 且主图不被压制（否则花钱买不到）

用法：
  python ad_decision.py --new _b3/submitted.json
  python ad_decision.py --expand searchterms.json --sku WBXZ-xxx
"""
import argparse
import json
import os
import statistics


# ---------- 1. 新品决策 ----------

def new_product_decision(product, comp_stats=None):
    """
    product: {sku, asin, price, status, main_img_ok, node, ...}
    comp_stats: {median_sales, median_price, video_rate, ebc_rate, n}
    返回 dict：{open: bool, groups: [...], reason: [...]}
    """
    reasons, blockers = [], []
    sku = product.get("sku")
    asin = product.get("asin")
    price = product.get("price") or 0
    status = (product.get("status") or "").upper()

    # 硬门槛：链接可用
    if not asin:
        blockers.append("没有 ASIN（还没上架成功或审核中）")
    if "BUYABLE" not in status:
        blockers.append(f"状态 {status or '空'}，不是 BUYABLE（买家买不了）")
    if product.get("main_img_ok") is False:
        blockers.append("主图被压制（18027/100581/100588/18644），先修图")

    if blockers:
        return {"sku": sku, "asin": asin, "open": False,
                "blockers": blockers, "reasons": ["链接不可售，开广告等于烧钱"]}

    # 市场容量
    if comp_stats:
        ms = comp_stats.get("median_sales") or 0
        if ms >= 100:
            reasons.append(f"同类目月销中位 {ms:.0f}，市场有量")
        elif ms >= 30:
            reasons.append(f"同类目月销中位 {ms:.0f}，中等市场")
        else:
            reasons.append(f"同类目月销中位 {ms:.0f}，小众市场 → bid 压低试水")
    else:
        reasons.append("无同类目数据，按默认参数开")

    # 价格带（项目客单 $20-40 最稳）
    if price >= 20:
        reasons.append(f"售价 ${price}，在 $20+ 区间，可承受 $0.2-0.4 bid")
    else:
        reasons.append(f"售价 ${price} 偏低，bid 必须压到 $0.2 以内，否则 ACoS 会爆")

    # 组结构：1 自动 + 1 手动
    bid = 0.4 if (comp_stats and (comp_stats.get("median_sales") or 0) >= 100) else 0.2
    groups = [
        {"type": "AUTO", "daily_budget": 4.0, "bid": bid,
         "note": "4 个匹配全开；bid 在 adGroup.defaultBid，不是 keywords"},
        {"type": "MANUAL", "daily_budget": 4.0, "bid": bid,
         "note": "从竞品标题/五点提取 8-12 个精准词，短语+精准各一组或一组两匹配"},
    ]
    if price < 20:
        bid = 0.2
        groups = [{"type": "AUTO", "daily_budget": 4.0, "bid": 0.2,
                   "note": "低价品只开自动，bid 压到 0.2，跑 7 天看数据"}]

    return {"sku": sku, "asin": asin, "open": True, "groups": groups,
            "reasons": reasons, "blockers": []}


# ---------- 2. 拓词决策 ----------

def expand_decision(terms, sku=None, min_ctr=0.005, min_cvr=0.05,
                    waste_spend=2.0, target_acos=0.30):
    """
    terms: [{keyword, impressions, clicks, spend, sales, orders, acos}]
    返回：{promote: [...], negate: [...], watch: [...]}
    """
    promote, negate, watch = [], [], []
    for t in terms or []:
        kw = t.get("keyword")
        imp = t.get("impressions") or 0
        clk = t.get("clicks") or 0
        spend = t.get("spend") or 0
        sales = t.get("sales") or 0
        orders = t.get("orders") or 0
        ctr = clk / imp if imp else 0
        cvr = orders / clk if clk else 0
        acos = spend / sales if sales else (99 if spend else 0)

        item = {"keyword": kw, "clicks": clk, "orders": orders,
                "spend": round(spend, 2), "sales": round(sales, 2),
                "ctr": round(ctr, 4), "cvr": round(cvr, 4),
                "acos": round(acos, 3) if acos < 90 else None}

        if orders >= 2 and acos <= target_acos:
            promote.append({**item, "action": "加精准组 / 提高 bid",
                            "why": f"出 {orders} 单且 ACoS {acos:.0%} ≤ {target_acos:.0%}"})
        elif spend >= waste_spend and orders == 0:
            negate.append({**item, "action": "否词（精准否定）",
                           "why": f"花费 ${spend:.2f} 零订单"})
        elif ctr >= min_ctr and cvr >= min_cvr:
            promote.append({**item, "action": "提 bid 抢位",
                            "why": f"CTR {ctr:.2%} / CVR {cvr:.2%} 表现好"})
        elif imp >= 100 and clk == 0:
            negate.append({**item, "action": "否词（曝光不点击）",
                           "why": f"{imp} 次曝光零点击，相关性差"})
        else:
            watch.append({**item, "action": "继续观察",
                          "why": "数据量不足，等更多曝光"})

    # 按花费排序，方便老板先看最贵的
    promote.sort(key=lambda x: -x["sales"])
    negate.sort(key=lambda x: -x["spend"])
    watch.sort(key=lambda x: -x["clicks"])
    return {"sku": sku, "promote": promote, "negate": negate, "watch": watch,
            "summary": {"promote": len(promote), "negate": len(negate), "watch": len(watch)}}


def to_markdown(result, kind="new"):
    mk = []
    if kind == "new":
        mk.append(f"# 新品开广告决策：{result['sku']}\n")
        mk.append(f"**ASIN**：{result.get('asin') or '—'}")
        mk.append(f"**结论**：{'✅ 开' if result['open'] else '❌ 暂不开'}\n")
        if result["blockers"]:
            mk.append("## 阻塞项（先解决）\n")
            for b in result["blockers"]:
                mk.append(f"- ⛔ {b}")
            mk.append("")
        if result["reasons"]:
            mk.append("## 判断依据\n")
            for r in result["reasons"]:
                mk.append(f"- {r}")
            mk.append("")
        if result["open"]:
            mk.append("## 建组方案\n")
            mk.append("| 类型 | 日预算 | bid | 备注 |")
            mk.append("|---|---|---|---|")
            for g in result["groups"]:
                mk.append(f"| {g['type']} | ${g['daily_budget']} | ${g['bid']} | {g['note']} |")
    else:
        s = result["summary"]
        mk.append(f"# 搜索词拓词决策：{result.get('sku') or '—'}\n")
        mk.append(f"拓词 {s['promote']} / 否词 {s['negate']} / 观察 {s['watch']}\n")
        if result["promote"]:
            mk.append("## 一、该加精准（有单且 ACoS 达标）\n")
            mk.append("| 词 | 点击 | 单 | 花费 | 销售额 | ACoS | 建议 |")
            mk.append("|---|---|---|---|---|---|---|")
            for x in result["promote"]:
                acos = f"{x['acos']:.0%}" if x["acos"] is not None else "—"
                mk.append(f"| {x['keyword']} | {x['clicks']} | {x['orders']} | "
                          f"${x['spend']} | ${x['sales']} | {acos} | {x['action']} |")
            mk.append("")
        if result["negate"]:
            mk.append("## 二、该否词（烧钱无单 / 曝光不点）\n")
            mk.append("| 词 | 点击 | 花费 | 原因 |")
            mk.append("|---|---|---|---|")
            for x in result["negate"]:
                mk.append(f"| {x['keyword']} | {x['clicks']} | ${x['spend']} | {x['why']} |")
            mk.append("")
        if result["watch"]:
            mk.append("## 三、继续观察\n")
            mk.append("| 词 | 曝光 | 点击 | 花费 |")
            mk.append("|---|---|---|---|")
            for x in result["watch"][:15]:
                mk.append(f"| {x['keyword']} | - | {x['clicks']} | ${x['spend']} |")
    return "\n".join(mk)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--new", help="新品 JSON（含 sku/asin/price/status）")
    ap.add_argument("--expand", help="搜索词 JSON")
    ap.add_argument("--sku", default=None)
    ap.add_argument("--out", help="Markdown 输出")
    args = ap.parse_args()

    if args.new:
        data = json.load(open(args.new, encoding="utf-8"))
        items = data if isinstance(data, list) else [data]
        md = []
        for it in items:
            r = new_product_decision(it)
            md.append(to_markdown(r, "new"))
            md.append("\n---\n")
        text = "\n".join(md)
    elif args.expand:
        terms = json.load(open(args.expand, encoding="utf-8"))
        if isinstance(terms, dict):
            terms = terms.get("terms") or terms.get("data") or []
        r = expand_decision(terms, args.sku)
        text = to_markdown(r, "expand")
    else:
        print(__doc__)
        raise SystemExit(1)

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        open(args.out, "w", encoding="utf-8").write(text)
        print(f"✅ 已写 {args.out}")
    else:
        print(text)
