#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
竞品视频 / A+ 扫描 —— 用卖家精灵查同类目竞品有没有视频和 A+

用法：
  python scan_competitor_video.py --keyword "christmas wreath ties"
  python scan_competitor_video.py --keyword "heated slippers" --size 20 --min-sales 30
  python scan_competitor_video.py --keyword "dog bed" --out reports/video_dogbed.md

输出：
  - 控制台表格
  - Markdown 报告（含视频竞品清单 + 直接可点的 Amazon 链接）
"""
import argparse
import json
import os
import sys
import time

# linkfox MCP 通过 DeferExecuteTool 调用，本脚本只做"结果整理"，
# 实际调用由上层 agent 完成；也支持直接读已保存的 JSON。

def summarize(products, keyword, min_sales=0):
    """从 sellersprite 返回里筛出有视频 / 有 A+ 的竞品"""
    rows = []
    for p in products or []:
        sales = p.get("monthlySalesUnits") or 0
        if sales < min_sales:
            continue
        badge = p.get("badge") or {}
        rows.append({
            "asin": p.get("asin"),
            "title": (p.get("title") or "")[:70],
            "brand": p.get("brand"),
            "price": p.get("price"),
            "sales": sales,
            "revenue": round(p.get("monthlySalesRevenue") or 0, 0),
            "bsr": p.get("bsr"),
            "rating": p.get("rating"),
            "ratings": p.get("ratings"),
            "variation": p.get("variationNum"),
            "video": (p.get("badgeVideo") or badge.get("video") or "N").upper() == "Y",
            "ebc": (p.get("badgeEbc") or badge.get("ebc") or "N").upper() == "Y",
            "fulfillment": p.get("fulfillment"),
            "node": p.get("nodeLabelPath"),
            "url": p.get("asinUrl") or f"https://www.amazon.com/dp/{p.get('asin')}",
        })
    rows.sort(key=lambda x: (-x["sales"], x["bsr"] or 10**9))
    return rows


def report(rows, keyword, out_path=None):
    total = len(rows)
    with_video = [r for r in rows if r["video"]]
    with_ebc = [r for r in rows if r["ebc"]]
    v_rate = len(with_video) / total * 100 if total else 0
    e_rate = len(with_ebc) / total * 100 if total else 0

    lines = []
    lines.append(f"# 竞品视频 / A+ 扫描：{keyword}\n")
    lines.append(f"- 样本：{total} 个竞品")
    lines.append(f"- **有视频：{len(with_video)} 个（{v_rate:.0f}%）**")
    lines.append(f"- **有 A+：{len(with_ebc)} 个（{e_rate:.0f}%）**")
    lines.append(f"- 扫描时间：{time.strftime('%Y-%m-%d %H:%M')}\n")

    lines.append("## 一、有视频的竞品（优先参考/抓取）\n")
    if with_video:
        lines.append("| ASIN | 月销 | 价格 | 评分 | 变体 | 品牌 | 标题 |")
        lines.append("|---|---|---|---|---|---|---|")
        for r in with_video:
            lines.append(f"| [{r['asin']}]({r['url']}) | {r['sales']} | ${r['price']} | "
                         f"{r['rating'] or '-'}({r['ratings'] or 0}) | {r['variation'] or 1} | "
                         f"{r['brand'] or '-'} | {r['title']} |")
    else:
        lines.append("_该关键词下没有找到带视频的竞品。_\n")

    lines.append("\n## 二、全量对照（视频 / A+）\n")
    lines.append("| ASIN | 视频 | A+ | 月销 | 价格 | BSR | 品牌 |")
    lines.append("|---|:---:|:---:|---|---|---|---|")
    for r in rows:
        lines.append(f"| [{r['asin']}]({r['url']}) | {'✅' if r['video'] else '—'} | "
                     f"{'✅' if r['ebc'] else '—'} | {r['sales']} | ${r['price']} | "
                     f"{r['bsr'] or '-'} | {r['brand'] or '-'} |")

    lines.append("\n## 三、给我们的结论\n")
    if v_rate >= 50:
        lines.append(f"- 同类目 **{v_rate:.0f}%** 有视频，属于标配 → **新品必须配视频**，否则转化吃亏。")
    elif v_rate >= 20:
        lines.append(f"- 同类目 **{v_rate:.0f}%** 有视频，属于加分项 → 有预算就做，能做就领先。")
    else:
        lines.append(f"- 同类目只有 **{v_rate:.0f}%** 有视频，属于稀缺 → 做了就是差异化优势。")

    if e_rate >= 60:
        lines.append(f"- 同类目 **{e_rate:.0f}%** 有 A+，已是标配 → **不配 A+ 明显处于劣势**。")
    elif e_rate >= 30:
        lines.append(f"- 同类目 **{e_rate:.0f}%** 有 A+ → 建议配，属于常规动作。")
    else:
        lines.append(f"- 同类目只有 **{e_rate:.0f}%** 有 A+ → 做了能明显拉开差距。")

    if with_video:
        top = with_video[0]
        lines.append(f"- 视频抓取优先级最高：`{top['asin']}`（月销 {top['sales']}，{top['url']}）")

    text = "\n".join(lines)
    if out_path:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        open(out_path, "w", encoding="utf-8").write(text)
        print(f"✅ 报告已写 {out_path}")
    return text, {
        "total": total, "video": len(with_video), "ebc": len(with_ebc),
        "v_rate": round(v_rate), "e_rate": round(e_rate),
        "video_asins": [r["asin"] for r in with_video],
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--keyword", required=True)
    ap.add_argument("--min-sales", type=int, default=0)
    ap.add_argument("--json", help="已保存的 sellersprite 返回 JSON 路径")
    ap.add_argument("--out", help="Markdown 输出路径")
    args = ap.parse_args()

    if args.json:
        data = json.load(open(args.json, encoding="utf-8"))
        products = data.get("products") or []
        rows = summarize(products, args.keyword, args.min_sales)
        text, stat = report(rows, args.keyword, args.out)
        print(text[:2000])
        print("\n统计:", stat)
    else:
        print("请先用 linkfox sellersprite/productSearch 取数据，保存 JSON 后加 --json 传入。")
        print("或由 agent 直接调用本项目内的 scan_competitor_video.summarize/report。")
