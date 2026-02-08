# AI-Shine 引き継ぎドキュメント

**最終更新**: 2026-02-08 12:00
**担当**: Claude Opus 4.5
**ステータス**: 504タイムアウト対策実装済み、テスト待ち

---

## 1. プロジェクト概要

**AI-Shine (AIsans)** は、Slackから営業リストを自動生成するAI社員システムです。

### システム構成図

```
┌─────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Slack     │────▶│  Railway        │────▶│   Dify API      │
│  (ユーザー)  │     │  (Node.js Bot)  │     │  (Workflow)     │
└─────────────┘     └─────────────────┘     └────────┬────────┘
                                                      │
                           ┌──────────────────────────┼──────────────────────────┐
                           │                          │                          │
                           ▼                          ▼                          ▼
                    ┌─────────────┐          ┌─────────────────┐         ┌─────────────┐
                    │  Python     │          │  Google Apps    │         │  OpenAI等   │
                    │  Scraping   │          │  Script (GAS)   │         │  (LLM)      │
                    │  (Railway)  │          │  → Spreadsheet  │         └─────────────┘
                    └─────────────┘          └─────────────────┘
```

### 主要サービス

| サービス | 役割 | URL/場所 |
|---------|------|----------|
| **Slack Bot** | ユーザーインターフェース | @Alex をメンション |
| **Node.js Backend** | Dify APIとの連携 | Railway (`ai-shain`) |
| **Dify Workflow** | AI営業リスト生成 | `https://api.dify.ai/v1/workflows/run` |
| **Python Scraping API** | Webスクレイピング | Railway (`dazzling-nature-production-9705.up.railway.app`) |
| **Google Apps Script** | スプレッドシート作成 | GAS WebApp |

---

## 2. 現在取り組んでいる問題

### 問題: 504 Gateway Timeout

**症状**:
- Slack から `@Alex 東京 IT企業 30件` とメンションすると 504 エラーが発生
- Dify の UI から直接テストすると正常に動作する
- 15件程度だと動くこともあるが、30件以上だとほぼ確実にタイムアウト

**原因分析**:
```
Backend → Dify API Gateway → Dify Workflow
               ↑
         ここでタイムアウト（60-120秒）
```

Dify API は `response_mode: 'blocking'` だと、ワークフロー完了まで1つのHTTPリクエストが待機します。
Dify の API Gateway に短いタイムアウト（60-120秒）が設定されており、ワークフローが長時間かかると 504 を返します。

**Dify UI で動く理由**:
- Dify UI は内部接続を使用しており、API Gateway を経由しない
- そのため長時間のワークフローでもタイムアウトしない

---

## 3. 実装した解決策

### 解決策: Streaming モードへの変更

**変更前** (Blocking モード):
```
1. リクエスト送信
2. Dify がワークフロー完了まで待機（数分）
3. 完了後にレスポンス返却
→ Gateway が先にタイムアウト (504)
```

**変更後** (Streaming モード):
```
1. リクエスト送信
2. Dify がすぐにストリーミング接続を確立
3. イベントを継続的に送信（workflow_started, node_finished, etc.）
4. 最後に workflow_finished イベントで結果を返却
→ データが流れ続けるためタイムアウトしにくい
```

### 変更したファイル

#### `src/infrastructure/dify/DifyClient.ts`
- `response_mode: 'blocking'` → `response_mode: 'streaming'`
- SSE (Server-Sent Events) パース処理を実装
- `parseSSEStream()` メソッドを追加

```typescript
// 主要な変更点
const requestBody: DifyWorkflowRequest = {
  inputs: { user_input: query },
  response_mode: 'streaming',  // ← ここを変更
  user: userId,
};

// ストリーミングレスポンスを取得
const response = await this.client.post('/workflows/run', requestBody, {
  responseType: 'stream',
  headers: { 'Accept': 'text/event-stream' },
});

// SSEストリームを解析
const result = await this.parseSSEStream(response.data, query);
```

#### `src/infrastructure/dify/DifyTypes.ts`
- `DifyWorkflowFinishedEvent` 型を追加
- `DifyStreamingEvent` 型を追加

#### `src/index.ts`
- 最大件数の上限を50件に設定
- 上限超過時はユーザーに通知

```typescript
const MAX_COUNT = 50;
const countMatch = query.match(/(\d+)\s*件/);
if (countMatch) {
  const requestedCount = parseInt(countMatch[1], 10);
  if (requestedCount > MAX_COUNT) {
    query = query.replace(/\d+\s*件/, `${MAX_COUNT}件`);
    // ユーザーに通知
  }
}
```

#### `src/application/WorkflowOrchestrator.ts`
- リトライ回数を 3 → 1 に削減
- タイムアウトエラー (504) はリトライしない

#### `src/utils/errors.ts`
- `TimeoutError` を `retryable: false` に変更

---

## 4. Git コミット履歴

```
8985fe4 fix: Dify APIをストリーミングモードに変更して504対策
d98bed1 fix: タイムアウト対策を実装
4b8803b refactor: 件数パースをDify側に移行
170aafb chore: 除外ドメインリストに3サイトを追加
7dee6ba feat: Slackメッセージから件数指定機能を追加
26e3e74 fix: target_countを文字列として送信
947f87f feat: DifyワークフローからspreadsheetUrl取得対応
```

---

## 5. 次にやるべきこと

### 5.1 テスト（最優先）

Railwayデプロイ完了後、Slackで以下をテスト:

```
@Alex 東京 IT企業 10件
@Alex 東京 IT企業 30件
@Alex 東京 IT企業 50件
```

