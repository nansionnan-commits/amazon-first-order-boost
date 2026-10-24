#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
首单品后续动作 —— 对一个刚出单的品，补齐三件事

为什么：品从 0 单变成有单，说明市场验证通过。这时候才值得投入：
  - 广告：放量 / 拓词（之前没单时烧钱没意义）
  - A+：补内容（提高转化）
  - 视频：补视频（提高转化 + 降低退货）

用法：
  # 单个品
  python first_order_action.py --sku LRR20261022004 --asin B0XXXX --price 34 --store zhangaodi

  # 批量（读 detect_first_orders 的输出）
  python first_order_action.py --from-detected reports/first_order/2026-10-23.json
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


# ---------- 广告 ----------
def ad_section(sku, asin, price):
    """生成广告建议（不含实际查询，查询由 agent 调 linkfox）"""
    lines = []
    if not asin:
        return ["⛔ 没有 ASIN，先确认上架状态"], {"open": False, "reason": "无 ASIN"}
    lines.append(f"**查广告是否存在**：`sp/campaigns/list` 按 ASIN 过滤")
    lines.append(f"**如果没广告** → 按项目铁律开组：")
    bid = 0.4 if price >= 20 else 0.2
    lines.append(f"  - 1 个 AUTO（4 匹配全开，bid ${bid}，日预算 $4）")
    if price >= 20:
        lines.append(f"  - 1 个 MANUAL（竞品标题/五点提取 8-12 词，bid ${bid}，日预算 $4）")
    else:
        lines.append(f"  - 低价品只开 AUTO（售价 ${price} < $20，手动必亏）")
    lines.append(f"**如果已有广告** → 拉最近 14 天搜索词报表，按 `ad_decision.expand_decision` 判：")
    lines.append(f"  - 出单≥2 且 ACoS≤30% → 加精准组")
    lines.append(f"  - 花费≥$2 零单 → 否词")
    return lines, {"open": True, "bid": bid, "price": price}


# ---------- A+ / 视频 ----------
def content_section(asin):
    """A+ 与视频检查（实际查询由 agent 调 sellersprite）"""
    lines = [
        f"**查 A+ 和视频状态**：sellersprite `productSearch` 用 ASIN 反查，看 `badgeEbc` / `badgeVideo`",
        f"  - `badgeEbc = N` → 出 A+ 方案：`build_aplus_plan.py --input <listing.json>`",
        f"  - `badgeVideo = N` → 扫竞品视频：`scan_competitor_video.py`，找同类目有视频的参考",
        f"  - 两者都是 Y → 只做优化（换主图/调价），不用补内容",
    ]
    return lines


def build_card(item):
    """单个品的动作卡片"""
    sku = item.get("sku")
    asin = item.get("asin")
    price = float(item.get("price") or item.get("first_price") or 0)
    store = item.get("store")
    market = item.get("market") or "US"

    ad_lines, ad_meta = ad_section(sku, asin, price)
    content_lines = content_section(asin)

    return {
        "sku": sku, "asin": asin, "price": price, "store": store, "market": market,
        "ad": {"lines": ad_lines, "meta": ad_meta},
        "content": {"lines": content_lines},
        "checklist": [
            "① 广告：确认有无 + 按表现决定开/加/拓词",
            "② A+：badgeEbc=N 就生成方案",
            "③ 视频：badgeVideo=N 就扫竞品参考",
        ],
    }


def to_markdown(cards, day=None):
    mk = [f"# 首单品后续动作清单{f'（{day}）' if day else ''}\n"]
    mk.append(f"本次 **{len(cards)}** 个品首次出单。\n")
    for i, c in enumerate(cards, 1):
        mk.append(f"## {i}. `{c['sku']}` — {c['store']}-{c['market']}\n")
        mk.append(f"- ASIN：**{c['asin'] or '—'}**")
        mk.append(f"- 首单价：${c['price']}\n")
        mk.append("### ① 广告\n")
        for l in c["ad"]["lines"]:
            mk.append(l)
        mk.append("\n### ② A+ / 视频\n")
        for l in c["content"]["lines"]:
            mk.append(l)
        mk.append("\n### ✅ 动作清单\n")
        for x in c["checklist"]:
            mk.append(f"- [ ] {x}")
        mk.append("\n---\n")
    return "\n".join(mk)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sku")
    ap.add_argument("--asin")
    ap.add_argument("--price", type=float, default=0)
    ap.add_argument("--store", default="zhangaodi")
    ap.add_argument("--market", default="US")
    ap.add_argument("--from-detected", help="detect_first_orders 的输出 JSON")
    ap.add_argument("--out")
    args = ap.parse_args()

    if args.from_detected:
        items = json.load(open(args.from_detected, encoding="utf-8"))
    elif args.sku:
        items = [{"sku": args.sku, "asin": args.asin, "price": args.price,
                  "store": args.store, "market": args.market}]
    else:
        print(__doc__)
        raise SystemExit(1)

    cards = [build_card(x) for x in items]
    text = to_markdown(cards)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        open(args.out, "w", encoding="utf-8").write(text)
        print(f"✅ 已写 {args.out}")
    print(text)
