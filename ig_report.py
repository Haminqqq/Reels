#!/usr/bin/env python3
"""抓取 Instagram 公開資料並產生分析報告（在自己的電腦上執行）。

用法：
    python ig_report.py haminqqq --reel DfZe4PRyT7l
    python ig_report.py haminqqq --reel DfZe4PRyT7l --compare 帳號A 帳號B
    python ig_report.py haminqqq --login haminqqq      # 匿名被擋時才用

輸出：data/report.md（貼給 Claude 看的）與 data/report.json（原始資料）。
"""
import argparse
import json
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import timedelta, timezone
from pathlib import Path

TW = timezone(timedelta(hours=8))
WEEKDAYS = "一二三四五六日"
KIND_LABEL = {"reel": "Reels/影片", "carousel": "輪播", "photo": "單張照片"}


def post_kind(typename, is_video):
    if is_video:
        return "reel"
    return "carousel" if typename == "GraphSidecar" else "photo"


def post_to_dict(post):
    """把 instaloader 的 Post 轉成單純的 dict。"""
    def safe(name):
        try:
            return getattr(post, name)
        except Exception:
            return None

    local = post.date_utc.replace(tzinfo=timezone.utc).astimezone(TW)
    caption = post.caption or ""
    return {
        "shortcode": post.shortcode,
        "url": f"https://www.instagram.com/p/{post.shortcode}/",
        "owner": safe("owner_username"),
        "date": local.strftime("%Y-%m-%d %H:%M"),
        "weekday": local.weekday(),
        "hour": local.hour,
        "kind": post_kind(post.typename, post.is_video),
        "likes": safe("likes"),
        "comments": safe("comments"),
        "views": safe("video_play_count") or safe("video_view_count"),
        "duration": safe("video_duration"),
        "pinned": bool(safe("is_pinned")),
        "caption": caption,
        "hashtags": list(safe("caption_hashtags") or []),
        "location": getattr(safe("location"), "name", None),
    }


