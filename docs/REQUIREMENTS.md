# AI-Shine 要件定義書

**バージョン**: 2.0（改訂版）
**作成日**: 2026-01-19
**最終更新**: 2026-01-19
**プロジェクト名**: AI-Shine（AI社員システム）

---

## 1. プロジェクト概要

### 1.1 プロジェクトビジョン
AI-Shineはマルチプラットフォーム対応の社内業務自動化プラットフォームです。Slack、LINE、Microsoft Teamsなど複数のコミュニケーションツールに対応し、各部署に特化したAI社員（ボット）を配置して定型業務や情報収集タスクを自動化します。

**長期ビジョン**: パッケージ化されたAI社員システムとして、プラットフォームや部署を問わず横展開可能な汎用的なアーキテクチャを採用します。

### 1.2 対象範囲
- **フェーズ1**：営業部門向けリスト作成AI（本要件定義の対象）
- **フェーズ2以降**：経理、その他部署への横展開

### 1.3 目的
- 社内業務の効率化
- 定型タスクの自動化によるリソース最適化
- 各部署に特化したAI活用の推進

---

## 2. システムアーキテクチャ

### 2.1 全体構成図（改訂版）

```
┌─────────────────────────────────────┐
│  Platform Layer (Adapters)          │
│  ┌─────────┬─────────┬─────────┐   │
│  │ Slack   │  LINE   │ Teams   │   │
│  └─────────┴─────────┴─────────┘   │
└─────────────────────────────────────┘
              ↕
┌─────────────────────────────────────┐
│  AI-Shine Core Backend (Railway)    │
│  ┌─────────────────────────────┐   │
│  │  Application Layer          │   │
│  │  - MessageHandler           │   │
│  │  - WorkflowOrchestrator     │   │
│  └─────────────────────────────┘   │
│  ┌─────────────────────────────┐   │
│  │  Domain Layer               │   │
│  │  - AIEmployee Service       │   │
│  │  - Log Service              │   │
│  └─────────────────────────────┘   │
└─────────────────────────────────────┘
       ↕                    ↕
┌─────────────┐    ┌─────────────┐
│  Dify API   │    │ PostgreSQL  │
│             │    │ (Supabase)  │
└─────────────┘    └─────────────┘
```

### 2.2 コンポーネント（改訂版）

| レイヤー | コンポーネント | 役割 | 技術 |
|---|---|---|---|
| **Interface** | Platform Adapters | プラットフォーム固有の通信処理 | Slack Bolt / LINE SDK / Teams SDK |
| **Application** | Message Handler | メッセージ受信・ルーティング | TypeScript |
| **Application** | Workflow Orchestrator | Dify連携・実行管理 | TypeScript |
| **Domain** | AIEmployee Service | AI社員の管理・設定 | TypeScript |
| **Domain** | Log Service | 実行履歴の記録・取得 | TypeScript + Prisma |
| **Infrastructure** | Database | データ永続化 | PostgreSQL (Supabase) |
| **Infrastructure** | Dify Client | ワークフロー実行 | Dify API |
| **Hosting** | App Server | アプリケーション実行 | Railway（無料枠） |

---

## 3. 技術スタック

### 3.1 開発環境
- **言語**: TypeScript
- **ランタイム**: Node.js 18.x以上
- **パッケージマネージャー**: npm or pnpm

### 3.2 主要ライブラリ・SDK
- `@slack/bolt`: Slackボット開発
- `@prisma/client`: データベースORM
- `prisma`: スキーマ管理・マイグレーション
- `axios`: HTTP通信（Dify API呼び出し）
- `csv-writer` or `papaparse`: CSV生成・パース
- `zod`: 型バリデーション

### 3.3 外部サービス
- **Slack Workspace**: ボット配置先（Phase 1）
- **Dify**: ワークフロー実行エンジン
- **Supabase**: PostgreSQLホスティング（無料枠）
- **Railway**: アプリケーションホスティング（無料枠）

### 3.4 認証・トークン管理
- Slack Bot Token（環境変数）
- Slack App Token（Socket Mode用、オプション）
- Slack Signing Secret（リクエスト検証）
- Dify API Key（環境変数）
- Supabase Database URL（環境変数）

---

