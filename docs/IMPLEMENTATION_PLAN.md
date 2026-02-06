# AI-Shine 実装計画書

**バージョン**: 2.0（Phase 1完了版）
**作成日**: 2026-01-19
**最終更新**: 2026-02-06
**プロジェクト**: AI-Shine（AI社員システム）

---

## 目次

1. [実装概要](#1-実装概要)
2. [Phase 1: 完了サマリー](#2-phase-1-完了サマリー)
3. [実装済みコンポーネント](#3-実装済みコンポーネント)
4. [Phase 2以降の計画](#4-phase-2以降の計画)
5. [運用情報](#5-運用情報)

---

## 1. 実装概要

### 1.1 実装戦略

AI-Shineは**レイヤード・アーキテクチャ**を採用し、各層を独立して開発・テスト可能な構造としました。

### 1.2 技術的な変更点

**当初の計画からの変更:**
- ~~Dify API~~ → **GAS WebApp（Google Apps Script）** に変更
  - Scraipin APIとの連携をGAS経由で実装
  - スプレッドシート作成もGAS内で実行
- スレッド返信機能を追加
- Google Sheets連携（GAS経由）を追加

---

## 2. Phase 1: 完了サマリー

### 2.1 達成した機能

**営業リスト作成ボット「Alex」** が以下の機能で稼働中：

| 機能 | 説明 | 状態 |
|---|---|---|
| Slackメンション応答 | `@Alex [地域] [業種]` で起動 | **完了** |
| GAS連携 | Scraipin API経由で企業リスト取得 | **完了** |
| CSV生成・送信 | 結果をCSVでSlackに添付 | **完了** |
| スプレッドシート作成 | Google Driveに自動保存 | **完了** |
| スレッド返信 | 全通知を元メッセージのスレッド内に | **完了** |
| ログ記録 | 実行履歴をPostgreSQLに保存 | **完了** |
| エラーハンドリング | リトライ機能付きエラー通知 | **完了** |

### 2.2 完了した開発タスク

#### Task A: データベース基盤
- [x] Supabaseプロジェクト作成
- [x] Prisma初期化・スキーマ定義
- [x] マイグレーション実行
- [x] Seedデータ作成

#### Task B: コアドメイン層
- [x] TypeScriptプロジェクト初期化
- [x] レイヤード構造のディレクトリ作成
- [x] Domain層の型定義・Entity
- [x] AIEmployeeService実装
- [x] LogService実装
- [x] Repository層実装

#### Task C: GAS連携層（当初はDify連携）
- [x] GASClient実装
- [x] クエリパーサー実装
- [x] リトライ機能
- [x] エラーハンドリング

#### Task D: Slackアダプター層
- [x] Slack App設定
- [x] Slack Boltセットアップ
- [x] SlackAdapter実装
- [x] スレッド返信機能
- [x] ファイルアップロード機能
- [x] イベント重複防止機能

#### Task E: 統合・デプロイ
- [x] 各レイヤーの統合
- [x] 環境変数管理
- [x] Railwayデプロイ設定
- [x] 本番動作確認

#### Task F: Google Sheets連携（追加タスク）
- [x] GAS WebAppでスプレッドシート作成機能実装
- [x] CSV + スプレッドシート同時作成
- [x] スプレッドシートURL通知機能

---

## 3. 実装済みコンポーネント

### 3.1 ディレクトリ構造

```
src/
├── index.ts                    # エントリーポイント
├── interfaces/
│   ├── PlatformAdapter.ts      # 共通インターフェース
│   └── slack/
│       └── SlackAdapter.ts     # Slack実装
├── application/
│   └── WorkflowOrchestrator.ts # ワークフロー制御
├── domain/
│   ├── entities/
│   │   ├── AIEmployee.ts
│   │   └── ExecutionLog.ts
│   ├── services/
│   │   ├── AIEmployeeService.ts
│   │   └── LogService.ts
│   └── types/
│       └── index.ts
├── infrastructure/
│   ├── database/
│   │   ├── prisma.ts
│   │   └── repositories/
│   │       ├── AIEmployeeRepository.ts
│   │       └── LogRepository.ts
│   └── gas/
│       ├── GASClient.ts
│       ├── GASTypes.ts
│       └── queryParser.ts
├── config/
│   └── env.ts
└── utils/
    ├── logger.ts
    └── errors.ts
```

### 3.2 主要クラス・関数

| ファイル | クラス/関数 | 責務 |
|---|---|---|
| `index.ts` | `main()` | アプリケーション起動・イベントハンドラ登録 |
| `SlackAdapter.ts` | `SlackAdapter` | Slack通信（メッセージ・ファイル送信） |
| `WorkflowOrchestrator.ts` | `WorkflowOrchestrator` | GAS呼び出し・リトライ制御 |
| `AIEmployeeService.ts` | `AIEmployeeService` | AI社員検索・管理 |
| `LogService.ts` | `LogService` | 実行ログ記録 |
| `GASClient.ts` | `GASClient` | GAS WebApp呼び出し |
| `queryParser.ts` | `parseQuery()` | クエリを地域・業種に分解 |

### 3.3 データベーステーブル

| テーブル | 用途 | レコード例 |
|---|---|---|
| `ai_employees` | AI社員の定義 | Alex（営業リスト作成） |
| `execution_logs` | 実行履歴 | 成功/失敗ログ |

---

## 4. Phase 2以降の計画

### 4.1 Phase 2: 他部署展開準備

| タスク | 説明 | 優先度 |
|---|---|---|
| 複数ワークフロー対応 | AI社員ごとに異なるGAS URLを設定 | 高 |
| 経理AI社員開発 | 経費精算・請求書処理 | 中 |
| 管理画面 | AI社員の設定をWebUIで管理 | 低 |
| ダッシュボード | 利用統計の可視化 | 低 |

### 4.2 Phase 3: プラットフォーム拡張

| タスク | 説明 | 優先度 |
|---|---|---|
| LINE対応 | LINEAdapter実装 | 中 |
| Teams対応 | TeamsAdapter実装 | 低 |
| Webhook対応 | 外部サービスとの連携 | 低 |

### 4.3 Phase 4: 運用・改善

| タスク | 説明 | 優先度 |
|---|---|---|
| モニタリング強化 | エラー通知・アラート | 高 |
| パフォーマンス改善 | レスポンス時間短縮 | 中 |
| テスト整備 | 単体・統合テスト追加 | 中 |

---

## 5. 運用情報

### 5.1 環境変数

```bash
# 必須
DATABASE_URL=postgresql://...
DIRECT_URL=postgresql://...
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
SLACK_APP_TOKEN=xapp-...
GAS_API_URL=https://script.google.com/...

# オプション
GOOGLE_DRIVE_FOLDER_ID=...
PORT=3000
NODE_ENV=production
```

### 5.2 デプロイ

**ホスティング**: Railway
- GitHub連携で自動デプロイ
- `main`ブランチへのマージで本番反映

### 5.3 コマンド

```bash
# 開発
npm run dev        # 開発サーバー起動
npm run build      # ビルド

# データベース
npx prisma migrate dev    # マイグレーション（開発）
npx prisma generate       # クライアント生成
npx prisma studio         # データ閲覧GUI
```

### 5.4 ログ確認

Railway Dashboardでログを確認可能。

---

## 6. 変更履歴

| 日付 | バージョン | 変更内容 |
|---|---|---|
| 2026-01-19 | 1.0 | 初版作成（Difyベース計画） |
| 2026-02-06 | 2.0 | Phase 1完了版（GASベース、全タスク完了） |

---

**承認**
- [x] プロジェクトマネージャー
- [x] 技術リード
- [x] 開発チーム
