---
name: amazon-first-order-boost
description: 亚马逊「首单品后续动作」—— 一个品从 0 单变成第一次出单后，给它补广告（放量/拓词）、A+ 内容、视频三件事。当老板说「这个品出单了帮我看看」「给这个首单品做后续」「出单了要不要加广告」「这个品要不要补 A+」「有没有视频」时触发。也支持批量扫昨天的首单品。
---

# 首单品后续动作（First Order Boost）

> **核心判断：品从 0 单变成有单，说明市场验证通过了，这时候才值得投入。**
> 没出过单的品做广告/A+/视频是浪费——你连它卖不卖得动都不知道。

---

## 何时用

| 场景 | 示例 |
|---|---|
| ✅ **用（单个品）** | "B0XXXX 出单了，帮我看看要不要加广告"、"这个首单品补个 A+" |
| ✅ **用（批量）** | "看看昨天有哪些品首次出单"、"扫一下最近出单的新品" |
| ✅ **用（只查一项）** | "这个品有没有 A+"、"同类目竞品有视频吗" |
| ❌ **不用** | 新品刚上架还没出单（先跑 `amazon-us-listing`）、广告日常调价（走广告 SOP） |

**当前模式：手动触发。** 老板指定品项后执行，不自动跑。

---

## 核心机制：首单台账

`config/first_order_ledger.json` 记录每个 SKU 第一次出单的日期。

```json
{
 "baseline_date": "2026-10-22",
 "skus": {
   "WBXZ-261023-GCP": {
     "first_order_date": "2026-10-22",
     "asin": "B0HNX6YW6H",
     "store": "zhangaodi",
     "market": "US",
     "first_price": 14.0,
     "baseline": true
   }
 }
}
```

| 字段 | 含义 |
|---|---|
| `baseline: true` | 初始化时从历史订单建的基线，**不报** |
| `baseline: false` | 真实检测到的首单，**要报** |

**判断逻辑**：台账里**没有**这个 SKU，但订单里有 → **首次出单**。

---

## 执行流程

### 场景 A：老板指定单个品

```bash
cd ~/.workbuddy/skills/amazon-first-order-boost/scripts

# 1. 确认是不是首单（查台账）
python -c "import json; d=json.load(open('../config/first_order_ledger.json',encoding='utf-8')); \
print(d['skus'].get('<SKU>', '台账无此 SKU → 是首单'))"

# 2. 查 ASIN + 状态（必须 BUYABLE）
#    用 sp-api/auth.py 拉 listings/2021-08-01/items/{sku}

# 3. 查 A+ / 视频状态（sellersprite）
#    toolName = "sellersprite/productSearch"
#    arguments = {"keyword": "<核心词>", "marketplace": "US", "size": 20}
#    → 找我们的 ASIN，看 badgeEbc / badgeVideo
#    → 同时统计同类目 video 率、ebc 率

# 4. 广告决策
python ad_decision.py --new <product.json>

# 5. 如果没 A+ → 出方案
python build_aplus_plan.py --input <listing.json> --out <报告路径>.md --json-out <prompts>.json

# 6. 如果没视频 → 扫竞品
python scan_competitor_video.py --json <sellersprite返回>.json --keyword "<核心词>" --out <报告>.md
```

### 场景 B：批量扫昨天的首单品

```bash
# 1. 先拉订单（用已有的 pull_sales 逻辑）
python ../../sp-api/pull_sales_*.py   # 或复用 sp-api 的订单拉取

# 2. 检测首单
python detect_first_orders.py --today 2026-10-23 --rows-glob "_sales_rows_*.json" \
    --out ../../reports/first_order/2026-10-23.md

# 3. 生成动作卡
python first_order_action.py --from-detected <上一步的JSON> \
    --out ../../reports/first_order/2026-10-23_actions.md
```

---

## 三个判断模块

### ⓿ 先做：链接全套面体检（12 项）

**首单后第一件事不是开广告，是把链接从头到尾看一遍。**

老板原话：「去检查链接各个方面看看有没有某个部位有大的差错，标题，五点，长描，亮点，变体设置，主图副图，a+，视频，价格，配送时间等」