def summarize(profile, posts):
    """純計算：輸入帳號資料與貼文 dict，輸出統計。"""
    followers = profile.get("followers") or 0
    by_kind = defaultdict(list)
    for p in posts:
        by_kind[p["kind"]].append(p)

    def avg(items, key):
        vals = [p[key] for p in items if isinstance(p.get(key), (int, float)) and p[key] >= 0]
        return round(statistics.mean(vals), 1) if vals else None

    kinds = {}
    for kind, items in by_kind.items():
        likes, comments = avg(items, "likes"), avg(items, "comments")
        rate = None
        if followers and likes is not None:
            rate = round((likes + (comments or 0)) / followers * 100, 2)
        kinds[kind] = {
            "count": len(items),
            "avg_likes": likes,
            "avg_comments": comments,
            "avg_views": avg(items, "views"),
            "engagement_rate_pct": rate,
        }

    def score(p):
        return (p.get("likes") or 0) + (p.get("comments") or 0)

    ranked = sorted(posts, key=score, reverse=True)

    slots = defaultdict(list)
    for p in posts:
        slots[(p["weekday"], p["hour"])].append(score(p))
    best_slots = sorted(
        ({"weekday": w, "hour": h, "posts": len(v), "avg_engagement": round(statistics.mean(v), 1)}
         for (w, h), v in slots.items()),
        key=lambda s: s["avg_engagement"], reverse=True)[:5]

    per_week = None
    if len(posts) >= 2:
        dates = sorted(p["date"][:10] for p in posts)
        from datetime import date
        span = (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days
        if span > 0:
            per_week = round(len(posts) / span * 7, 2)

    tags = Counter(t.lower() for p in posts for t in p["hashtags"])
    return {
        "kinds": kinds,
        "posts_per_week": per_week,
        "top_posts": ranked[:5],
        "bottom_posts": ranked[-5:][::-1] if len(ranked) > 5 else [],
        "best_slots": best_slots,
        "top_hashtags": tags.most_common(15),
    }


def short(text, n=60):
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= n else text[:n] + "…"


def fmt(v):
    return "—" if v is None else f"{v:,}" if isinstance(v, (int, float)) else str(v)


def render_account(acc):
    p, s = acc["profile"], acc["summary"]
    out = [f"## @{p['username']}", ""]
    out.append(f"- 追蹤者 {fmt(p['followers'])}｜追蹤中 {fmt(p['followees'])}｜貼文 {fmt(p['mediacount'])}")
    out.append(f"- 自介：{short(p.get('biography'), 200) or '（空白）'}")
    if p.get("external_url"):
        out.append(f"- 連結：{p['external_url']}")
    out.append(f"- 分析最近 {len(acc['posts'])} 則貼文，平均每週發 {fmt(s['posts_per_week'])} 則")
    out += ["", "| 類型 | 則數 | 平均讚 | 平均留言 | 平均觀看 | 互動率 |", "|---|---|---|---|---|---|"]
    for kind, k in s["kinds"].items():
        rate = "—" if k["engagement_rate_pct"] is None else f"{k['engagement_rate_pct']}%"
        out.append(f"| {KIND_LABEL[kind]} | {k['count']} | {fmt(k['avg_likes'])} | "
                   f"{fmt(k['avg_comments'])} | {fmt(k['avg_views'])} | {rate} |")

    def table(title, rows):
        if not rows:
            return
        out.extend(["", f"**{title}**", "", "| 日期 | 類型 | 讚 | 留言 | 觀看 | 秒數 | 文案開頭 | 連結 |",
                    "|---|---|---|---|---|---|---|---|"])
        for r in rows:
            out.append(f"| {r['date']} | {KIND_LABEL[r['kind']]} | {fmt(r['likes'])} | {fmt(r['comments'])} | "
                       f"{fmt(r['views'])} | {fmt(r['duration'])} | {short(r['caption'], 40).replace('|', '/')} | {r['url']} |")

    table("表現最好的 5 則", s["top_posts"])
    table("表現最差的 5 則", s["bottom_posts"])
    if s["best_slots"]:
        out += ["", "**互動最高的發文時段（台灣時間）**", ""]
        for b in s["best_slots"]:
            out.append(f"- 週{WEEKDAYS[b['weekday']]} {b['hour']:02d}:00（{b['posts']} 則，平均互動 {fmt(b['avg_engagement'])}）")
    if s["top_hashtags"]:
        out += ["", "**常用 hashtag**：" + "、".join(f"#{t}×{n}" for t, n in s["top_hashtags"])]
    out.append("")
    return out


def render_report(data):
    out = ["# Instagram 分析報告", "", f"產生時間：{data['generated_at']}", ""]
    for acc in data["accounts"]:
        out += render_account(acc)
    for r in data.get("reels", []):
        out += [f"## 參考影片 {r['url']}", "",
                f"- 作者：@{r['owner']}（追蹤者 {fmt(r.get('owner_followers'))}）",
                f"- 發布：{r['date']}｜長度 {fmt(r['duration'])} 秒",
                f"- 觀看 {fmt(r['views'])}｜讚 {fmt(r['likes'])}｜留言 {fmt(r['comments'])}",
                f"- 地點：{r.get('location') or '—'}",
                f"- hashtag：{' '.join('#' + t for t in r['hashtags']) or '—'}",
                "", "文案全文：", "", "```", r["caption"] or "（無）", "```", ""]
        if r.get("cover_file"):
            out += [f"封面圖已存到 `{r['cover_file']}`", ""]
    if data.get("errors"):
        out += ["## 抓取失敗的項目", ""] + [f"- {e}" for e in data["errors"]] + [""]
    return "\n".join(out)


def shortcode_from(value):
    m = re.search(r"/(?:reel|reels|p|tv)/([A-Za-z0-9_-]+)", value)
    return m.group(1) if m else value.strip("/ ")


def main():
    ap = argparse.ArgumentParser(description="抓取 IG 公開資料並產生分析報告")
    ap.add_argument("username", help="你的 IG 帳號")
    ap.add_argument("--compare", nargs="*", default=[], help="想參考的其他公開帳號")
    ap.add_argument("--reel", nargs="*", default=[], help="參考影片的網址或代碼")
    ap.add_argument("--posts", type=int, default=30, help="每個帳號分析最近幾則（預設 30）")
    ap.add_argument("--login", metavar="帳號", help="匿名被擋時，用這個帳號登入（密碼在終端機輸入，不會存檔）")
    ap.add_argument("--out", default="data", help="輸出資料夾")
    args = ap.parse_args()

    try:
        import instaloader
    except ImportError:
        sys.exit("請先安裝：pip install -r requirements.txt")

    L = instaloader.Instaloader(quiet=True, max_connection_attempts=2,
                                download_pictures=False, download_videos=False)
    if args.login:
        try:
            L.load_session_from_file(args.login)
        except FileNotFoundError:
            L.interactive_login(args.login)
            L.save_session_to_file()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    data = {"generated_at": time.strftime("%Y-%m-%d %H:%M"), "accounts": [], "reels": [], "errors": []}

    for name in [args.username, *args.compare]:
        print(f"抓取 @{name} …")
        try:
            prof = instaloader.Profile.from_username(L.context, name.lstrip("@"))
            profile = {
                "username": prof.username, "full_name": prof.full_name,
                "followers": prof.followers, "followees": prof.followees,
                "mediacount": prof.mediacount, "biography": prof.biography,
                "external_url": prof.external_url, "is_private": prof.is_private,
                "is_business": prof.is_business_account,
                "category": prof.business_category_name,
            }
            posts = []
            if prof.is_private and not args.login:
                data["errors"].append(f"@{name} 是私人帳號，只拿到基本資料")
            else:
                for post in prof.get_posts():
                    if len(posts) >= args.posts:
                        break
                    posts.append(post_to_dict(post))
                    time.sleep(1.5)  # 放慢速度，避免被 IG 限流
            data["accounts"].append({"profile": profile, "posts": posts,
                                     "summary": summarize(profile, posts)})
        except Exception as e:
            data["errors"].append(f"@{name}：{type(e).__name__}: {e}")
            print(f"  失敗：{e}")
        time.sleep(3)

    for value in args.reel:
        code = shortcode_from(value)
        print(f"抓取影片 {code} …")
        try:
            post = instaloader.Post.from_shortcode(L.context, code)
            r = post_to_dict(post)
            r["url"] = f"https://www.instagram.com/reel/{code}/"
            try:
                r["owner_followers"] = post.owner_profile.followers
            except Exception:
                r["owner_followers"] = None
            try:
                cover = out_dir / f"cover_{code}.jpg"
                cover.write_bytes(L.context.get_raw(post.url).content)
                r["cover_file"] = str(cover)
            except Exception:
                pass
            data["reels"].append(r)
        except Exception as e:
            data["errors"].append(f"影片 {code}：{type(e).__name__}: {e}")
            print(f"  失敗：{e}")

    (out_dir / "report.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "report.md").write_text(render_report(data), encoding="utf-8")
    print(f"\n完成：{out_dir / 'report.md'}")
    if data["errors"]:
        print("有項目抓取失敗，詳見報告最後一段。若是被要求登入，請加上 --login 你的帳號 再跑一次。")


if __name__ == "__main__":
    main()
