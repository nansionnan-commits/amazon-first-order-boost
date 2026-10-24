#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
首单检测 —— 找出「之前没出过单、现在出单了」的品

为什么需要：一个品首次出单，说明市场验证通过了，这时候要给它补后续动作
（广告放量/拓词、补 A+、补视频）。之前没出单时做这些是浪费。

机制：
  1. 台账 config/first_order_ledger.json 记录每个 SKU 的首次出单日期
  2. 每天拉订单，跟台账对比
  3. 台账里没有、但订单里有 → 首次出单
  4. 写进台账（只写一次，以后不再报）

用法：
  # 首次初始化（把历史订单全部建基线，不当作新出单）
  python detect_first_orders.py --init --rows _sales_rows_1010.json,_sales_rows_1022.json

  # 日常：只查某天的新出单
  python detect_first_orders.py --today 2026-10-22 --rows _sales_rows_1022.json

  # 输出报告
  python detect_first_orders.py --today 2026-10-22 --rows xxx.json --out reports/first_order/2026-10-22.md
"""
import argparse
import glob
import json
import os
import re
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LEDGER = os.path.join(ROOT, "config", "first_order_ledger.json")

BAD_STATUS = {"cancelled", "canceled", "refunded"}
MK = {"Amazon.com": "US", "Amazon.ca": "CA", "Amazon.com.mx": "MX",
      "Amazon.com.au": "AU", "Amazon.com.au ": "AU"}


def _load():
    if not os.path.exists(LEDGER):
        return {"_desc": "SKU 首单台账：记录每个 SKU 第一次出单日期，用于识别「新出单品」",
                "baseline_date": None, "skus": {}}
    try:
        d = json.load(open(LEDGER, encoding="utf-8"))
        d.setdefault("skus", {})
        return d
    except (json.JSONDecodeError, OSError):
        return {"_desc": "首单台账（读取失败已重建）", "baseline_date": None, "skus": {}}


def _save(d):
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    tmp = LEDGER + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, LEDGER)


def load_rows(paths):
    """读订单流水，剔除取消/退款"""
    rows = []
    for p in paths:
        if not os.path.exists(p):
            continue
        try:
            data = json.load(open(p, encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for r in data:
            if not isinstance(r, dict):
                continue
            if (r.get("status") or "").lower() in BAD_STATUS:
                continue
            if not r.get("sku"):
                continue
            rows.append(r)
    return rows


def init_baseline(rows):
    """首次初始化：把历史订单全写进台账（不当作新出单）"""
    d = _load()
    dates = sorted({r.get("day") for r in rows if r.get("day")})
    cnt = 0
    for r in rows:
        sku = r["sku"]
        if sku in d["skus"]:
            continue
        d["skus"][sku] = {
            "first_order_date": r.get("day"),
            "asin": r.get("asin"),
            "store": r.get("store"),
            "market": MK.get(r.get("channel"), r.get("channel")),
            "first_price": r.get("item_price"),
            "baseline": True,
        }
        cnt += 1
    d["baseline_date"] = dates[-1] if dates else time.strftime("%Y-%m-%d")
    _save(d)
    return cnt, d["baseline_date"]


def detect(rows, day=None):
    """
    返回首次出单的 SKU 列表。
    day 为 None 时，按订单里所有日期判；否则只判该日
    """
    d = _load()
    seen, newbies = set(), []
    for r in rows:
        if day and r.get("day") != day:
            continue
        sku = r["sku"]
        if sku in seen:
            continue
        seen.add(sku)
        if sku in d["skus"]:
            continue          # 台账有 → 不是首单
        newbies.append({
            "sku": sku,
            "asin": r.get("asin"),
            "store": r.get("store"),
            "market": MK.get(r.get("channel"), r.get("channel")),
            "day": r.get("day"),
            "price": r.get("item_price"),
            "qty": r.get("qty"),
            "currency": r.get("currency"),
        })
    newbies.sort(key=lambda x: (x["store"], x["market"], x["sku"]))
    return newbies, d


def commit(newbies, d):
    """把首单品写进台账"""
    for n in newbies:
        d["skus"][n["sku"]] = {
            "first_order_date": n["day"],
            "asin": n["asin"],
            "store": n["store"],
            "market": n["market"],
            "first_price": n["price"],
            "baseline": False,     # 真实检测到的首单
        }
    _save(d)


def to_markdown(newbies, day, out_path=None):
    mk = [f"# 新出单品（首单）：{day}\n"]
    if not newbies:
        mk.append("_今天没有首次出单的品。_\n")
    else:
        mk.append(f"共 **{len(newbies)}** 个品首次出单，说明市场验证通过，需要补后续动作。\n")
        mk.append("| # | SKU | ASIN | 站点 | 首单价格 |")
        mk.append("|---|---|---|---|---|")
        for i, n in enumerate(newbies, 1):
            mk.append(f"| {i} | `{n['sku']}` | {n['asin'] or '-'} | "
                      f"{n['store']}-{n['market']} | {n['currency'] or ''}{n['price']} |")
        mk.append("")
        mk.append("## 下一步（每品三项）\n")
        mk.append("1. **广告**：现在有没有广告？有 → 看表现决定加预算/拓词；没有 → 按 `ad_decision` 开组")
        mk.append("2. **A+**：查 `badgeEbc`，没有就出 A+ 方案（`build_aplus_plan.py`）")
        mk.append("3. **视频**：查 `badgeVideo`，没有就扫竞品视频作参考（`scan_competitor_video.py`）")
    text = "\n".join(mk)
    if out_path:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        open(out_path, "w", encoding="utf-8").write(text)
    return text


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", help="订单 JSON 路径，逗号分隔")
    ap.add_argument("--rows-glob", default="_sales_rows_*.json", help="或按通配符取全部")
    ap.add_argument("--init", action="store_true", help="初始化基线（历史订单全算已出单）")
    ap.add_argument("--today", help="只判这一天的首单")
    ap.add_argument("--out", help="Markdown 输出")
    ap.add_argument("--dry-run", action="store_true", help="只输出不写台账")
    args = ap.parse_args()

    paths = [p.strip() for p in args.rows.split(",")] if args.rows else sorted(glob.glob(args.rows_glob))
    if not paths:
        print("❌ 没找到订单文件")
        raise SystemExit(1)

    rows = load_rows(paths)
    print(f"读取订单 {len(rows)} 行（已剔取消/退款），来自 {len(paths)} 个文件")

    if args.init:
        cnt, base = init_baseline(rows)
        print(f"✅ 基线已建：新写入 {cnt} 个 SKU，基线日期 {base}")
        print(f"   台账总计 {len(_load()['skus'])} 个 SKU")
        raise SystemExit(0)

    newbies, d = detect(rows, args.today)
    text = to_markdown(newbies, args.today or "全部", args.out)
    print(text)

    if newbies and not args.dry_run:
        commit(newbies, d)
        print(f"\n✅ 已把 {len(newbies)} 个首单品写入台账（不会重复报）")
    elif args.dry_run:
        print("\n（dry-run，未写台账）")