| # | 检查项 | 判断标准 | 数据来源 |
|---|---|---|---|
| 1 | **标题** | 核心词在**前 80 字符**？有没有买家真会搜的品类词？ | listing attributes |
| 2 | **五点** | 讲的是「买家关心的」还是「工厂想说的」？首句能不能扫读？ | bullet_point |
| 3 | **长描述** | 有没有？还是空的？ | product_description |
| 4 | **亮点** | 五点首句是否带【】概括 | bullet_point |
| 5 | **变体设置** | 同款不同规格是否合并到一个父体（防 100730）| relationships |
| 6 | **主图** | 纯白底 / ≥1000px / 无文字 logo | issues: 18027/100581/100588/18644 |
| 7 | **副图** | ≥5 张？有没有场景、细节、尺寸、包装 | images |
| 8 | **A+** | `badgeEbc` = Y？ | sellersprite |
| 9 | **视频** | `badgeVideo` = Y？ | sellersprite |
| 10 | **价格** ⭐ | **跟前台同款比**（见下节）| 同款调研 |
| 11 | **配送时间** | FBM 承诺几天 vs 竞品 | offer |
| 12 | **Review** | 数量/评分差距 | listings/catalog |

**输出格式**：每项标 ✅ / ⚠️ / ❌，⚠️ 和 ❌ 必须给具体修法。

---

### ⓪-2 价格对比：必须跟前台同款比，不是跟"感觉"比

老板原话：「我的价格比前台竞品普遍高 10 美元，大家都比我便宜的很多那我的转化就会很受影响。这个时候你就要提醒出来，或者自己主动去帮我调整」

**找谁比 —— 必须是「同款」，不是「同类」**

> 老板原话：「颜色可以不一样，图案可以不一样，尺寸可以不一样，但是样式都是一样的」
> 「不管送不送赠品，送什么样的赠品都算同款！」
> 「不管是几件装，只要样子一样就是同款！记住！牢记！」

**允许不同**：颜色 / 图案 / 尺寸 / **几件装** / **赠品**
**必须一致**：结构形态 / 核心功能件（按扣≠拉链≠抽绳）/ 使用方式 / 关键识别特征 / 材质大类

**详细判定标准见**：`amazon-same-model-finder/references/criteria.md`

**做法**（完整流程见 `amazon-same-model-finder` skill）：
1. **从标题提核心词**（剥掉品牌/形容词/数量词）
2. **前台搜索**（优先 bsk 真实浏览器，兜底 curl）
3. **逐个看图判同款**（5 维度）
4. 算同款价格中位数 / 最低价 / 最高价
5. 我们的价格 vs 中位数：

| 我们 vs 中位 | 结论 |
|---|---|
| 高 >15% | 🔴 严重，转化必受影响，建议调价 |
| 高 5-15% | ⚠️ 需要理由支撑（更好材料/更多配件/A+ 更好）|
| ±5% | ✅ 正常 |
| 低 >5% | ⚠️ 可能定价过低，有涨价空间 |

6. **同时看**：同款里**卖得最好的那几个**是什么价位（不是最低价，是"卖得动的价"）

**⚠️ 价格口径**：必须算**含运费总价**（我们 FBM 是商品价 + 5.99 运费）。

---

## 竞品同款调研（核心能力）

### 老板的人工方法（必须照此实现）

> 1. 去亚马逊美国站前台搜索关键词
> 2. 这个词最好是产品相关性很高的词，这样搜出来才能有大多数链接是同款
> 3. 用眼睛去分辨链接的图片和 listing 页面，看看这个链接里卖的到底跟我想的是不是同款
> 4. 只有是同款才有参考的意义
> 5. 怎么确保关键词相关性高？**一般可以搜标题的核心关键词**
> 6. 我肯定会提供一个链接或 ASIN。判断是否同款就是**根据这个链接的 listing 和图片**判断的，前台的搜索词也是根据**这个链接的核心关键词**去找的

### 🎯 同款定义（老板原话，严格执行）

> 「颜色可以不一样，图案可以不一样，尺寸可以不一样，但是**样式都是一样的**」

| 维度 | 允许不同 | 必须一致 |
|---|---|---|
| 颜色 | ✅ | — |
| 图案/印花 | ✅ | — |
| 尺寸 | ✅ | — |
| **样式 / 款式 / 结构** | — | ✅ **必须一致** |

**"样式一致"落到可判定的 5 个维度**：