## 4. 機能要件

### 4.1 第一号AI社員：営業リスト作成ボット

#### 4.1.1 基本機能
| ID | 機能名 | 説明 | 優先度 |
|---|---|---|---|
| F-001 | キーワード受付 | @メンションでキーワードを受け取る | 必須 |
| F-002 | Dify API呼び出し | キーワードをDifyに送信してワークフロー実行 | 必須 |
| F-003 | 処理状態通知 | 開始・完了・エラーをユーザーに通知 | 必須 |
| F-004 | CSV生成・添付 | 結果をCSV形式でSlackに添付 | 必須 |
| F-005 | ログ記録 | 実行履歴をPostgreSQLに保存 | 必須 |
| F-006 | エラーハンドリング | エラー時の詳細メッセージとリトライ提案 | 必須 |

#### 4.1.2 入力仕様
- **入力形式**: `@営業AI [キーワード]`
- **キーワード例**:
  - 「横浜市に工場を持つ製造業」
  - 「東京都内のIT企業」
  - 「関西圏の食品メーカー」
- **文字数制限**: 特になし（Slack制限に準拠）

#### 4.1.3 出力仕様
- **形式**: CSV（UTF-8 BOM付き推奨）
- **ファイル名**: `sales_list_YYYYMMDD_HHMMSS.csv`
- **列構成**（暫定）:
  - 企業名
  - 企業URL
  - 問い合わせURL
  - その他（Difyワークフローに依存）
- **件数**: 約30社（Difyワークフローに依存）

### 4.2 ユーザーフロー

#### 4.2.1 正常フロー
```
1. ユーザー: @営業AI 横浜市に工場を持つ製造業
2. ボット: 了解しました！営業リスト作成を開始します...⏳
3. [バックエンド → Dify API呼び出し]
4. [数分待機]
5. ボット: ✅ 完了しました！30社のリストを作成しました
          📎 sales_list_20260119_143025.csv
6. [ログ記録]
```

#### 4.2.2 エラーフロー
```
1. ユーザー: @営業AI キーワード
2. ボット: 了解しました！営業リスト作成を開始します...⏳
3. [エラー発生]
4. ボット: ❌ リスト作成に失敗しました
          原因: API接続エラー / タイムアウト / データ取得失敗
          再度実行しますか？ [はい] [いいえ]
5a. ユーザーが「はい」を選択 → 再実行
5b. ユーザーが「いいえ」を選択 → 終了
6. [ログ記録（エラー情報含む）]
```

### 4.3 Dify連携仕様

#### 4.3.1 API呼び出し
- **エンドポイント**: Dify Workflow API（詳細はDifyドキュメント参照）
- **メソッド**: POST
- **認証**: Bearer Token（API Key）
- **リクエストボディ**:
```json
{
  "inputs": {
    "keyword": "横浜市に工場を持つ製造業"
  }
}
```

#### 4.3.2 レスポンス処理
- **成功時**: 企業リストデータを取得 → CSV変換
- **失敗時**: エラーメッセージをSlackに返信
- **タイムアウト**: 5分（調整可能）

### 4.4 データベーススキーマ

#### 4.4.1 ai_employees テーブル
AI社員の定義を管理

| カラム名 | 型 | 説明 | 制約 |
|---|---|---|---|
| id | UUID | 主キー | PRIMARY KEY |
| name | VARCHAR(255) | AI社員名（例：営業AI） | NOT NULL |
| bot_mention | VARCHAR(255) | メンション文字列（例：@営業AI） | NOT NULL, UNIQUE |
| platform | ENUM | プラットフォーム（slack, line, teams） | NOT NULL |
| channel_id | VARCHAR(255) | 対象チャンネルID | NOT NULL |
| dify_workflow_id | VARCHAR(255) | DifyワークフローID | NOT NULL |
| dify_api_endpoint | TEXT | DifyエンドポイントURL | NOT NULL |
| is_active | BOOLEAN | 有効/無効 | DEFAULT true |
| created_at | TIMESTAMP | 作成日時 | DEFAULT NOW() |
| updated_at | TIMESTAMP | 更新日時 | DEFAULT NOW() |

#### 4.4.2 execution_logs テーブル
実行履歴を記録

