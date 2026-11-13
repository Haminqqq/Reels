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

跑完會產生 `data/report.md`，把內容整份貼回對話即可。

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
