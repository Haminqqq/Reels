# IG 分析工具

在自己的電腦上抓 Instagram 公開資料，產生一份報告給 Claude 分析。

## 使用方式

需要 Python 3.9 以上。

```bash
pip install -r requirements.txt
python ig_report.py haminqqq --reel https://www.instagram.com/reel/DfZe4PRyT7l/
```

想一起分析其他公開帳號（例如你喜歡的穿搭、旅遊創作者）：

```bash
python ig_report.py haminqqq --reel DfZe4PRyT7l --compare 帳號A 帳號B
```

跑完會產生兩個檔案：

- `data/highlights.md`：給你看的。只列表現好的貼文、時段和內容類型，不顯示你的追蹤數，也不列表現差的貼文。
- `data/for_claude.json`：完整數據。不用打開，直接上傳到對話給 Claude 即可。

每跑一次還會在 `data/history.jsonl` 累積一筆紀錄，用來長期追蹤，同樣不用打開。

## 被 IG 擋下來時

IG 常會擋未登入的請求。報告最後若出現「抓取失敗」，加上登入再跑一次：

```bash
python ig_report.py haminqqq --reel DfZe4PRyT7l --login 你的帳號
```

密碼只在終端機輸入，登入狀態存在你電腦的使用者資料夾，不會進到這個專案。
自動化登入有被 IG 要求驗證或暫時限制的風險，建議用小號登入，不要用主帳號。

## 參數

| 參數 | 說明 |
|---|---|
| `--posts 30` | 每個帳號分析最近幾則貼文 |
| `--compare` | 其他要比較的公開帳號 |
| `--reel` | 參考影片的網址或代碼，可以放多個 |
| `--login` | 用指定帳號登入 |
| `--out data` | 輸出資料夾 |

# 模仿剪輯風格：分析 → 拍攝 → 自動剪

需要另外安裝 ffmpeg：

- Mac：`brew install ffmpeg`
- Windows：`winget install Gyan.FFmpeg`，裝完重開終端機

## 1. 分析參考影片

先把想模仿的影片存成檔案（手機螢幕錄影最簡單，錄完裁掉頭尾），然後：

```bash
python analyze_style.py 參考影片.mp4
```

會在 `data/style_參考影片/` 產生：

- `sheet.jpg`：每個鏡頭一張縮圖，標上編號和秒數
- `style.json`：每個鏡頭的起訖時間
- `plan.json`：剪輯計畫範本

把 `sheet.jpg` 和 `style.json` 上傳給 Claude，會拿到逐鏡頭的拍攝清單。

鏡頭抓得太少時加 `--sensitivity 0.15`，抓得太多時用 `0.5`。

## 2. 拍素材

照拍攝清單拍，每個鏡頭一個檔案，放進 `footage/`，檔名用鏡頭編號：
`01.mp4`、`02.mp4`…（照片也可以，把 `plan.json` 裡的檔名改成 `.jpg`）。

每段拍得比需要的秒數長一點，至少多 1–2 秒。

## 3. 自動剪輯

```bash
python auto_edit.py data/style_參考影片/plan.json
```

成品在 `output/`，是 1080×1920 直式、沒有聲音的影片，每個鏡頭的長度和參考影片一樣。
橫的素材會自動裁成直式（取中間）。

`plan.json` 每一段可以調整：

| 欄位 | 說明 |
|---|---|
| `file` | 素材路徑 |
| `duration` | 這個鏡頭在成品裡的秒數 |
| `start` | 從素材第幾秒開始取；不寫就取正中間那一段 |
| `speed` | 速度，`2` 是兩倍快，`0.5` 是慢動作 |

## 4. 音樂和字幕在 IG 裡加

上傳成品到 IG 後，選和參考影片同一首音樂。因為鏡頭長度一樣，
音樂從同一個位置開始就會對上節拍。字幕也在 IG 或 Edits 裡加。

這樣做是因為用 IG 內建音樂才不會有版權問題，也才吃得到熱門音樂的流量。

## 限制

- 只會做「硬切」。溶接、縮放、搖鏡這類轉場特效偵測不到，也不會自動加。
- iPhone 用 HDR 拍的素材，剪出來顏色可能偏灰；拍之前到「設定 → 相機 → 錄影」關掉 HDR 影片。
