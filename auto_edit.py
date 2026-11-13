#!/usr/bin/env python3
"""照剪輯計畫把素材自動剪成直式短影片（在自己的電腦上執行，需要 ffmpeg）。

用法：
    python auto_edit.py data/style_參考影片/plan.json

plan.json 的 clips 每一項：
    file      素材路徑（影片或照片）
    duration  這個鏡頭在成品裡的秒數
    start     從素材第幾秒開始取（省略時取素材正中間那一段）
    speed     播放速度，2 是兩倍快、0.5 是慢動作（省略為 1）
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic"}


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def media_duration(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)])
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def check_plan(plan, base):
    """回傳問題清單（空的代表可以開始剪）。"""
    problems = []
    for i, c in enumerate(plan.get("clips", []), 1):
        f = base / c["file"]
        if not f.exists():
            problems.append(f"第 {i} 段：找不到素材 {c['file']}")
            continue
        if f.suffix.lower() in IMAGE_EXT:
            continue
        need = c["duration"] * c.get("speed", 1) + c.get("start", 0)
        have = media_duration(f)
        if have is not None and have + 0.05 < need:
            problems.append(f"第 {i} 段：{c['file']} 只有 {have:.1f} 秒，需要至少 {need:.1f} 秒")
    if not plan.get("clips"):
        problems.append("plan.json 裡沒有 clips")
    return problems


def render_clip(clip, base, out, w, h, fps):
    src = base / clip["file"]
    speed = clip.get("speed", 1)
    frames = max(1, round(clip["duration"] * fps))
    vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,"
          f"setpts=PTS/{speed},fps={fps},format=yuv420p")
    if src.suffix.lower() in IMAGE_EXT:
        inp = ["-loop", "1", "-i", str(src)]
    else:
        start = clip.get("start")
        if start is None:
            have = media_duration(src) or 0
            start = max(0, (have - clip["duration"] * speed) / 2)
        inp = ["-ss", f"{start:.3f}", "-i", str(src)]
    r = run(["ffmpeg", "-y", "-v", "error", *inp, "-an", "-vf", vf, "-frames:v", str(frames),
             "-c:v", "libx264", "-preset", "medium", "-crf", "18", str(out)])
    if r.returncode != 0 or not out.exists():
        sys.exit(f"剪 {clip['file']} 時失敗：\n{r.stderr.strip()[-600:]}")


def main():
    ap = argparse.ArgumentParser(description="照 plan.json 自動剪輯")
    ap.add_argument("plan")
    ap.add_argument("--base", default=".", help="素材路徑的起點資料夾（預設為目前資料夾）")
    args = ap.parse_args()

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        sys.exit("找不到 ffmpeg，請先安裝（見 README）")
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    base = Path(args.base)
    problems = check_plan(plan, base)
    music = plan.get("music")
    if music and not (base / music).exists():
        problems.append(f"找不到音樂 {music}")
    if problems:
        sys.exit("先處理這些問題再剪：\n" + "\n".join(f"- {p}" for p in problems))

    w, h, fps = plan.get("width", 1080), plan.get("height", 1920), plan.get("fps", 30)
    out = base / plan.get("output", "output/reel.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        parts = []
        for i, clip in enumerate(plan["clips"], 1):
            print(f"[{i}/{len(plan['clips'])}] {clip['file']}")
            part = tmp / f"{i:03d}.mp4"
            render_clip(clip, base, part, w, h, fps)
            parts.append(part)
        listing = tmp / "list.txt"
        listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
        cmd = ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing)]
        if music:
            cmd += ["-i", str(base / music), "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "192k", "-shortest"]
        cmd += ["-c:v", "copy", "-movflags", "+faststart", str(out)]
        r = run(cmd)
        if r.returncode != 0:
            sys.exit(f"合併失敗：\n{r.stderr.strip()[-600:]}")

    total = sum(c["duration"] for c in plan["clips"])
    print(f"\n完成：{out}（約 {total:.1f} 秒，{w}x{h}）")


if __name__ == "__main__":
    main()
