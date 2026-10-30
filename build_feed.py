#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新闻订阅源聚合器
=================================================================
把多个公开的 RSS / Atom / JSON 源聚合成一个小程序可直接消费的
feed.json，放到任意静态托管（GitHub Pages / 对象存储 / 自己的服务器）
上，小程序端只要在「设置 → 新闻订阅源」里填这个地址即可实现每日自动更新。

特点：
  * 只用 Python 3 标准库，不需要 pip install
  * RSS 2.0 / Atom / JSON 三种格式自动识别
  * 失败的单源不影响整体（跳过并计数）
  * 自动分类（政策 / 工厂 / 资本 / 数据 / 品牌），规则与小程序端
    utils/newsFeed.js 的 CATEGORY_RULES 保持一致
  * 按 (标题, 链接) 去重、只保留最近 N 天、最多 N 条

用法：
  python3 build_feed.py                  # 使用同目录 sources.json
  python3 build_feed.py -c my.json -o out.json
  python3 build_feed.py --dry-run        # 只打印结果不写文件

也可以直接定时跑：
  */30 * * * *  cd /path/to/news-feed && /usr/bin/python3 build_feed.py
"""

import argparse
import html
import io
import json
import os
import re
import sys
import time
import ssl
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

# ------------------------------------------------------------------
# 分类关键词（中文与 utils/newsFeed.js 的 CATEGORY_RULES 对齐；
# 英文词为本项目扩展——主要垂类源是英文媒体，不补英文会导致清一色落到 brand）
# ------------------------------------------------------------------
CATEGORY_RULES = [
    ("policy", [
        "法规", "标准", "国标", "政策", "监管", "备案", "许可", "准入", "团体标准",
        "进口登记", "农业农村部", "市监", "食品安全", "GB/T", "征求意见", "整治",
        "处罚", "禁用", "限用", "管理办法", "条例", "新规", "实施", "公告", "目录",
        "规范", "合规", "标签规定", "饲料管理",
        # 英文
        "regulation", "regulatory", "compliance", "labeling", "labelling",
        "fda", "aafco", "feed regulation", "safety standard", "traceability",
        "recall", "ban", "mandate", "policy", "lawsuit", "declar", "certif",
    ]),
    ("factory", [
        "产能", "工厂", "代工", "产线", "投产", "扩产", "新建", "智能工厂", "基地",
        "供应链", "物流", "仓储", "产能规划", "gmp", "GMP", "车间",
        # 英文
        "manufactur", "production", "facility", "plant", "capacity", "factory",
        "supply chain", "logistics", "warehouse", "co-manufactur", "co-packer",
        "ingredient handling", "extruder", "production line", "plant-based",
    ]),
    ("capital", [
        "融资", "轮", "IPO", "上市", "投资", "并购", "收购", "估值", "股权",
        "募资", "港交所", "创业板", "财报", "营收", "净利", "业绩", "股价", "基金",
        # 英文
        "acquisition", "acquire", "merger", "merger", "funding", "raise",
        "investment", "invest", "valuation", "stake", "series a", "series b",
        "ipo", "revenue", "earnings", "profit", "shares", "expansion into",
        "partner", "partnership", "joint venture",
    ]),
    ("data", [
        "白皮书", "数据", "报告", "规模", "亿元", "增长", "渗透率", "占比", "调研",
        "统计", "出货量", "复合增长", "市场规模", "销量", "消费额",
        # 英文
        "report", "survey", "study", "outlook", "market size", "forecast",
        "data", "statistics", "growth", "percent", "consumption", "spending",
        "opportunity", "trend", "analysis", "insight",
    ]),
    ("brand", [
        "发布", "上新", "新品", "联名", "签约", "代言", "渠道", "618", "双11",
        "预售", "涨价", "调价", "召回", "配方升级", "活动", "直播", "门店",
        "战略", "合作",
        # 英文
        "launch", "unveil", "introduc", "debut", "new product", "rebrand",
        "packaging", "formula", "flavor", "flavour", "treat", "snack",
        "brand", "campaign", "signing", "partnership", "collab",
        "cat food", "dog food", "kibble", "pet food",
    ]),
]

DEFAULT_CATEGORY = "brand"

# ------------------------------------------------------------------
# 关键词过滤表
# ------------------------------------------------------------------
# 设计要点（踩过的坑）：
#   1) 早期版本把"进口/出口/标准/政策/电商"这类泛化词放进 includeAny，
#      结果综合财经源的时事新闻全被放行（"海南自贸港再迎政策支持"也算命中），
#      真正的宠物行业新闻反而因为不含中文关键词被误杀。
#   2) 因此拆成三层：
#      includeAny —— 必须命中的「垂类强词」，只保留宠物/食品行业的专属词。
#      includeAll —— 可选的「宽泛词」，配合 tier:strong 才生效。
#      excludeAny —— 命中即丢弃，用于排除明显跑题的条目。
#   3) 源级别用 tier 区分：
#      tier: "vertical" —— 本身就是垂类媒体，整源放行，不做关键词过滤。
#      tier: "general"  —— 泛资讯源，必须命中 includeAny 才保留。
#   4) 关键词表同时含中英文，因为 Petfood Industry 等源是英文。
FILTER_INCLUDE_ANY = [
    # 宠物主体
    "宠物", "猫", "狗", "犬", "猫粮", "狗粮", "主粮", "冻干", "罐头", "零食",
    "宠物食品", "宠物经济", "宠物行业", "宠物产业", "宠物医疗", "宠物用品",
    "宠物营养", "养宠", "萌宠", "铲屎官", "猫舍", "犬舍", "猫用", "犬用",
    # 英文
    "pet food", "petfood", "pet industry", "pet nutrition", "pet supplement",
    "pet treat", "petcare", "pet care", "companion animal", "dog food", "cat food",
    "kibble", "pet owner", "pet brand", "pet manufacturer", "animal nutrition",
    "pet food industry", "aafco", "fda", "wet food", "dry food", "treats for",
]

# 泛化词：只有和强词同时出现才算命中（用于 rescue 逻辑）
FILTER_INCLUDE_ALL = [
    "饲料", "代工", "食品", "营养", "配料", "原料", "烘焙", "会展", "展会",
    "电商", "天猫", "京东", "零售", "工厂", "产能", "供应链", "白皮书",
    "海关", "进出口", "标准", "监管", "政策", "法规", "备案", "收购", "投资", "融资",
    "market", "industry", "manufactur", "supply chain", "retail", "e-commerce",
    "trade", "regulation", "label", "ingredient", "consumer", "growth",
]

# 命中即丢弃（明显跑题）
FILTER_EXCLUDE_ANY = [
    "球队", "球员", "比赛", "演唱会", "电影票房", "明星", "离婚", "讣告",
    "football", "nba", "movie", "celebrity", "obituary",
]

UA = ("Mozilla/5.0 (compatible; CatFoodFeedBot/1.0; "
      "+https://github.com/catfood-analyzer) Python-urllib")

MAX_ITEMS = 120          # 最多输出多少条
MAX_AGE_DAYS = 45        # 只保留最近多少天的
TIMEOUT = 20             # 单源超时（秒）
MIN_TITLE_LEN = 4        # 标题过短的条目丢弃（多为导航/版权行）


# ------------------------------------------------------------------
# 工具函数
# ------------------------------------------------------------------
def local_name(tag):
    """去掉 XML 命名空间前缀：'{http://www.w3.org/2005/Atom}entry' -> 'entry'"""
    return tag.split("}", 1)[1] if "}" in tag else tag


def strip_tags(s):
    """去掉 HTML 标签并反转义实体，压成纯文本摘要"""
    if not s:
        return ""
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s, flags=re.S)
    s = html.unescape(s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)   # 二次反转义：处理 &lt; 这类双重编码
    s = re.sub(r"\s+", " ", s).strip()
    return s


def classify(text, fallback=DEFAULT_CATEGORY):
    """按关键词把一条新闻归入 5 个分类之一"""
    t = (text or "")
    for key, words in CATEGORY_RULES:
        for w in words:
            if w in t:
                return key
    return fallback


def parse_date(raw):
    """把各种日期写法归一成 YYYY-MM-DD"""
    if not raw:
        return ""
    s = str(raw).strip()
    # RFC822 / RFC2822（RSS pubDate）
    try:
        dt = parsedate_to_datetime(s)
        if dt:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone().strftime("%Y-%m-%d")
    except Exception:
        pass
    # ISO8601（Atom）
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return m.group(0)
    m = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", s)
    if m:
        return "%s-%02d-%02d" % (m.group(1), int(m.group(2)), int(m.group(3)))
    m = re.search(r"(\d{4})[-/年](\d{1,2})", s)
    if m:
        return "%s-%02d" % (m.group(1), int(m.group(2)))
    return ""


def date_from_url(url):
    """
    有些源（如 petworldwide.net）不在 item 里给 pubDate，
    只把日期写在链接路径上：/content-1/news/2026/10/plus/xxx.html
    这里做兜底提取，否则这类条目会因"无日期"被时间窗过滤掉。
    """
    if not url:
        return ""
    m = re.search(r"/(20\d{2})[-/](\d{1,2})(?:[-/](\d{1,2}))?(?:/|$)", url)
    if not m:
        return ""
    y, mo, d = m.group(1), int(m.group(2)), m.group(3)
    if not (1 <= mo <= 12):
        return ""
    if d:
        dd = int(d)
        if not (1 <= dd <= 31):
            return ""
        return "%s-%02d-%02d" % (y, mo, dd)
    return "%s-%02d" % (y, mo)


def fetch(url):
    """抓取一个 URL，返回文本"""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, "
                  "application/json, text/xml, */*",
    })
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
        raw = resp.read()
    for enc in ("utf-8", "gbk", "gb18030", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


# ------------------------------------------------------------------
# 解析器
# ------------------------------------------------------------------
def parse_feed(text):
    """自动识别格式，返回原始条目列表"""
    s = (text or "").strip()
    if not s:
        return []
    if s[0] in "{[":
        return parse_json(s)
    low = s[:4000].lower()
    # HTML 页面（源失效/被重定向）直接判失败，不要把 HTML 行当新闻
    if low.startswith("<!doctype html") or low.startswith("<html"):
        raise ValueError("返回的是 HTML 页面，不是订阅源（该源可能已失效）")
    if "<rss" in low or "<feed" in low or "<item" in low or "<entry" in low:
        return parse_rss(s)
    # 有些源直接给纯文本行
    return parse_lines(s)


def parse_json(s):
    try:
        data = json.loads(s)
    except Exception as e:
        raise ValueError("JSON 解析失败: %s" % e)
    arr = None
    if isinstance(data, list):
        arr = data
    elif isinstance(data, dict):
        for k in ("items", "data", "list", "articles", "news", "result", "records", "results"):
            if isinstance(data.get(k), list):
                arr = data[k]
                break
    if arr is None:
        raise ValueError("JSON 结构无法识别（需 items/data/list 数组）")
    return [x for x in arr if isinstance(x, dict)]


def _first(node, names):
    """在 XML 节点里按本地名找第一个非空子节点文本"""
    for child in node:
        if local_name(child.tag) in names:
            txt = "".join(child.itertext()).strip()
            if txt:
                return txt
    return ""


def parse_rss(s):
    try:
        root = ET.fromstring(s)
    except ET.ParseError as e:
        raise ValueError("XML 解析失败: %s" % e)
    # 根节点必须是真正的 RSS/Atom，否则多半是抓到了 HTML 页面
    if local_name(root.tag) not in ("rss", "feed", "rdf", "channel"):
        raise ValueError("根节点是 <%s>，不是 RSS/Atom 文档" % local_name(root.tag))
    out = []
    for node in root.iter():
        if local_name(node.tag) not in ("item", "entry"):
            continue
        title = strip_tags(_first(node, ("title",)))
        if not title:
            continue
        link = ""
        for child in node:
            if local_name(child.tag) == "link":
                link = (child.get("href") or child.get("url") or
                        "".join(child.itertext()).strip() or "")
                if link:
                    break
        if not link:
            link = _first(node, ("guid", "id"))
        summary = strip_tags(_first(node, ("description", "summary", "encoded", "content")))
        date = parse_date(_first(node, ("pubDate", "published", "updated", "date", "created")))
        cat = strip_tags(_first(node, ("category",)))
        out.append({
            "title": title,
            "summary": summary,
            "url": link,
            "date": date,
            "category": cat,
        })
    return out


def parse_lines(s):
    """极简兜底：每行一条，取 '标题 | 摘要 | 链接 | 日期' 形式"""
    out = []
    for line in s.splitlines():
        line = line.strip()
        if not line or len(line) < MIN_TITLE_LEN:
            continue
        parts = [p.strip() for p in line.split("|")]
        out.append({
            "title": parts[0],
            "summary": parts[1] if len(parts) > 1 else "",
            "url": parts[2] if len(parts) > 2 else "",
            "date": parse_date(parts[3] if len(parts) > 3 else ""),
            "category": "",
        })
    return out


# ------------------------------------------------------------------
# 归一化
# ------------------------------------------------------------------
def pick(d, names):
    for k in names:
        v = d.get(k)
        if v not in (None, "", []):
            return v
    return ""


def normalize(raw, src):
    """把各源条目统一成小程序认识的字段"""
    title = strip_tags(str(pick(raw, ("title", "headline", "name", "subject"))))
    if not title or len(title) < MIN_TITLE_LEN:
        return None
    summary = strip_tags(str(pick(raw, (
        "summary", "description", "content", "excerpt", "abstract",
        "digest", "desc", "body", "content:encoded"))))
    if len(summary) > 220:
        summary = summary[:220] + "…"
    url = str(pick(raw, ("url", "link", "guid", "permalink", "href")))
    date = parse_date(str(pick(raw, (
        "date", "pubDate", "published_at", "published", "created",
        "time", "pubdate", "updated"))))
    if not date:
        # 兜底：从链接路径里抠日期（部分源只在 URL 上标日期）
        date = date_from_url(url)
    raw_cat = str(pick(raw, ("category", "type", "tag", "channel"))).strip().lower()
    valid = {k for k, _ in CATEGORY_RULES}
    category = raw_cat if raw_cat in valid else ""
    if not category:
        category = classify(title + " " + summary, src.get("category") or DEFAULT_CATEGORY)
    return {
        "title": title,
        "summary": summary,
        "url": url,
        "date": date,
        "category": category,
        "source": src.get("name") or "订阅源",
    }


# ------------------------------------------------------------------
# 主流程
# ------------------------------------------------------------------
def build(config, out_path, dry_run=False):
    sources = config.get("sources", [])
    cutoff = (datetime.now() - timedelta(days=MAX_AGE_DAYS)).strftime("%Y-%m-%d")

    flt = config.get("filter") or {}
    filter_on = flt.get("enabled", False)
    # 关键词表：优先读配置文件里的自定义表，没配就用内置的三层词表
    strong_words = [w.lower() for w in (flt.get("includeAny") or FILTER_INCLUDE_ANY) if w]
    broad_words = [w.lower() for w in (flt.get("includeAll") or FILTER_INCLUDE_ALL) if w]
    exclude_words = [w.lower() for w in (flt.get("excludeAny") or FILTER_EXCLUDE_ANY) if w]

    merged = []
    seen = set()
    stats = []
    filtered_out = 0

    def item_text(m):
        return (m["title"] + " " + m["summary"]).lower()

    for src in sources:
        if not src.get("enabled", True):
            stats.append((src.get("name") or src.get("url") or "?", "跳过", "enabled=false"))
            continue
        url = (src.get("url") or "").strip()
        name = src.get("name") or url
        if not url:
            stats.append((name, "跳过", "未配置 url"))
            continue
        # tier: vertical = 垂类媒体（本身就是宠物/食品行业），整源放行
        # tier: general  = 泛资讯源，必须命中关键词才保留
        tier = (src.get("tier") or "general").lower()
        try:
            text = fetch(url)
            raws = parse_feed(text)
        except Exception as e:
            stats.append((name, "失败", str(e)[:120]))
            continue

        kept = 0
        src_filtered = 0
        for raw in raws:
            item = normalize(raw, src)
            if not item:
                continue
            if item["date"] and item["date"] < cutoff:
                continue
            if filter_on and tier != "vertical":
                t = item_text(item)
                if any(x in t for x in exclude_words):
                    src_filtered += 1
                    continue
                hit = any(w in t for w in strong_words)
                if not hit and broad_words:
                    # 宽泛词只在同时命中至少一个强词时才有效
                    hit = any(w in t for w in broad_words) and any(
                        w in t for w in strong_words)
                if not hit:
                    src_filtered += 1
                    continue
            key = (item["title"], item["url"])
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
            kept += 1
        filtered_out += src_filtered
        extra = "（过滤掉 %d 条）" % src_filtered if src_filtered else ""
        stats.append((name, "成功", "%d 条%s" % (kept, extra)))
        time.sleep(0.4)  # 轻微限速，别把人家源打挂

    # 日期倒序（无日期的排最后），再截断
    merged.sort(key=lambda x: (x["date"] or "0000-00-00"), reverse=True)
    merged = merged[:MAX_ITEMS]

    print("=" * 62)
    print("订阅源聚合完成")
    print("=" * 62)
    for name, status, detail in stats:
        print("  [%s] %-28s %s" % (status, name[:28], detail))
    print("-" * 62)
    print("  合计输出 %d 条（去重后 / 最近 %d 天 / 上限 %d）"
          % (len(merged), MAX_AGE_DAYS, MAX_ITEMS))
    cats = {}
    for m in merged:
        cats[m["category"]] = cats.get(m["category"], 0) + 1
    print("  分类分布：" + "，".join("%s %d" % (k, v) for k, v in sorted(cats.items())))
    print("=" * 62)

    if dry_run:
        for m in merged[:5]:
            print("  · [%s] %s | %s" % (m["category"], m["date"], m["title"][:40]))
        return merged

    with io.open(out_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(merged, ensure_ascii=False, indent=2))
    print("  已写入：%s" % out_path)
    return merged


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="新闻订阅源聚合器")
    ap.add_argument("-c", "--config", default=os.path.join(here, "sources.json"),
                    help="订阅源配置文件路径")
    ap.add_argument("-o", "--out", default=os.path.join(here, "feed.json"),
                    help="输出 feed.json 路径")
    ap.add_argument("--dry-run", action="store_true", help="只打印不写文件")
    args = ap.parse_args()

    if not os.path.exists(args.config):
        print("找不到配置文件：%s" % args.config, file=sys.stderr)
        return 1
    with io.open(args.config, encoding="utf-8") as f:
        config = json.load(f)

    build(config, args.out, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
