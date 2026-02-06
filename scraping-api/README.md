# AI-Shine Scraping API

営業リスト作成用のスクレイピングAPI。GASの6分タイムアウト制約を解消するため、Python (FastAPI) で実装。

## 機能

- 企業URLからお問い合わせURL・電話番号を抽出
- 企業名一致チェック（company_mismatch判定）
- 非同期並列処理で高速化（最大10件同時）

## API

### POST /scrape

企業リストをスクレイピング。

**リクエスト:**
```json
{
  "companies": [
    {
      "company_name": "株式会社ABC",
      "url": "https://www.abc.co.jp/"
    }
  ]
}
```

**レスポンス:**
```json
{
  "status": "success",
  "results": [
    {
      "company_name": "株式会社ABC",
      "base_url": "https://www.abc.co.jp/",
      "contact_url": "https://www.abc.co.jp/contact/",
      "phone": "03-1234-5678",
      "domain": "www.abc.co.jp",
      "error": ""
    }
  ],
  "total": 1,
  "scraped": 1,
  "success_count": 1
}
```

### GET /health

ヘルスチェック。

## ローカル開発

```bash
# 仮想環境作成
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 依存関係インストール
pip install -r requirements.txt

# 起動
python main.py
# または
uvicorn main:app --reload
```

APIドキュメント: http://localhost:8000/docs

## Railway デプロイ

1. Railwayでサービス作成
2. `scraping-api` ディレクトリをルートに設定
3. 自動でビルド・デプロイ

環境変数は特に不要。

## エラー種別

| error | 意味 |
|-------|------|
| (空) | 正常 |
| `top_page_failed` | トップページ取得失敗 |
| `company_mismatch` | 企業名とページ内容が不一致 |