| 维度 | 怎么看 | 例子 |
|---|---|---|
| ① 部件组成 | 有几件、包含什么 | 3 个袋子+1 双手套 vs 3 个袋子 |
| ② 结构形态 | 方的/圆的/异形、几层、开合方式 | 方形带盖 vs 圆形无盖 |
| ③ 功能件 | 绑带/扣子/拉链/拉绳/吸盘 | 按扣 vs 拉链 |
| ④ 使用方式 | 套/挂/夹/贴/穿 | 水龙头挂式 vs 台面摆放 |
| ⑤ 关键结构特征 | 有没有那个"一眼认出"的特征 | 小鸟造型、鹿角、格子纹路 |

**不算同款的情况**：结构不同（如"挂门上"vs"放地上"）、功能件不同（如"按扣"vs"魔术贴"）、部件数量差异大（3 件装 vs 12 件装要标注）。

### 执行流程

```
输入：老板给的一个 ASIN（或链接）
  ↓
① 读该 ASIN 的完整 listing
   - 标题 / 五点 / 主图 / 全部副图 / 价格 / 变体 / 类目
  ↓
② 提取核心关键词
   - 从标题里剥掉：品牌名、形容词（Premium/Soft/Reusable/Upgraded）、数量词、颜色词
   - 保留：品类名词 + 材质 + 核心功能
   - 例："Reusable Self Sealing Potato and Onion Storage Bags" → "potato onion storage bags"
  ↓
③ 前台搜索这个词（拿前 20-30 个结果）
  - 工具：sellersprite/productSearch（keyword）
  - 或 linkfox amazon/search（真实前台）
  ↓
④ 逐个看主图，判断是否同款
  - 按上面 5 个维度比
  - 逐条记录：同款 / 不同款 + 理由
  ↓
⑤ 输出同款清单 + 价格对比 + 结论
```

### 判断同款时的诚实边界

**我能做**：
- ✅ 看图判断**结构/部件/形态**（这是视觉识别擅长的事）
- ✅ 对比多张图（主图 + 副图）交叉确认
- ✅ 给出判断理由（"都有按扣+3 件装+方形"）

**我做不到 / 会出错**：
- ⚠️ **图片模糊时**（<500px）判断会失准
- ⚠️ **细节差异**（缝线方式、扣子材质）看不出来
- ⚠️ **只有一张主图**时，可能把"相似款"误判为"同款"
- ⚠️ **文字描述与图片矛盾**时，以图为准但可能漏掉 listing 里的关键差异

**所以规则**：**每次同款调研都必须输出"判断依据表"，让老板能核对。** 不确定的标 `?` 而不是硬判。

---

### ① 广告

**先确认现值**：`sp/campaigns/list` 按 ASIN 过滤，看有没有活动、什么状态。

**如果没广告**（`ad_decision.new_product_decision`）：

| 条件 | 动作 |
|---|---|
| 售价 **≥ $20** 且同类目月销中位 ≥100 | 1 AUTO(bid $0.4) + 1 MANUAL(bid $0.4)，各 $4/天 |
| 售价 **≥ $20** 且月销中位 <100 | 1 AUTO + 1 MANUAL，bid 都 $0.2 |
| 售价 **< $20** | **只开 AUTO**，bid $0.2（低价品开手动必亏） |

**三道硬门槛**（不过就不开，开了等于烧钱）：
1. 有 ASIN
2. `status` 含 **BUYABLE**
3. 主图未被压制（无 18027/100581/100588/18644）

**如果已有广告**（`ad_decision.expand_decision`）：拉近 14 天搜索词报表，按下表处理：

| 条件 | 动作 |
|---|---|
| 出单 ≥2 且 ACoS ≤30% | 加精准组 / 提 bid |
| 花费 ≥$2 且 0 单 | **否词（精准否定）** |
| CTR ≥0.5% 且 CVR ≥5% | 提 bid 抢位 |
| 曝光 ≥100 且 0 点击 | **否词**（相关性差） |
| 其他 | 观察 |

### ② A+ 内容

**先查 `badgeEbc`**：`Y` 就跳过，`N` 才做。

`build_aplus_plan.py` 输出标准 7 模块：

| # | 类型 | 尺寸 | 内容来源 |
|---|---|---|---|
| 1 | banner | 970×600 | 产品名 + 第一条五点的主张 |
| 2-4 | three_img | 300×300 ×3 | 前三条五点各拆一个卖点 |
| 5 | wide_banner | 970×300 | 场景图 |
| 6 | compare | 970×300 | 材质/数量/配件对比 |
| 7 | specs | 970×300 | 规格清单 |

