# AI-Shine

マルチプラットフォーム対応のAI社員システム

## 概要

AI-ShineはSlack、LINE、Microsoft Teamsなど複数のプラットフォームに対応したAI社員（ボット）システムです。各部署に特化したAI社員を配置し、定型業務や情報収集タスクを自動化します。

**Phase 1 完了**: Slack対応 + 営業リスト作成AI「Alex」

## 主な機能

- **営業リスト作成**: `@Alex [地域] [業種]` でメンションすると、約30社の営業リストを自動生成
- **CSV出力**: 結果をCSV形式でSlackに添付
- **スプレッドシート作成**: Google Driveに自動保存、URLをSlackで通知
- **スレッド返信**: 全ての通知を元メッセージのスレッド内に表示
- **実行ログ**: 全ての実行履歴をデータベースに記録

## 技術スタック

| 項目 | 技術 |
|---|---|
| **言語** | TypeScript (Node.js) |
| **データベース** | PostgreSQL (Supabase) + Prisma ORM |
| **プラットフォーム** | Slack Bolt SDK |
| **ワークフロー** | Google Apps Script (Scraipin API連携) |
| **ホスティング** | Railway |

## アーキテクチャ

```
┌─────────────────────────────────────┐
│  Slack (Interface Layer)            │
└─────────────────────────────────────┘
              ↕
┌─────────────────────────────────────┐
│  AI-Shine Core Backend (Railway)    │
│  - WorkflowOrchestrator             │
│  - AIEmployeeService                │
│  - LogService                       │
└─────────────────────────────────────┘
       ↕                    ↕
┌─────────────┐    ┌─────────────┐
│  GAS WebApp │    │ PostgreSQL  │
│ (Scraipin)  │    │ (Supabase)  │
└─────────────┘    └─────────────┘
       ↓
┌─────────────────────────────────────┐
│  Google Drive (スプレッドシート)     │
└─────────────────────────────────────┘
```

## ディレクトリ構造

```
ai-shain/
├── docs/                # ドキュメント
│   ├── REQUIREMENTS.md      # 要件定義書
│   ├── ARCHITECTURE.md      # アーキテクチャ設計書
│   └── IMPLEMENTATION_PLAN.md # 実装計画書
├── prisma/              # データベーススキーマ
├── src/                 # ソースコード
│   ├── interfaces/      # プラットフォーム固有（Slack等）
│   ├── application/     # オーケストレーション
│   ├── domain/          # ビジネスロジック
│   └── infrastructure/  # 外部連携（DB、GAS）
├── CLAUDE.md            # 開発ガイドライン
└── package.json
```

## セットアップ

### 前提条件

- Node.js 18.x以上
- npm
- PostgreSQL（Supabase推奨）
- Slackワークスペース + Slack App

### インストール

```bash
# 依存関係インストール
npm install

# 環境変数設定
cp .env.example .env
# .envを編集

# Prismaセットアップ
npx prisma migrate dev
npx prisma generate

# 開発サーバー起動
npm run dev
```

### 環境変数

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

## 使い方

Slackで以下のようにメンション：

```
@Alex 東京 IT企業
```

**レスポンス例：**
```
了解しました！営業リスト作成を開始します...

✅ 完了しました！30社のリストを作成しました

📊 Googleスプレッドシートも作成しました！
https://docs.google.com/spreadsheets/d/...

📎 sales_list_20260206T143025.csv
```

## 開発コマンド

```bash
npm run dev        # 開発サーバー起動
npm run build      # ビルド
npm run start      # 本番サーバー起動

# Prisma
npx prisma migrate dev    # マイグレーション（開発）
npx prisma generate       # クライアント生成
npx prisma studio         # データ閲覧GUI
```

## ドキュメント

- [要件定義書](./docs/REQUIREMENTS.md)
- [アーキテクチャ設計書](./docs/ARCHITECTURE.md)
- [実装計画書](./docs/IMPLEMENTATION_PLAN.md)
- [開発ガイドライン](./CLAUDE.md)

## 今後の展開（Phase 2以降）

- 経理AI社員の追加
- LINE / Teams対応
- 管理画面・ダッシュボード

## ライセンス

MIT