| カラム名 | 型 | 説明 | 制約 |
|---|---|---|---|
| id | UUID | 主キー | PRIMARY KEY |
| ai_employee_id | UUID | AI社員ID | FOREIGN KEY |
| user_id | VARCHAR(255) | ユーザーID | NOT NULL |
| user_name | VARCHAR(255) | ユーザー名 | NOT NULL |
| platform | ENUM | プラットフォーム | NOT NULL |
| channel_id | VARCHAR(255) | チャンネルID | NOT NULL |
| input_keyword | TEXT | 入力キーワード | NOT NULL |
| status | ENUM | ステータス（success, error, timeout） | NOT NULL |
| result_count | INTEGER | 結果件数 | NULLABLE |
| processing_time_seconds | INTEGER | 処理時間（秒） | NULLABLE |
| error_message | TEXT | エラーメッセージ | NULLABLE |
| created_at | TIMESTAMP | 実行日時 | DEFAULT NOW() |

---

## 5. 非機能要件

### 5.1 パフォーマンス
- **処理時間**: Difyワークフローに依存（数分）
- **同時実行**: 順次処理（キュー方式）
- **タイムアウト**: 5分（調整可能）

### 5.2 可用性
- **稼働時間**: 24時間365日（Railwayの稼働率に依存）
- **メンテナンス**: 必要時に計画停止

### 5.3 スケーラビリティ
- **第一号リリース**: 単一チャンネル、単一ワークフロー
- **将来拡張**:
  - 複数チャンネル対応
  - 複数ワークフロー管理（経理AI、他部署AI）
  - ワークフローIDとチャンネルのマッピング管理

### 5.4 セキュリティ
- **認証情報管理**: 環境変数で管理（GitHub Secrets、Railway環境変数）
- **アクセス制限**: 特定チャンネルのみで動作
- **データ保護**: ログに機密情報を含めない

### 5.5 保守性
- **コード品質**: TypeScript型定義、ESLintルール適用
- **ドキュメント**: README.md、API仕様書
- **エラーログ**: 構造化ログ（JSON形式推奨）

---

## 6. 制約事項

### 6.1 技術的制約
- Railwayの無料枠制限（月500時間）
- Dify APIのレート制限（プランに依存）
- Slackファイルアップロード制限（ファイルサイズ上限）

### 6.2 運用制約
- 使用回数制限なし（将来的に制限追加の可能性）
- 特定チャンネルのみで動作
- ユーザー制限なし（チャンネルメンバー全員が使用可能）

---

## 7. セットアップ要件

### 7.1 Slack側の準備
1. Slack Appの作成
2. Bot Token Scopesの設定:
   - `app_mentions:read` - @メンション検知
   - `chat:write` - メッセージ送信
   - `files:write` - ファイルアップロード
   - `channels:history` - チャンネル履歴読み取り（必要に応じて）
3. Event Subscriptionsの有効化:
   - `app_mention` イベント購読
4. OAuth Tokenの取得
5. ボットを対象チャンネルに招待

### 7.2 Dify側の準備
1. ワークフローの確認・調整（API経由での実行に対応）
2. API Keyの発行
3. エンドポイントURLの確認

### 7.3 Supabase側の準備
1. Supabaseプロジェクト作成
2. PostgreSQLデータベース確認
3. Database URLの取得
4. Prismaマイグレーション実行

### 7.4 Railway側の準備
1. プロジェクト作成
2. GitHub連携（オプション）
3. 環境変数の設定

---

## 8. 環境変数一覧（改訂版）

| 変数名 | 説明 | 例 | 必須 |
|---|---|---|---|
| `DATABASE_URL` | PostgreSQL接続URL | `postgresql://user:pass@host:5432/db` | ✅ |
| `DIRECT_URL` | Supabase Direct URL（マイグレーション用） | `postgresql://...` | ✅ |
| `SLACK_BOT_TOKEN` | Slack Bot User OAuth Token | `xoxb-...` | ✅ |
| `SLACK_SIGNING_SECRET` | Slackリクエスト検証用 | `abc123...` | ✅ |
| `SLACK_APP_TOKEN` | Socket Mode用（オプション） | `xapp-...` | - |
| `PORT` | サーバーポート番号 | `3000` | - |
| `NODE_ENV` | 実行環境 | `development` / `production` | ✅ |

