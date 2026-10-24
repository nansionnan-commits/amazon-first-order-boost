#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
首单品体检入口 —— 给一个 SKU/ASIN，自动跑完能自动的部分

用法：
  python run_one.py --sku CHT20260822149
  python run_one.py --asin B0HNWW48YN
  python run_one.py --sku CHT20260822149 --price 20 --out report.md

输出：
  1. 是不是首单（查台账）
  2. 链接当前状态（ASIN / BUYABLE / 主图有没有被压制）
  3. 广告决策（基于价格 + 类目数据）
  4. 待办清单：哪些需要 agent 调 MCP（sellersprite / aigc）
"""
import argparse
import json
import os
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

SPAPI = r"D:/workbuddy-ml/D盘默认/sp-api"
LEDGER = os.path.join(SKILL_ROOT, "config", "first_order_ledger.json")
MP_US = "ATVPDKIKX0DER"
IMG_BAD = {100581, 18027, 100588, 18644}
TM_BAD = {18146}


def load_ledger():
    if not os.path.exists(LEDGER):
        return {"skus": {}}
    return json.load(open(LEDGER, encoding="utf-8"))


def check_listing(store, sku):
    """查 Amazon 上的实际状态"""
    if not os.path.isdir(SPAPI):
        return {"error": "sp-api 目录不可用"}
    sys.path.insert(0, SPAPI)
    try:
        import auth
    except ImportError as e:
        return {"error": f"auth 导入失败: {e}"}
    auth.set_store(store)
    qs = urllib.parse.urlencode({
        "marketplaceIds": MP_US,
        "includedData": "summaries,offers,fulfillmentAvailability,issues",
    })
    st, r = auth.request(
        "GET", f"/listings/2021-08-01/items/{auth.SELLER_ID}/{urllib.parse.quote(sku)}?{qs}")
    if st != 200:
        return {"error": f"HTTP {st}", "sku": sku}
    s = (r.get("summaries") or [{}])[0]
    errs = [i for i in (r.get("issues") or []) if i.get("severity") == "ERROR"]
    codes = []
    for e in errs:
        try:
            codes.append(int(e.get("code")))
        except (TypeError, ValueError):
            pass
    return {
        "sku": sku,
        "asin": s.get("asin"),
        "status": s.get("status") or [],
        "buyable": "BUYABLE" in (s.get("status") or []),
        "price": (r.get("offers") or [{}])[0].get("price", {}).get("amount"),
        "qty": (r.get("fulfillmentAvailability") or [{}])[0].get("quantity"),
        "img_bad": bool(IMG_BAD & set(codes)),
        "tm_bad": bool(TM_BAD & set(codes)),
        "error_codes": codes,
        "errors": [{"code": e.get("code"), "msg": (e.get("message") or "")[:120]} for e in errs],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sku", help="Amazon SKU（= ERP SPU 编码）")
    ap.add_argument("--asin")
    ap.add_argument("--store", default="zhangaodi")
    ap.add_argument("--price", type=float, default=0, help="不传则用 Amazon 上的实际价")
    ap.add_argument("--keyword", help="核心词（用于扫竞品视频），不传则用 SKU 反查的标题猜")
    ap.add_argument("--out")
    args = ap.parse_args()

    if not args.sku and not args.asin:
        print("需要 --sku 或 --asin")
        raise SystemExit(1)

    sku = args.sku
    md = ["# 首单品体检\n"]
    todo = []

    # ① 台账
    ledger = load_ledger()
    rec = ledger.get("skus", {}).get(sku) if sku else None
    if rec:
        md.append(f"## ① 台账状态\n")
        md.append(f"- 这个 SKU **已经出过单**：{rec.get('first_order_date')}")
        md.append(f"- 首次价格：{rec.get('first_price')}")
        md.append(f"- 类型：{'历史基线（老品）' if rec.get('baseline') else '检测到的首单'}")
        md.append(f"\n> 不是首单品。如果老板仍要复查，按常规运营处理。\n")
    else:
        md.append(f"## ① 台账状态\n")
        md.append(f"- 台账里**没有** `{sku}` → 如果订单里有单，这就是**首次出单**\n")

    # ② 链接状态
    info = check_listing(args.store, sku)
    md.append("## ② 链接状态\n")
    if "error" in info:
        md.append(f"- ⛔ {info['error']}")
        todo.append("确认 SKU 是否正确 / 卖家账号是否有权限")
    else:
        md.append(f"- ASIN：**{info['asin'] or '未分配'}**")
        md.append(f"- 状态：`{','.join(info['status']) or '空'}`")
        md.append(f"- 可购买：{'✅ 是' if info['buyable'] else '❌ 否'}")
        md.append(f"- 价格：${info['price'] or '—'}｜库存：{info['qty'] if info['qty'] is not None else '—'}")
        if info["img_bad"]:
            md.append(f"- ⚠️ **主图被压制**（错误码 {[c for c in info['error_codes'] if c in IMG_BAD]}）")
        if info["tm_bad"]:
            md.append(f"- ⚠️ **商标滥用**（18146）")
        if info["errors"]:
            md.append("\n  错误详情：")
            for e in info["errors"]:
                md.append(f"  - `{e['code']}` {e['msg']}")
        if not info["buyable"]:
            todo.append("先把链接修到 BUYABLE（否则开广告等于烧钱）")
        if info["img_bad"]:
            todo.append("换主图（纯白底、无文字 logo、≥1000px）")

    # ③ 广告决策
    price = args.price or (info.get("price") if isinstance(info, dict) else 0) or 0
    try:
        import ad_decision as A
        r = A.new_product_decision({
            "sku": sku, "asin": info.get("asin"), "price": float(price),
            "status": ",".join(info.get("status") or []),
            "main_img_ok": not info.get("img_bad", False),
        })
        md.append("\n## ③ 广告决策\n")
        md.append(f"- **结论**：{'✅ 该开' if r['open'] else '❌ 暂不开'}")
        for b in r.get("blockers") or []:
            md.append(f"- ⛔ {b}")
        for x in r.get("reasons") or []:
            md.append(f"- {x}")
        if r["open"]:
            md.append("\n| 类型 | 日预算 | bid | 备注 |")
            md.append("|---|---|---|---|")
            for g in r["groups"]:
                md.append(f"| {g['type']} | ${g['daily_budget']} | ${g['bid']} | {g['note']} |")
    except Exception as e:
        md.append(f"\n## ③ 广告决策\n- ⛔ 计算失败：{e}")

    # ④ 待办（agent 需调 MCP 的部分）
    md.append("\n## ④ 需要 agent 调 MCP 的部分\n")
    md.append("| 项 | 工具 | 做什么 |")
    md.append("|---|---|---|")
    asin_or_sku = info.get("asin") or sku
    md.append(f"| A+ 状态 | sellersprite/productSearch | 查 `{asin_or_sku}` 的 `badgeEbc` |")
    md.append(f"| 视频状态 | sellersprite/productSearch | 查 `badgeVideo`，顺便统计同类目视频率 |")
    md.append(f"| 广告现状 | linkfox sp/campaigns/list | 按 ASIN 过滤，看有没有活动、什么状态 |")
    md.append(f"| A+ 生图 | aigc/imageGenAsync | 如果 badgeEbc=N，按 build_aplus_plan 的 prompt 生成 |")
    md.append(f"| 竞品视频 | sellersprite/productSearch | 如果 badgeVideo=N，筛同类目有视频的做参考 |")

    if info.get("asin") and not (info.get("img_bad")):
        md.append("\n> A+ 和视频只有在链接 BUYABLE 且主图正常时才值得做，否则先修链接。")

    text = "\n".join(md)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        open(args.out, "w", encoding="utf-8").write(text)
        print(f"✅ 已写 {args.out}")
    print(text)


if __name__ == "__main__":
    main()
