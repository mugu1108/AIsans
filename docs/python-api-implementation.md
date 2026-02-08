# Python API 実装完了報告

## 概要

DifyワークフローのClaudeからの依頼に基づき、検索機能をPython APIに実装しました。
`/search_sync` エンドポイントが追加され、Difyから直接呼び出せます。

---

## 新エンドポイント

### POST /search_sync（Dify用・同期版）

検索→スクレイピング→GAS保存を一括で実行し、完了後に結果を返します。

**リクエスト:**
```json
{
    "search_keyword": "東京 IT企業",
    "target_count": 50,
    "queries": ["東京 IT企業 一覧", "東京 システム開発会社"]  // オプション
}
```

**レスポンス:**
```json
{
    "status": "success",
    "search_keyword": "東京 IT企業",
    "target_count": 50,
    "result_count": 45,
    "search_count": 60,
    "scrape_count": 60,
    "success_count": 45,
    "spreadsheet_url": "https://docs.google.com/spreadsheets/d/xxx",
    "results": [
        {
            "company_name": "株式会社ABC",
            "base_url": "https://abc.co.jp/",
            "contact_url": "https://abc.co.jp/contact/",
            "phone": "03-1234-5678",
            "domain": "abc.co.jp"
        }
    ],
    "message": "検索完了: 45件の企業情報を取得しました。"
}
```

**エラーレスポンス:**
```json
{
    "detail": "SERPER_API_KEY が未設定です"
}
```

---

## 処理フロー

```
POST /search_sync
    ↓
1. GASから既存ドメイン取得 (action: get_domains)
    ↓
2. クエリ生成（指定がなければ自動生成）
   - "{keyword} 企業一覧"
   - "{keyword} 会社"
   - "{keyword} 株式会社"
   - "{keyword} ランキング"
   - "{keyword} おすすめ"
   - "{keyword} 比較"
   - "{keyword} co.jp"
    ↓
3. Serper検索（各クエリ最大100件×3ページ）
   - 除外ドメインフィルタ
   - 既存ドメイン重複排除
   - 目標件数まで収集
    ↓
4. スクレイピング（並列10件）
   - トップページ取得
   - 企業名一致チェック
   - お問い合わせURL抽出
   - 電話番号抽出
    ↓
5. GAS保存 (action: save_results)
    ↓
6. レスポンス返却
```

---

## 必要な環境変数（Railway）

```env
# 必須
SERPER_API_KEY=xxx              # Serper.dev APIキー
GAS_WEBHOOK_URL=https://script.google.com/macros/s/.../exec

# オプション（/search エンドポイント用、Slack通知が必要な場合）
SLACK_BOT_TOKEN=xoxb-xxx
```

---

## GAS側の対応

新GAS（AI-Shine版）で以下のアクションに対応済み:

### action: get_domains
既存のドメインリストを返す
```json
// リクエスト
{"action": "get_domains"}

// レスポンス
{"status": "success", "domains": ["abc.co.jp", "xyz.co.jp", ...]}
```

### action: save_results
スクレイピング結果を新規スプレッドシートに保存
```json
// リクエスト
{
    "action": "save_results",
    "search_keyword": "東京 IT企業",
    "companies": [
        {"company_name": "...", "base_url": "...", "contact_url": "...", "phone": "...", "domain": "..."}
    ]
}

// レスポンス
{
    "status": "success",
    "spreadsheet_id": "xxx",
    "spreadsheet_url": "https://docs.google.com/...",
    "row_count": 45
}
```

GASコードは `gas/Code.gs` に用意してあります。

---

## Dify側の設定

### HTTPリクエストノードの設定

```
URL: https://{RAILWAY_URL}/search_sync
Method: POST
Headers:
  Content-Type: application/json
Body:
{
    "search_keyword": "{{input_keyword}}",
    "target_count": {{target_count}}
}
Timeout:
  Connect: 60
  Read: 600  ← 重要！最大10分まで待機
  Write: 60
```

### ワークフロー簡素化案

```
【現在の重いワークフロー（61ノード）】
入力パース → LLMクエリ生成 → Serper検索×30 → 統合 → LLMクレンジング → ...

【新しい軽いワークフロー（6ノード程度）】
1. 開始
2. 入力パース（件数抽出）
3. HTTPリクエスト（/search_sync）
4. 結果表示
5. 終了
```

---

## 制限事項

| 項目 | 値 |
|------|-----|
| 最大件数 | 200件（設定で変更可能） |
| タイムアウト | 10分程度を推奨 |
| 同時スクレイピング | 10件 |
| Serper検索 | 各クエリ100件×最大3ページ |

---

## テスト方法

### 1. ヘルスチェック
```bash
curl https://{RAILWAY_URL}/health
```

### 2. 少件数テスト
```bash
curl -X POST https://{RAILWAY_URL}/search_sync \
  -H "Content-Type: application/json" \
  -d '{"search_keyword": "東京 IT企業", "target_count": 5}'
```

---

## ファイル構成

```
scraping-api/
├── main.py                    ← /search_sync エンドポイント
├── scraper.py                 ← スクレイピングロジック（既存）
├── requirements.txt
├── config/
│   └── settings.py            ← 環境変数管理
├── models/
│   ├── job.py                 ← ジョブモデル
│   └── search.py              ← 検索モデル
└── services/
    ├── serper.py              ← Serper API + クエリ生成
    ├── gas_client.py          ← GAS連携
    ├── job_manager.py         ← ジョブ管理（非同期用）
    ├── slack_notifier.py      ← Slack通知（非同期用）
    └── search_workflow.py     ← ワークフロー実行（非同期用）
```

---

## 補足: /scrape の500エラーについて

既存の `/scrape` エンドポイントは引き続き使用可能です。
500エラーが発生していた場合、以下を確認してください：

1. `lxml` が `requirements.txt` に含まれている（確認済み）
2. Railwayのメモリが十分か
3. リクエストの `companies` 配列が正しい形式か

```json
// 正しい形式
{
    "companies": [
        {"company_name": "株式会社ABC", "url": "https://abc.co.jp"}
    ]
}
```

---

## 連絡事項

- Serper.dev のAPIキーが必要です
- GASのデプロイURLを `GAS_WEBHOOK_URL` に設定してください
- Dify側のHTTPタイムアウトを600秒に設定してください