**確認ポイント**:
- [ ] 504エラーが発生しないこと
- [ ] CSVファイルが正常にSlackに送信されること
- [ ] スプレッドシートURLが表示されること
- [ ] 指定した件数に近い結果が返ること

### 5.2 ストリーミングが動かない場合の代替案

もしストリーミングでも問題が解決しない場合:

**案A: 非同期ポーリング方式**
1. ワークフロー実行をリクエスト → `workflow_run_id` を取得
2. 定期的に状態を確認 (GET /workflows/runs/{id})
3. 完了したら結果を取得

**案B: Dify側のワークフロー最適化**
- リトライ/蓄積ロジックを簡素化
- target_count を確実に反映させる
- 処理時間を短縮

**案C: 件数上限をさらに下げる**
- MAX_COUNT を 30 や 20 に下げる

---

## 6. 重要なファイル一覧

### Backend (Node.js)

| ファイル | 役割 |
|---------|------|
| `src/index.ts` | メインエントリーポイント、Slackイベント処理 |
| `src/application/WorkflowOrchestrator.ts` | ワークフロー実行とリトライ制御 |
| `src/infrastructure/dify/DifyClient.ts` | Dify API クライアント（**今回主に変更**） |
| `src/infrastructure/dify/DifyTypes.ts` | Dify関連の型定義 |
| `src/interfaces/slack/SlackAdapter.ts` | Slack連携アダプター |
| `src/utils/errors.ts` | カスタムエラークラス |

### Dify Workflow

| ファイル | 役割 |
|---------|------|
| `営業リスト作成.yaml` | Difyワークフロー定義（参照用） |

**Difyワークフローの主要ノード**:
1. `input_parse` - user_input から target_count と search_query をパース
2. `scraping_http` - Python Scraping API を呼び出し
3. `retry/accumulation` - 結果が足りない場合にリトライ
4. `gas_update_http` - GAS を呼び出してスプレッドシート作成
5. `final_format` - 最終出力フォーマット

### Google Apps Script

| ファイル | 役割 |
|---------|------|
| `gascode.js` | スプレッドシート作成、除外ドメインフィルタリング |

**除外ドメイン** (gascode.js 内):
- ポータルサイト: baseconnect.in, wantedly.com, etc.
- 求人サイト: recruit.co.jp, mynavi.jp, etc.
- 検索・マッチングサイト: biz.ne.jp, web-kanji.com, ipros.com

---

## 7. 環境変数

`.env` に必要な環境変数:

```env
# Slack
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
SLACK_APP_TOKEN=xapp-...

# Dify
DIFY_API_URL=https://api.dify.ai/v1
DIFY_API_KEY=app-...

# Google Drive
GOOGLE_DRIVE_FOLDER_ID=...

# Database
DATABASE_URL=postgresql://...

# Server
PORT=3000
```

---

## 8. デプロイ方法

### Railway (Backend)
```bash
git push origin main
# Railway が自動デプロイ
```

### Dify Workflow
- Dify Studio で直接編集
- YAML をインポート/エクスポート可能

### Google Apps Script
- GAS エディタで編集
- 「デプロイ」→「ウェブアプリ」で公開

---

## 9. デバッグ方法

### Railway ログ確認
Railway ダッシュボード → Deployments → Logs

### 重要なログメッセージ
```
[DEBUG] Dify Workflow（ストリーミング）を呼び出し中  ← リクエスト開始
[DEBUG] SSEイベント受信: workflow_started            ← ストリーミング開始
[DEBUG] SSEイベント受信: node_finished               ← 各ノード完了
[DEBUG] workflow_finished イベントを受信              ← ワークフロー完了
[INFO] Dify Workflow（ストリーミング）実行完了        ← 成功
```

### エラー時のログ
```
[ERROR] Dify APIエラー: Request failed with status code 504  ← Gateway Timeout
[WARN] 504 Gateway Timeoutはリトライしません                  ← リトライスキップ
```

---

## 10. 既知の問題・注意点

### 10.1 Dify の input_parse ノード
ユーザーが追加した `input_parse` ノードが user_input から件数をパースします。
Backend 側では件数パースを削除済み（Dify側に任せる）。

```python
# Dify input_parse ノードのコード
def main(user_input: str) -> dict:
    target_count = "30"  # デフォルト
    match = re.search(r'(\d+)\s*件', user_input)
    if match:
        target_count = match.group(1)
    return {"target_count": target_count, "search_query": search_query}
```

### 10.2 スプレッドシートURL
Dify ワークフローの END ノードで `spreadsheet_url` を出力に含める必要があります。
`gas_update_http` ノードの結果から取得。

### 10.3 GitHub リポジトリの移動
リポジトリが移動したという警告が出ますが、push は正常に動作します:
```
remote: This repository moved. Please use the new location:
remote:   https://github.com/mugu1108/AIsans.git
```

---

## 11. 連絡事項

- **Python Scraping API URL**: `https://dazzling-nature-production-9705.up.railway.app`
- **Dify ワークフロー内で HTTP ノードの URL を設定する必要あり**

---

## 12. 次回セッションでの確認事項

1. **ストリーミングモードのテスト結果**
   - 504エラーは解消されたか？
   - 処理時間はどのくらいか？

2. **Dify ワークフローの挙動**
   - target_count は正しくパースされているか？
   - 指定件数に近い結果が返ってきているか？

3. **追加対応が必要な場合**
   - 非同期ポーリング方式への移行
   - Dify ワークフローの最適化
   - GAS の処理時間短縮

---

**以上が現在の状況です。ストリーミングモードの変更をデプロイ済みなので、まずはSlackでテストして結果を確認してください。**
