#!/usr/bin/env python3
"""分析一支參考影片的剪輯節奏（在自己的電腦上執行，需要 ffmpeg）。

用法：
    python analyze_style.py 參考影片.mp4
    python analyze_style.py 參考影片.mp4 --sensitivity 0.2   # 鏡頭切得少、漏抓時調低

輸出到 data/style_<檔名>/：
    sheet.jpg   每個鏡頭一張縮圖的總覽圖（上傳給 Claude 看）
    shot_XX.jpg 每個鏡頭各自的截圖
    style.json  每個鏡頭的起訖時間（上傳給 Claude）
    plan.json   剪輯計畫範本，拍好素材後交給 auto_edit.py
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def probe(path):
    r = run(["ffprobe", "-v", "error", "-show_entries",
             "format=duration:stream=codec_type,width,height,r_frame_rate", "-of", "json", str(path)])
    if r.returncode != 0:
        sys.exit(f"讀不到影片：{path}\n{r.stderr.strip()}")
    info = json.loads(r.stdout)
    video = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    if not video:
        sys.exit("這個檔案沒有影像軌")
    num, den = video["r_frame_rate"].split("/")
    return {
        "duration": float(info["format"]["duration"]),
        "width": video["width"], "height": video["height"],
        "fps": round(float(num) / float(den), 2) if float(den) else None,
        "has_audio": any(s["codec_type"] == "audio" for s in info["streams"]),
    }


def detect_cuts(path, sensitivity):
    r = run(["ffmpeg", "-hide_banner", "-i", str(path), "-vf",
             f"select='gt(scene,{sensitivity})',showinfo", "-an", "-f", "null", "-"])
    return [float(t) for t in re.findall(r"pts_time:([0-9.]+)", r.stderr)]


def build_shots(cuts, duration, min_len=0.2):
    """把切點轉成鏡頭清單；太靠近的切點（閃光、轉場特效）合併。"""
    points = [0.0]
    for t in sorted(cuts):
        if t - points[-1] >= min_len and duration - t >= min_len:
            points.append(t)
    points.append(duration)
    return [{"n": i + 1, "start": round(a, 2), "end": round(b, 2), "duration": round(b - a, 2)}
            for i, (a, b) in enumerate(zip(points, points[1:]))]


def extract_thumbs(video, shots, out_dir, thumb_w=216):
    """每個鏡頭取中間一格存成 shot_XX.jpg，回傳成功的檔案與失敗原因。"""
    ok, errors = [], []
    for s in shots:
        f = out_dir / f"shot_{s['n']:02d}.jpg"
        f.unlink(missing_ok=True)
        mid = s["start"] + s["duration"] / 2
        r = run(["ffmpeg", "-y", "-v", "error", "-ss", f"{mid:.3f}", "-i", str(video),
                 "-frames:v", "1", "-vf", f"scale={thumb_w}:-2,format=yuvj420p", "-q:v", "4", str(f)])
        if f.exists() and f.stat().st_size > 0:
            ok.append((s, f))
        else:
            errors.append(f"鏡頭 {s['n']}：{(r.stderr.strip().splitlines() or ['未知錯誤'])[-1]}")
    return ok, errors


def sheet_with_pillow(thumbs, out_dir, cols=5):
    from PIL import Image, ImageDraw, ImageFont
    images = [(s, Image.open(f).convert("RGB")) for s, f in thumbs]
    tw = max(im.width for _, im in images)
    th = max(im.height for _, im in images)
    label_h, pad = 34, 8
    rows = -(-len(images) // cols)
    sheet = Image.new("RGB", (cols * (tw + pad) + pad, rows * (th + label_h + pad) + pad), "white")
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default(size=15)
    except TypeError:
        font = ImageFont.load_default()
    for i, (s, im) in enumerate(images):
        x = pad + (i % cols) * (tw + pad)
        y = pad + (i // cols) * (th + label_h + pad)
        sheet.paste(im, (x, y))
        draw.text((x, y + th + 2), f"#{s['n']}  {s['start']:.1f}s", fill="black", font=font)
        draw.text((x, y + th + 17), f"len {s['duration']:.2f}s", fill="black", font=font)
    path = out_dir / "sheet.jpg"
    sheet.save(path, quality=85)
    return path


def sheet_with_ffmpeg(thumbs, out_dir, cols=5):
    """沒有 Pillow 時改用 ffmpeg 拼圖（沒有文字標籤，順序就是鏡頭編號）。"""
    rows = -(-len(thumbs) // cols)
    path = out_dir / "sheet.jpg"
    run(["ffmpeg", "-y", "-v", "error", "-framerate", "1", "-start_number", "1",
         "-i", str(out_dir / "shot_%02d.jpg"), "-vf",
         f"pad=iw+8:ih+8:4:4:white,tile={cols}x{rows}:color=white", "-frames:v", "1", str(path)])
    return path if path.exists() else None


def make_sheet(video, shots, out_dir):
    thumbs, errors = extract_thumbs(video, shots, out_dir)
    for e in errors[:3]:
        print(f"  截圖失敗 {e}")
    if not thumbs:
        return None
    try:
        return sheet_with_pillow(thumbs, out_dir)
    except ImportError:
        print("（沒裝 Pillow，改用 ffmpeg 拼總覽圖，圖上不會有編號文字）")
    except Exception as e:
        print(f"（Pillow 拼圖失敗：{e}，改用 ffmpeg）")
    if len(thumbs) == len(shots):
        return sheet_with_ffmpeg(thumbs, out_dir)
    return None


def main():
    ap = argparse.ArgumentParser(description="分析參考影片的剪輯節奏")
    ap.add_argument("video")
    ap.add_argument("--sensitivity", type=float, default=0.3, help="切點偵測門檻 0–1，越低越敏感（預設 0.3）")
    ap.add_argument("--out", default="data")
    args = ap.parse_args()

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        sys.exit("找不到 ffmpeg，請先安裝（見 README）")
    video = Path(args.video)
    if not video.exists():
        sys.exit(f"找不到檔案：{video}")

    info = probe(video)
    shots = build_shots(detect_cuts(video, args.sensitivity), info["duration"])
    out_dir = Path(args.out) / f"style_{video.stem}"
    out_dir.mkdir(parents=True, exist_ok=True)

    durs = [s["duration"] for s in shots]
    style = {
        "source": video.name, **info,
        "shot_count": len(shots),
        "avg_shot": round(sum(durs) / len(durs), 2),
        "shortest_shot": min(durs), "longest_shot": max(durs),
        "shots": shots,
    }
    (out_dir / "style.json").write_text(json.dumps(style, ensure_ascii=False, indent=2), encoding="utf-8")

    plan = {
        "output": f"output/{video.stem}_mine.mp4",
        "width": 1080, "height": 1920, "fps": 30,
        "music": None,
        "clips": [{"file": f"footage/{s['n']:02d}.mp4", "duration": s["duration"]} for s in shots],
    }
    (out_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    sheet = make_sheet(video, shots, out_dir)

    print(f"影片長度 {info['duration']:.1f} 秒，共 {len(shots)} 個鏡頭，平均每個 {style['avg_shot']} 秒")
    print(f"結果在 {out_dir}/")
    if sheet:
        print("把 sheet.jpg 和 style.json 上傳給 Claude，就會拿到拍攝清單。")
    elif any(out_dir.glob("shot_*.jpg")):
        print("總覽圖沒做成，但每個鏡頭的截圖 shot_01.jpg… 都在資料夾裡，直接上傳這些截圖給 Claude 即可。")
    else:
        print("沒辦法從影片截圖。請把上面的錯誤訊息截圖給 Claude。")
    if len(shots) <= 2 and info["duration"] > 6:
        print("偵測到的鏡頭很少，可能漏抓了，可以加 --sensitivity 0.15 再試一次。")


if __name__ == "__main__":
    main()