---

## 9. 開発フェーズ

### Phase 1: MVP開発（第一号AI社員）
**並列開発可能タスク（Git worktree活用）**

#### Task A: データベース基盤（`feature/database-schema`）
- [ ] Supabaseプロジェクト作成
- [ ] Prismaセットアップ
- [ ] スキーマ定義（ai_employees, execution_logs）
- [ ] マイグレーション実行
- [ ] Seedデータ作成

#### Task B: コアドメイン層（`feature/core-domain`）
- [ ] TypeScriptプロジェクト初期化
- [ ] レイヤード構造のディレクトリ作成
- [ ] Domain層の型定義・Entity
- [ ] WorkflowService実装
- [ ] LogService実装

#### Task C: Dify連携層（`feature/dify-integration`）
- [ ] Dify APIクライアント実装
- [ ] リトライ機能
- [ ] エラーハンドリング
- [ ] CSV生成ユーティリティ

#### Task D: Slackアダプター層（`feature/slack-adapter`）
- [ ] Slack App設定
- [ ] Slack Boltセットアップ
- [ ] SlackAdapter実装
- [ ] メッセージフォーマッター

#### Task E: 統合・デプロイ（`feature/integration`）
- [ ] 各レイヤーの統合
- [ ] E2Eテスト
- [ ] Railway デプロイ設定
- [ ] 本番動作確認

### Phase 2: 他部署展開準備
- [ ] 複数ワークフロー対応（設定ファイル化）
- [ ] 管理画面（オプション）
- [ ] ダッシュボード（オプション）
- [ ] 経理AI社員開発

### Phase 3: 運用・改善
- [ ] モニタリング強化
- [ ] パフォーマンスチューニング
- [ ] 利用統計分析

---

## 10. 成功指標（KPI）

### Phase 1（営業AI）
- デプロイ成功率: 100%
- リクエスト成功率: 90%以上
- 平均処理時間: 5分以内
- エラー率: 10%以下

### Phase 2以降
- 展開部署数: 3部署以上
- 月間利用回数: 50回以上
- ユーザー満足度: 調査実施

---

## 11. リスク管理

| リスク | 影響度 | 対策 |
|---|---|---|
| Dify APIの不安定性 | 高 | リトライ機能、タイムアウト設定 |
| Railwayの無料枠超過 | 中 | 使用状況モニタリング、有料プラン検討 |
| Slackレート制限 | 中 | レート制限対応、キューイング |
| CSV生成失敗 | 中 | エラーハンドリング、フォールバック |

---

## 12. 今後の拡張性

### 12.1 想定される追加機能
- 複数のAI社員（経理、人事、マーケティング等）
- インタラクティブなUIコンポーネント（Slack Block Kit）
- スケジュール実行（定期レポート自動生成）
- 条件分岐（ユーザーの選択に応じた処理）
- 他サービス連携（Google Drive、Salesforce等）

### 12.2 アーキテクチャの進化
- ✅ **データベース導入済み**（PostgreSQL + Prisma）
- ✅ **レイヤード構造採用済み**（マルチプラットフォーム対応）
- マイクロサービス化（各AI社員を独立サービスに）
- 管理コンソール開発（Next.js + Supabase）
- リアルタイムダッシュボード（実行状況可視化）

---

## 13. 参考資料

- [Slack Bolt for JavaScript](https://slack.dev/bolt-js/)
- [Dify API Documentation](https://docs.dify.ai/)
- [Railway Documentation](https://docs.railway.app/)
- [Supabase Documentation](https://supabase.com/docs)
- [Prisma Documentation](https://www.prisma.io/docs)

---

## 14. 変更履歴

| 日付 | バージョン | 変更内容 | 担当者 |
|---|---|---|---|
| 2026-01-19 | 1.0 | 初版作成（Airtable/Notionベース） | Claude & User |
| 2026-01-19 | 2.0 | 改訂版（PostgreSQL + Prismaベース、マルチプラットフォーム対応設計） | Claude & User |

---

**承認**
- [ ] プロジェクトオーナー
- [ ] 技術責任者
- [ ] 開発チーム
