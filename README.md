# AI-Shine

マルチプラットフォーム対応のAI社員システム

## 概要

AI-ShineはSlack、LINE、Microsoft Teamsなど複数のプラットフォームに対応したAI社員（ボット）システムです。各部署に特化したAI社員を配置し、定型業務や情報収集タスクを自動化します。

**Phase 1**: Slack対応 + 営業リスト作成AI（Dify連携）

## 技術スタック

- **言語**: TypeScript (Node.js)
- **データベース**: PostgreSQL (Supabase) + Prisma ORM
- **プラットフォーム**: Slack Bolt SDK
- **ワークフロー**: Dify API
- **ホスティング**: Railway

## ディレクトリ構造

```
ai-shain/
├── .claude/              # Claude Code設定
│   ├── commands/         # カスタムコマンド
│   ├── rules/           # ルールファイル
│   └── settings.json    # フック設定
├── docs/                # ドキュメント
│   ├── REQUIREMENTS.md
│   ├── ARCHITECTURE.md
│   └── IMPLEMENTATION_PLAN.md
├── prisma/              # データベーススキーマ
├── src/                 # ソースコード
│   ├── interfaces/      # プラットフォーム固有
│   ├── application/     # オーケストレーション
│   ├── domain/          # ビジネスロジック
│   └── infrastructure/  # 外部連携
├── tests/               # テスト
├── CLAUDE.md           # Claude Code設定
└── package.json
```

## セットアップ

```bash
# 依存関係インストール
npm install

# 環境変数設定
cp .env.example .env
# .envを編集して実際の値を設定

# Prismaセットアップ
npx prisma migrate dev
npx prisma generate

# 開発サーバー起動
npm run dev
```

## ドキュメント

- [要件定義書](./docs/REQUIREMENTS.md)
- [アーキテクチャ設計書](./docs/ARCHITECTURE.md)
- [実装計画書](./docs/IMPLEMENTATION_PLAN.md)
- [開発ガイドライン](./CLAUDE.md)

詳細は[IMPLEMENTATION_PLAN.md](./docs/IMPLEMENTATION_PLAN.md)を参照してください。

## ライセンス

MIT