**生图**（linkfox）：
```json
{"toolName": "aigc/imageGenAsync",
 "arguments": {"prompt": "<模块prompt>", "images": ["<产品主图URL>"], "size": "1536x1024"}}
→ taskId → {"toolName":"aigc/taskQuery","arguments":{"taskId":"..."}} 轮询到 SUCCESS
→ resultList[0].url 下载
```

**prompt 必须写清**：
- 尺寸/比例（如"aspect ratio 970x600 horizontal"）
- 产品占位（"product on the LEFT two-thirds, clean negative space on the RIGHT third for headline"）
- `no text, no logo, no watermark, photorealistic`

### ③ 视频

**先查 `badgeVideo`**：`Y` 就跳过。

`scan_competitor_video.py` 输出：
- 同类目样本数、视频率、A+ 率
- 有视频的竞品清单（ASIN + 链接 + 月销 + BSR）
- 结论：视频是标配/加分项/差异化

**判断口径**：

| 视频率 | 结论 |
|---|---|
| ≥50% | 标配 → 必须配 |
| 20-50% | 加分项 → 有预算就做 |
| <20% | 稀缺 → 做了就是差异化 |

| A+ 率 | 结论 |
|---|---|
| ≥60% | 标配 → 不配明显劣势 |
| 30-60% | 建议配 |
| <30% | 做了能拉开差距 |

**视频抓取**：sellersprite 只给「有没有」和 ASIN，**视频文件本身抓不到**（Amazon 视频地址要页面解析）。需要抓取时单独处理。

---

## 输出物

每个首单品一份 Markdown 动作卡：

```markdown
## <SKU> — <store>-<market>
- ASIN：B0XXXX
- 首单价：$34.00

### ① 广告
<现状 + 建议>

### ② A+ / 视频
<badgeEbc / badgeVideo 状态 + 结论>

### ✅ 动作清单
- [ ] ① 广告：...
- [ ] ② A+：...
- [ ] ③ 视频：...
```

报告落点：`.workbuddy/memory/reports/first_order/`

---

## 踩坑

| 坑 | 说明 |
|---|---|
| **台账必须先初始化** | 第一次跑要 `--init`，把历史订单全写进去，否则老品会被误报为首单 |
| **Cancelled / Refunded 不算首单** | 脚本会剔除。实测有 4 个 SKU 只有取消订单，不算出过单 |
| **只有取消订单 = 有需求但转化失败** | 这是另一个信号，值得单独看（可能价格/主图/描述有问题）|
| **SP-API 状态读 `summaries[0].status`** | 顶层 `status` 字段是 None |
| **BUYABLE 判断** | 数组里含 `BUYABLE` 才算，只有 `DISCOVERABLE` = 买家买不了 |
| **父体不该有 BUYABLE** | 父体无 offer，只有 DISCOVERABLE 是正常的，不算问题 |
| **sellersprite 返回字段名** | `badgeVideo` / `badgeEbc`，也有一份在 `badge{}` 里 |
| **生图必传参考图** | 不传会失败；prompt 要显式写「不要照抄参考图构图」 |
| **低价品不开手动** | 售价 <$20 开手动广告，ACoS 必爆 |

---

## 台账现状（2026-10-23）

- **65 个 SKU**（全部为历史出过单的，`baseline: true`）
- 基线日期：`2026-10-22`
- 昨天上架的 22 个新品**不在台账**（还没出单）→ 出单时会正确触发

---

## 快速入口

```bash
cd ~/.workbuddy/skills/amazon-first-order-boost/scripts

# 给一个 SKU，跑完能自动的部分（台账/链接状态/广告决策）
python run_one.py --sku CHT20260822149

# 指定价格和核心词
python run_one.py --sku LRR20261022004 --price 34 --keyword "heated slippers"
```

`run_one.py` 输出四段：①台账状态 ②链接状态 ③广告决策 ④需要 agent 调 MCP 的待办。
**sellersprite / aigc 的调用由 agent 完成**（脚本无法直连 MCP）。

---

## 相关脚本

| 脚本 | 用途 |
|---|---|
| `detect_first_orders.py` | 首单检测（对比台账）|
| `first_order_action.py` | 生成动作卡 |
| `ad_decision.py` | 广告决策（新品开组 / 拓词否词）|
| `build_aplus_plan.py` | A+ 7 模块方案 + 生图 prompt |
| `scan_competitor_video.py` | 竞品视频/A+ 扫描 |

依赖：`sp-api/auth.py`（SP-API 凭证）、linkfox MCP（sellersprite / aigc）。
