# AI-Shine 要件定義書

**バージョン**: 3.0（Phase 1完了版）
**作成日**: 2026-01-19
**最終更新**: 2026-02-06
**プロジェクト名**: AI-Shine（AI社員システム）

---

## 1. プロジェクト概要

### 1.1 プロジェクトビジョン
AI-Shineはマルチプラットフォーム対応の社内業務自動化プラットフォームです。Slack、LINE、Microsoft Teamsなど複数のコミュニケーションツールに対応し、各部署に特化したAI社員（ボット）を配置して定型業務や情報収集タスクを自動化します。

**長期ビジョン**: パッケージ化されたAI社員システムとして、プラットフォームや部署を問わず横展開可能な汎用的なアーキテクチャを採用します。

### 1.2 対象範囲
- **フェーズ1**：営業部門向けリスト作成AI「Alex」 **← 完了**
- **フェーズ2以降**：経理、その他部署への横展開

### 1.3 目的
- 社内業務の効率化
- 定型タスクの自動化によるリソース最適化
- 各部署に特化したAI活用の推進

---

## 2. システムアーキテクチャ

### 2.1 全体構成図（Phase 1完了版）

```
┌─────────────────────────────────────┐
│  Platform Layer (Adapters)          │
│  ┌─────────┬─────────┬─────────┐   │
│  │ Slack   │  LINE   │ Teams   │   │
│  │ (実装済)│ (予定)  │ (予定)  │   │
│  └─────────┴─────────┴─────────┘   │
└─────────────────────────────────────┘
              ↕
┌─────────────────────────────────────┐
│  AI-Shine Core Backend (Railway)    │
│  ┌─────────────────────────────┐   │
│  │  Application Layer          │   │
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
│  GAS WebApp │    │ PostgreSQL  │
│ (Scraipin)  │    │ (Supabase)  │
└─────────────┘    └─────────────┘
       ↓
┌─────────────────────────────────────┐
│  Google Workspace                    │
│  ┌─────────────────────────────┐   │
│  │  Google Drive                │   │
│  │  - 共有フォルダ              │   │
│  │  - スプレッドシート作成      │   │
│  └─────────────────────────────┘   │
└─────────────────────────────────────┘
```

### 2.2 コンポーネント（Phase 1完了版）

| レイヤー | コンポーネント | 役割 | 技術 | 状態 |
|---|---|---|---|---|
| **Interface** | SlackAdapter | Slack固有の通信処理 | Slack Bolt | **実装完了** |
| **Application** | WorkflowOrchestrator | GAS連携・実行管理 | TypeScript | **実装完了** |
| **Domain** | AIEmployeeService | AI社員の管理・設定 | TypeScript | **実装完了** |
| **Domain** | LogService | 実行履歴の記録・取得 | TypeScript + Prisma | **実装完了** |
| **Infrastructure** | GASClient | GAS WebApp呼び出し | TypeScript + Axios | **実装完了** |
| **Infrastructure** | Database | データ永続化 | PostgreSQL (Supabase) | **実装完了** |
| **Hosting** | App Server | アプリケーション実行 | Railway | **デプロイ完了** |

---

## 3. 技術スタック

### 3.1 開発環境
- **言語**: TypeScript
- **ランタイム**: Node.js 18.x以上
- **パッケージマネージャー**: npm

### 3.2 主要ライブラリ・SDK
- `@slack/bolt`: Slackボット開発
- `@prisma/client`: データベースORM
- `prisma`: スキーマ管理・マイグレーション
- `axios`: HTTP通信（GAS WebApp呼び出し）
- `dotenv`: 環境変数管理

### 3.3 外部サービス
- **Slack Workspace**: ボット配置先（Phase 1）
- **Google Apps Script**: ワークフロー実行エンジン（Scraipin API連携）
- **Google Drive**: スプレッドシート保存先
- **Supabase**: PostgreSQLホスティング
- **Railway**: アプリケーションホスティング

### 3.4 認証・トークン管理
- Slack Bot Token（環境変数）
- Slack App Token（Socket Mode用）
- Slack Signing Secret（リクエスト検証）
- GAS WebApp URL（環境変数）
- Google Drive Folder ID（環境変数）
- Supabase Database URL（環境変数）

---

## 4. 機能要件

### 4.1 第一号AI社員：営業リスト作成ボット「Alex」 **← 実装完了**

