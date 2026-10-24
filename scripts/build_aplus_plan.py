#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A+ 内容方案生成 —— 读 listing JSON，产出 A+ 模块结构 + 每张图的生成 prompt

设计依据：Amazon 普通 A+（Basic A+ / Standard A+，非 Premium）
标准模块尺寸（px）：
  970x600  品牌横幅 / 主视觉
  300x300  三图对比（配合 970 宽的模块用）
  970x300  图文分栏（左图右文 / 上图下文）
  970x150  短横幅
  300x400  侧栏图

用法：
  python build_aplus_plan.py --input _b3_p2.json --out reports/aplus/heated-slippers.md

输出：
  - Markdown 方案（模块顺序 + 每个模块的文案 + 图片 prompt）
  - 可直接喂给 linkfox aigc/imageGenAsync 的 prompt 清单（JSON）
"""
import argparse
import json
import os

# Amazon 普通 A+ 模块规格
MODULE_SPECS = {
    "banner":      {"size": "970x600", "desc": "品牌横幅：产品主视觉 + 一句主张"},
    "three_img":   {"size": "300x300 x3", "desc": "三图并排：三个核心卖点各一张"},
    "left_img":    {"size": "300x400 / 600x450", "desc": "左图右文：一张深挖一个卖点"},
    "right_img":   {"size": "300x400 / 600x450", "desc": "右图左文：换边，避免视觉疲劳"},
    "wide_banner": {"size": "970x300", "desc": "宽横幅：场景图 + 使用情境"},
    "compare":     {"size": "970x300", "desc": "对比表：我们 vs 普通款"},
    "specs":       {"size": "970x300", "desc": "规格说明：尺寸/材质/配件"},
}


def build_plan(listing):
    """从 listing JSON 生成 A+ 方案"""
    title = listing.get("title", "")
    bullets = listing.get("bullets") or []
    color = listing.get("color", "")
    material = listing.get("material", "")
    size = listing.get("size", "")
    n_items = listing.get("number_of_items", 1)
    incl = listing.get("included_components", "")
    pt = listing.get("product_type", "")

    # 从标题提取产品核心名（第一个逗号前）
    core = title.split(",")[0].strip()

    plan = {
        "product": core,
        "product_type": pt,
        "modules": [],
    }

    # ① 品牌横幅
    plan["modules"].append({
        "type": "banner",
        "size": MODULE_SPECS["banner"]["size"],
        "headline": core,
        "subline": (bullets[0].split("】")[0].replace("【", "") if bullets else ""),
        "prompt": (f"Amazon A+ module, hero banner, 970x600, product photography of {core}, "
                   f"{color} color, {material} material, on clean light gray studio background, "
                   f"soft directional light from upper left, subtle shadow beneath, "
                   f"premium e-commerce hero shot, wide negative space on the right third for headline text, "
                   f"no text, no logo, no watermark, photorealistic"),
    })

    # ② 三个卖点（从五点里取前三个，去掉末尾的序号词）
    for i, b in enumerate(bullets[:3], 1):
        # 五点格式：【标题】正文
        if "】" in b:
            head, body = b.split("】", 1)
            head = head.replace("【", "").strip()
            body = body.strip()
        else:
            head, body = f"Feature {i}", b
        plan["modules"].append({
            "type": "three_img",
            "index": i,
            "size": MODULE_SPECS["three_img"]["size"],
            "headline": head,
            "body": body[:120],
            "prompt": (f"Amazon A+ module image, 300x300 square, close-up detail shot illustrating: {head}. "
                       f"Product: {core} ({color}, {material}). "
                       f"Show only the relevant part of the product, tight framing, clean white or very light gray background, "
                       f"soft studio light, macro detail, photorealistic, no text, no logo, no hands unless the feature requires grip"),
        })

    # ③ 场景图
    plan["modules"].append({
        "type": "wide_banner",
        "size": MODULE_SPECS["wide_banner"]["size"],
        "headline": "In real use",
        "prompt": (f"Amazon A+ lifestyle banner, 970x300, {core} in a natural home setting, "
                   f"warm indoor lighting, shallow depth of field, product clearly the focal point, "
                   f"realistic home interior context, no text, no logo, photorealistic, wide crop"),
    })

    # ④ 对比表
    plan["modules"].append({
        "type": "compare",
        "size": MODULE_SPECS["compare"]["size"],
        "headline": "Why this one",
        "rows": [
            {"item": "Material", "ours": material or "—", "others": "Common alternative"},
            {"item": "Quantity", "ours": f"{n_items} pcs", "others": "Fewer"},
            {"item": "Included", "ours": incl or "—", "others": "Sold separately"},
        ],
        "prompt": (f"Amazon A+ comparison table module, 970x300, clean minimal layout, "
                   f"product on the left as a cutout against light background, "
                   f"empty right area for a table, flat design, soft neutral palette, no text, photorealistic product render"),
    })

    # ⑤ 规格
    plan["modules"].append({
        "type": "specs",
        "size": MODULE_SPECS["specs"]["size"],
        "headline": "Specifications",
        "items": [
            f"Product: {core}",
            f"Color: {color}",
            f"Material: {material}",
            f"Size: {size}",
            f"Pack: {n_items} pc(s)",
            f"Includes: {incl}",
        ],
        "prompt": (f"Amazon A+ specifications module, 970x300, product laid flat with measuring context, "
                   f"technical illustration style, clean white background, subtle drop shadow, "
                   f"space on the right for spec list, no text, photorealistic"),
    })

    return plan


def to_markdown(plan, listing):
    mk = ["# A+ 内容方案\n"]
    mk.append(f"**产品**：{plan['product']}")
    mk.append(f"**类型**：{plan['product_type']}")
    mk.append(f"**标题**：{listing.get('title', '')}\n")
    mk.append(f"共 {len(plan['modules'])} 个模块，全部为 Amazon 普通 A+ 可用尺寸。\n")

    for i, m in enumerate(plan["modules"], 1):
        mk.append(f"## 模块 {i}：{m['type']}（{m['size']}）\n")
        if m.get("headline"):
            mk.append(f"**主标题**：{m['headline']}")
        if m.get("subline"):
            mk.append(f"**副标题**：{m['subline']}")
        if m.get("body"):
            mk.append(f"**正文**：{m['body']}")
        if m.get("rows"):
            mk.append("\n| 项目 | 我们 | 其他 |")
            mk.append("|---|---|---|")
            for r in m["rows"]:
                mk.append(f"| {r['item']} | {r['ours']} | {r['others']} |")
        if m.get("items"):
            mk.append("\n" + "\n".join(f"- {x}" for x in m["items"]))
        mk.append(f"\n**生图 prompt**：\n```\n{m['prompt']}\n```\n")

    mk.append("---\n## 生图清单（喂 linkfox aigc/imageGenAsync）\n")
    mk.append("| 序号 | 尺寸 | prompt 摘要 |")
    mk.append("|---|---|---|")
    for i, m in enumerate(plan["modules"], 1):
        mk.append(f"| {i} | {m['size']} | {m['prompt'][:60]}... |")
    return "\n".join(mk)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="listing JSON")
    ap.add_argument("--out", help="Markdown 输出")
    ap.add_argument("--json-out", help="prompt 清单 JSON 输出")
    args = ap.parse_args()

    listing = json.load(open(args.input, encoding="utf-8"))
    plan = build_plan(listing)
    md = to_markdown(plan, listing)

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        open(args.out, "w", encoding="utf-8").write(md)
        print(f"✅ A+ 方案已写 {args.out}")
    else:
        print(md)

    if args.json_out:
        os.makedirs(os.path.dirname(args.json_out) or ".", exist_ok=True)
        json.dump(plan, open(args.json_out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"✅ prompt 清单已写 {args.json_out}")

    print(f"\n模块数：{len(plan['modules'])}")
    for i, m in enumerate(plan["modules"], 1):
        print(f"  {i}. {m['type']:<12} {m['size']:<14} {m.get('headline','')[:30]}")