#### 4.1.1 実装済み機能
| ID | 機能名 | 説明 | 状態 |
|---|---|---|---|
| F-001 | キーワード受付 | @メンションでキーワードを受け取る | **完了** |
| F-002 | GAS WebApp呼び出し | キーワードをGAS経由でScraipin APIに送信 | **完了** |
| F-003 | 処理状態通知 | 開始・完了・エラーをスレッド内で通知 | **完了** |
| F-004 | CSV生成・添付 | 結果をCSV形式でSlackスレッドに添付 | **完了** |
| F-005 | スプレッドシート作成 | Google Driveにスプレッドシートを自動作成 | **完了** |
| F-006 | スプレッドシートURL通知 | 作成したスプレッドシートのURLをSlackで通知 | **完了** |
| F-007 | ログ記録 | 実行履歴をPostgreSQLに保存 | **完了** |
| F-008 | エラーハンドリング | エラー時の詳細メッセージとリトライ提案 | **完了** |
| F-009 | スレッド返信 | 全ての通知を元メッセージのスレッド内に表示 | **完了** |

#### 4.1.2 入力仕様
- **入力形式**: `@Alex [地域] [業種]`
- **キーワード例**:
  - 「東京 IT企業」
  - 「横浜市 製造業」
  - 「大阪 食品メーカー」
- **文字数制限**: Slack制限に準拠

#### 4.1.3 出力仕様
- **CSV形式**: UTF-8 BOM付き
- **ファイル名**: `sales_list_YYYYMMDDTHHMMSS.csv`
- **スプレッドシート**: 指定のGoogle Driveフォルダに自動保存
- **列構成**:
  - 企業名
  - 企業URL
  - 問い合わせURL
  - その他（Scraipin APIレスポンスに依存）
- **件数**: 約30社

### 4.2 ユーザーフロー（実装済み）

#### 4.2.1 正常フロー
```
1. ユーザー: @Alex 東京 IT企業
2. Alex: 了解しました！営業リスト作成を開始します...⏳
3. [バックエンド → GAS WebApp → Scraipin API]
4. [数秒〜数十秒待機]
5. Alex: ✅ 完了しました！30社のリストを作成しました
        📊 Googleスプレッドシートも作成しました！
        [スプレッドシートURL]
6. Alex: 📎 sales_list_20260206T143025.csv（ファイル添付）
7. [ログ記録]

※ 全ての返信は元のメッセージのスレッド内に表示
```

#### 4.2.2 エラーフロー
```
1. ユーザー: @Alex キーワード
2. Alex: 了解しました！営業リスト作成を開始します...⏳
3. [エラー発生]
4. Alex: ❌ エラーが発生しました
        *エラー詳細*
        [エラーメッセージ]
        [リトライボタン] [キャンセルボタン]
5. [ログ記録（エラー情報含む）]
```

### 4.3 GAS連携仕様（実装済み）

#### 4.3.1 API呼び出し
- **エンドポイント**: GAS WebApp URL
- **メソッド**: POST
- **リクエストボディ**:
```json
{
  "region": "東京",
  "industry": "IT企業",
  "count": 30,
  "outputFormat": "both",
  "folderId": "Google DriveフォルダID"
}
```

#### 4.3.2 レスポンス処理
- **outputFormat: "both"の場合**:
  - CSVデータ（Base64エンコード）
  - スプレッドシートURL
  - 件数
- **タイムアウト**: 5分
- **リトライ**: 指数バックオフ（最大3回）

### 4.4 データベーススキーマ（実装済み）

#### 4.4.1 ai_employees テーブル
AI社員の定義を管理

| カラム名 | 型 | 説明 | 制約 |
|---|---|---|---|
| id | UUID | 主キー | PRIMARY KEY |
| name | VARCHAR | AI社員名（例：Alex） | NOT NULL |
| botMention | VARCHAR | メンション文字列 | NOT NULL |
| platform | ENUM | プラットフォーム（SLACK, LINE, TEAMS） | NOT NULL |
| channelId | VARCHAR | 対象チャンネルID | NOT NULL |
| difyWorkflowId | VARCHAR | ワークフローID（レガシー） | NOT NULL |
| difyApiEndpoint | VARCHAR | APIエンドポイント（レガシー） | NOT NULL |
| isActive | BOOLEAN | 有効/無効 | DEFAULT true |
| createdAt | TIMESTAMP | 作成日時 | DEFAULT NOW() |
| updatedAt | TIMESTAMP | 更新日時 | AUTO UPDATE |

#### 4.4.2 execution_logs テーブル
実行履歴を記録

| カラム名 | 型 | 説明 | 制約 |
|---|---|---|---|
| id | UUID | 主キー | PRIMARY KEY |
| aiEmployeeId | UUID | AI社員ID | FOREIGN KEY |
| userId | VARCHAR | ユーザーID | NOT NULL |
| userName | VARCHAR | ユーザー名 | NOT NULL |
| platform | ENUM | プラットフォーム | NOT NULL |
| channelId | VARCHAR | チャンネルID | NOT NULL |
| inputKeyword | TEXT | 入力キーワード | NOT NULL |
| status | ENUM | ステータス（SUCCESS, ERROR, TIMEOUT） | NOT NULL |
| resultCount | INTEGER | 結果件数 | NULLABLE |
| processingTimeSeconds | FLOAT | 処理時間（秒） | NULLABLE |
| errorMessage | TEXT | エラーメッセージ | NULLABLE |
| createdAt | TIMESTAMP | 実行日時 | DEFAULT NOW() |

---

## 5. 非機能要件

### 5.1 パフォーマンス
- **処理時間**: 通常10〜60秒（Scraipin API依存）
- **同時実行**: 順次処理
- **タイムアウト**: 5分

### 5.2 可用性
- **稼働時間**: 24時間365日（Railway稼働率に依存）
- **メンテナンス**: 必要時に計画停止

### 5.3 スケーラビリティ
- **Phase 1**: 単一チャンネル、単一ワークフロー（実装完了）
- **将来拡張**:
  - 複数チャンネル対応
  - 複数ワークフロー管理（経理AI、他部署AI）
  - 他プラットフォーム対応（LINE, Teams）

### 5.4 セキュリティ
- **認証情報管理**: 環境変数で管理
- **アクセス制限**: 特定チャンネルのみで動作
- **データ保護**: ログに機密情報を含めない

### 5.5 保守性
- **コード品質**: TypeScript型定義、レイヤード・アーキテクチャ
- **ドキュメント**: 各種設計書完備
- **エラーログ**: 構造化ログ

---

## 6. 環境変数一覧（最新）

| 変数名 | 説明 | 例 | 必須 |
|---|---|---|---|
| `DATABASE_URL` | PostgreSQL接続URL | `postgresql://user:pass@host:5432/db` | **必須** |
| `DIRECT_URL` | Supabase Direct URL | `postgresql://...` | **必須** |
| `SLACK_BOT_TOKEN` | Slack Bot User OAuth Token | `xoxb-...` | **必須** |
| `SLACK_SIGNING_SECRET` | Slackリクエスト検証用 | `abc123...` | **必須** |
| `SLACK_APP_TOKEN` | Socket Mode用 | `xapp-...` | **必須** |
| `GAS_API_URL` | GAS WebApp URL | `https://script.google.com/...` | **必須** |
| `GOOGLE_DRIVE_FOLDER_ID` | スプレッドシート保存先フォルダID | `1GmLdANj...` | 任意 |
| `PORT` | サーバーポート番号 | `3000` | 任意 |
| `NODE_ENV` | 実行環境 | `production` | 任意 |

---

## 7. 開発フェーズ

### Phase 1: MVP開発（第一号AI社員「Alex」）**← 完了**

#### 完了したタスク
- [x] Supabaseプロジェクト作成
- [x] Prismaセットアップ・スキーマ定義
- [x] マイグレーション実行
- [x] レイヤード構造のディレクトリ作成
- [x] Domain層の型定義・Entity
- [x] AIEmployeeService実装
- [x] LogService実装
- [x] GASClient実装（Scraipin API連携）
- [x] WorkflowOrchestrator実装
- [x] SlackAdapter実装
- [x] スレッド返信機能実装
- [x] Google Sheets連携（GAS経由）
- [x] Railwayデプロイ
- [x] 本番動作確認

### Phase 2: 他部署展開準備（予定）
- [ ] 複数ワークフロー対応
- [ ] 管理画面（オプション）
- [ ] ダッシュボード（オプション）
- [ ] 経理AI社員開発

### Phase 3: 運用・改善（予定）
- [ ] モニタリング強化
- [ ] パフォーマンスチューニング
- [ ] 利用統計分析

---

## 8. 成功指標（KPI）

### Phase 1（営業AI「Alex」）**← 達成**
- デプロイ成功率: 100% **達成**
- リクエスト成功率: 90%以上 **運用中**
- 平均処理時間: 5分以内 **達成**
- エラー率: 10%以下 **運用中**

### Phase 2以降
- 展開部署数: 3部署以上
- 月間利用回数: 50回以上
- ユーザー満足度: 調査実施

---

## 9. 変更履歴

| 日付 | バージョン | 変更内容 | 担当者 |
|---|---|---|---|
| 2026-01-19 | 1.0 | 初版作成 | Claude & User |
| 2026-01-19 | 2.0 | 改訂版（PostgreSQL + Prisma、マルチプラットフォーム設計） | Claude & User |
| 2026-02-06 | 3.0 | Phase 1完了版（GASベース、スレッド返信、Google Sheets連携） | Claude & User |

---

**承認**
- [x] プロジェクトオーナー
- [x] 技術責任者
- [x] 開発チーム
