# AI-Shine アーキテクチャ設計書

**バージョン**: 2.0（Phase 1完了版）
**作成日**: 2026-01-19
**最終更新**: 2026-02-06
**プロジェクト**: AI-Shine（AI社員システム）

---

## 目次

1. [アーキテクチャ概要](#1-アーキテクチャ概要)
2. [レイヤード構造](#2-レイヤード構造)
3. [ディレクトリ構造](#3-ディレクトリ構造)
4. [データフロー](#4-データフロー)
5. [データベース設計](#5-データベース設計)
6. [API設計](#6-api設計)
7. [エラーハンドリング戦略](#7-エラーハンドリング戦略)
8. [拡張性への配慮](#8-拡張性への配慮)

---

## 1. アーキテクチャ概要

### 1.1 設計原則

AI-Shineは以下の設計原則に基づいて構築されています：

1. **レイヤード・アーキテクチャ（Layered Architecture）**
   - 関心の分離（Separation of Concerns）
   - 各レイヤーの独立性と交換可能性

2. **プラットフォーム非依存（Platform-Agnostic）**
   - Adapter パターンでプラットフォーム固有ロジックを分離
   - Slack、LINE、Teams等への横展開が容易

3. **データ駆動（Data-Driven）**
   - AI社員の設定をデータベースで管理
   - コード変更なしで新しいAI社員を追加可能

4. **拡張性優先（Extensibility First）**
   - 新機能追加が既存コードに影響しない設計
   - インターフェース駆動開発

---

## 2. レイヤード構造

### 2.1 全体像（Phase 1完了版）

```
┌───────────────────────────────────────────────────────────┐
│                    Interface Layer                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │SlackAdapter  │  │ LINEAdapter  │  │TeamsAdapter  │    │
│  │  [実装済]    │  │   [予定]     │  │   [予定]     │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
└───────────────────────────────────────────────────────────┘
                            ↓
┌───────────────────────────────────────────────────────────┐
│                   Application Layer                        │
│  ┌────────────────────────────────────────────────┐      │
│  │ WorkflowOrchestrator                            │      │
│  │ - executeWorkflow (クエリ実行)                  │      │
│  │ - retryWithBackoff (リトライ処理)               │      │
│  └────────────────────────────────────────────────┘      │
└───────────────────────────────────────────────────────────┘
                            ↓
┌───────────────────────────────────────────────────────────┐
│                      Domain Layer                          │
│  ┌──────────────────┐  ┌────────────────────────────┐    │
│  │ AIEmployee       │  │ ExecutionLog               │    │
│  │ (Entity)         │  │ (Entity)                   │    │
│  ├──────────────────┤  ├────────────────────────────┤    │
│  │AIEmployeeService │  │ LogService                 │    │
│  │ - findByMention  │  │ - recordExecution          │    │
│  │ - getActive      │  │ - queryLogs                │    │
│  └──────────────────┘  └────────────────────────────┘    │
└───────────────────────────────────────────────────────────┘
                            ↓
┌───────────────────────────────────────────────────────────┐
│                  Infrastructure Layer                      │
│  ┌──────────────────┐  ┌────────────────────────────┐    │
│  │ PrismaClient     │  │ GASClient                  │    │
│  │ - database ops   │  │ - fetchCSV                 │    │
│  │                  │  │ - fetchBoth (CSV+Sheet)    │    │
│  └──────────────────┘  └────────────────────────────┘    │
│                              ↓                             │
│                   ┌────────────────────────────┐          │
│                   │ Google Apps Script WebApp  │          │
│                   │ - Scraipin API連携         │          │
│                   │ - スプレッドシート作成     │          │
│                   └────────────────────────────┘          │
└───────────────────────────────────────────────────────────┘
```

### 2.2 レイヤーの責務

#### 2.2.1 Interface Layer（インターフェース層）
**責務**: 外部システム（Slack、LINE等）との通信を担当

- プラットフォーム固有のSDKを使用
- メッセージの受信・送信
- ファイルのアップロード
- スレッド返信の管理
- 共通インターフェース `PlatformAdapter` を実装

**実装済みコンポーネント**:
- `SlackAdapter` - Slack Bolt SDKを使用
- `PlatformAdapter` - 共通インターフェース定義

**依存関係**: Application Layer に依存

#### 2.2.2 Application Layer（アプリケーション層）
**責務**: ビジネスロジックの調整・オーケストレーション

- クエリのパース（地域・業種の抽出）
- GAS WebApp呼び出しの制御
- エラーハンドリング・リトライ
- レスポンスのフォーマット

**実装済みコンポーネント**:
- `WorkflowOrchestrator` - ワークフロー実行制御
- `queryParser` - クエリ解析

**依存関係**: Domain Layer, Infrastructure Layer に依存

#### 2.2.3 Domain Layer（ドメイン層）
**責務**: コアビジネスロジックとエンティティ

- AI社員の管理
- 実行ログの記録・取得
- ビジネスルールの実装
- データモデルの定義

**実装済みコンポーネント**:
- `AIEmployee` - AI社員エンティティ
- `ExecutionLog` - 実行ログエンティティ
- `AIEmployeeService` - AI社員管理サービス
- `LogService` - ログ記録サービス

**依存関係**: Infrastructure Layer に依存（DI経由）

#### 2.2.4 Infrastructure Layer（インフラ層）
**責務**: 外部リソースへのアクセス

- データベースアクセス（Prisma）
- GAS WebApp呼び出し
- 環境変数管理

**実装済みコンポーネント**:
- `prisma.ts` - Prismaクライアント初期化
- `AIEmployeeRepository` - AI社員リポジトリ
- `LogRepository` - ログリポジトリ
- `GASClient` - GAS WebApp呼び出し
- `GASTypes` - GAS API型定義
- `queryParser` - クエリ解析ユーティリティ

**依存関係**: 外部ライブラリのみに依存

---

## 3. ディレクトリ構造（実装済み）

```
ai-shain/
├── README.md
├── CLAUDE.md                    # 開発ガイドライン
├── package.json
├── tsconfig.json
├── .env.example
├── .gitignore
│
├── docs/                        # ドキュメント
│   ├── REQUIREMENTS.md
│   ├── ARCHITECTURE.md          # 本ドキュメント
│   ├── IMPLEMENTATION_PLAN.md
│   └── DIAGRAMS.md
│
├── prisma/
│   ├── schema.prisma           # Prismaスキーマ定義
│   ├── migrations/             # マイグレーションファイル
│   └── seed.ts                 # Seedデータ
│
├── src/
│   ├── index.ts                # アプリケーションエントリーポイント
│   │
│   ├── interfaces/             # Interface Layer
│   │   ├── PlatformAdapter.ts  # 共通インターフェース定義
│   │   └── slack/
│   │       └── SlackAdapter.ts # Slack実装
│   │
│   ├── application/            # Application Layer
│   │   └── WorkflowOrchestrator.ts
│   │
│   ├── domain/                 # Domain Layer
│   │   ├── entities/
│   │   │   ├── AIEmployee.ts
│   │   │   └── ExecutionLog.ts
│   │   ├── services/
│   │   │   ├── AIEmployeeService.ts
│   │   │   └── LogService.ts
│   │   └── types/
│   │       └── index.ts
│   │
│   ├── infrastructure/         # Infrastructure Layer
│   │   ├── database/
│   │   │   ├── prisma.ts
│   │   │   └── repositories/
│   │   │       ├── AIEmployeeRepository.ts
│   │   │       └── LogRepository.ts
│   │   ├── gas/                # GAS連携（Phase 1で実装）
│   │   │   ├── GASClient.ts
│   │   │   ├── GASTypes.ts
│   │   │   └── queryParser.ts
│   │   └── google/             # Google API直接連携（未使用）
│   │       └── GoogleSheetsClient.ts
│   │
│   ├── config/
│   │   └── env.ts              # 環境変数管理
│   │
│   └── utils/
│       ├── logger.ts           # ロギングユーティリティ
│       └── errors.ts           # カスタムエラークラス
│
└── tests/
    ├── unit/
    ├── integration/
    └── e2e/
```

---

## 4. データフロー

### 4.1 正常系フロー（営業リスト作成 - Phase 1実装済み）

```
[ユーザー] @Alex 東京 IT企業
    ↓
[Slack] app_mention イベント発火
    ↓
[SlackAdapter] イベント受信・重複チェック
    ↓ (1) ユーザー情報取得・メッセージパース
[index.ts] メインハンドラ
    ↓ (2) AI社員を特定
[AIEmployeeService] findByMention()
    ↓ (3) DB問い合わせ
[AIEmployeeRepository] Prismaでクエリ
    ↓ (4) AI社員情報を返却
[index.ts] ← AIEmployee entity
    ↓ (5) 処理開始通知を送信（スレッド作成）
[SlackAdapter] sendMessage() → threadTs取得
    ↓ (6) ワークフロー実行依頼
[WorkflowOrchestrator] executeWorkflow(query, maxRetries, folderId)
    ↓ (7) クエリをパース
[queryParser] parseQuery() → {region: "東京", industry: "IT企業"}
    ↓ (8) GAS WebApp呼び出し（CSV+スプレッドシート同時作成）
[GASClient] fetchBoth(region, industry, count, folderId)
    ↓ (9) HTTPリクエスト
[GAS WebApp] Scraipin API呼び出し + スプレッドシート作成
    ↓ (10) 結果返却（CSV Base64 + スプレッドシートURL）
[GASClient] ← {csvBuffer, spreadsheetUrl, rowCount}
    ↓ (11) ワークフロー結果返却
[WorkflowOrchestrator] ← WorkflowExecutionResult
    ↓ (12) 完了メッセージ送信（スレッド内）
[SlackAdapter] sendMessage(completeMessage, threadTs)
    ↓ (13) CSVファイル送信（スレッド内）
[SlackAdapter] sendFile(csvBuffer, filename, threadTs)
    ↓ (14) ログ記録
[LogService] recordExecution(log)
    ↓ (15) DB保存
[LogRepository] Prismaで挿入
    ↓
[ユーザー] ✅ スレッド内でCSV + スプレッドシートURL受信
```

### 4.2 エラー系フロー

```
[GASClient] fetchBoth() → エラー発生
    ↓
[WorkflowOrchestrator] catch error
    ↓ (1) リトライ判定
    if (retryable && attempt < maxRetries) {
        ↓ (2) 指数バックオフで再実行
        retry with backoff (1秒, 2秒, 4秒...)
    } else {
        ↓ (3) エラー結果を返却
        return {success: false, errorMessage}
    }
    ↓
[index.ts]
    ↓ (4) エラーメッセージ送信（スレッド内）
    [SlackAdapter] sendErrorWithRetry(errorMessage, threadTs)
    ↓ (5) ログ記録
    [LogService] recordExecution(status: "error")
    ↓
[ユーザー] ❌ エラー詳細 + リトライボタン
```

---

## 5. データベース設計

### 5.1 ER図

```
┌────────────────────────────┐
│      ai_employees          │
├────────────────────────────┤
│ id (UUID, PK)              │
│ name (VARCHAR)             │
│ botMention (VARCHAR)       │
│ platform (ENUM)            │
│ channelId (VARCHAR)        │
│ difyWorkflowId (VARCHAR)   │  ※レガシー（GAS移行済み）
│ difyApiEndpoint (VARCHAR)  │  ※レガシー（GAS移行済み）
│ isActive (BOOLEAN)         │
│ createdAt (TIMESTAMP)      │
│ updatedAt (TIMESTAMP)      │
└────────────────────────────┘
         │ 1
         │
         │ has many
         │
         ↓ N
┌────────────────────────────┐
│     execution_logs         │
├────────────────────────────┤
│ id (UUID, PK)              │
│ aiEmployeeId (UUID, FK)    │
│ userId (VARCHAR)           │
│ userName (VARCHAR)         │
│ platform (ENUM)            │
│ channelId (VARCHAR)        │
│ inputKeyword (TEXT)        │
│ status (ENUM)              │
│ resultCount (INTEGER)      │
│ processingTimeSeconds      │
│ errorMessage (TEXT)        │
│ createdAt (TIMESTAMP)      │
└────────────────────────────┘
```

### 5.2 Prismaスキーマ（実装済み）

```prisma
// prisma/schema.prisma

generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider  = "postgresql"
  url       = env("DATABASE_URL")
  directUrl = env("DIRECT_URL")
}

enum Platform {
  SLACK
  LINE
  TEAMS
}

enum ExecutionStatus {
  SUCCESS
  ERROR
  TIMEOUT
}

model AIEmployee {
  id              String   @id @default(uuid())
  name            String
  botMention      String
  platform        Platform
  channelId       String
  difyWorkflowId  String   // レガシー（GAS移行済み）
  difyApiEndpoint String   // レガシー（GAS移行済み）
  isActive        Boolean  @default(true)
  createdAt       DateTime @default(now())
  updatedAt       DateTime @updatedAt

  executionLogs ExecutionLog[]

  @@map("ai_employees")
}

model ExecutionLog {
  id                    String          @id @default(uuid())
  aiEmployeeId          String
  userId                String
  userName              String
  platform              Platform
  channelId             String
  inputKeyword          String
  status                ExecutionStatus
  resultCount           Int?
  processingTimeSeconds Float?
  errorMessage          String?
  createdAt             DateTime        @default(now())

  aiEmployee AIEmployee @relation(fields: [aiEmployeeId], references: [id], onDelete: Cascade)

  @@map("execution_logs")
}
```

---

## 6. API設計

### 6.1 内部API（レイヤー間通信）

#### PlatformAdapter インターフェース（実装済み）

```typescript
// src/interfaces/PlatformAdapter.ts

export interface MessageEvent {
  userId: string;
  userName: string;
  channelId: string;
  text: string;
  mention?: string;
  ts: string;          // メッセージのタイムスタンプ
  threadTs?: string;   // スレッドのルートタイムスタンプ
}

export interface PlatformAdapter {
  sendMessage(channelId: string, text: string, threadTs?: string): Promise<string>;
  sendFile(channelId: string, file: Buffer, filename: string, comment?: string, threadTs?: string): Promise<void>;
  sendErrorWithRetry(channelId: string, errorMessage: string, threadTs?: string): Promise<void>;
  onMention(handler: (event: MessageEvent) => Promise<void>): void;
}
```

#### WorkflowOrchestrator（実装済み）

```typescript
// src/application/WorkflowOrchestrator.ts

export interface WorkflowExecutionResult {
  success: boolean;
  csvBuffer?: Buffer;
  resultCount?: number;
  processingTimeSeconds: number;
  errorMessage?: string;
  spreadsheetUrl?: string;  // スプレッドシートURL（作成時のみ）
}

export class WorkflowOrchestrator {
  async executeWorkflow(
    query: string,
    maxRetries: number = 3,
    folderId?: string        // スプレッドシート保存先フォルダID
  ): Promise<WorkflowExecutionResult>;
}
```

### 6.2 外部API（GAS WebApp）

#### GASClient（実装済み）

```typescript
// src/infrastructure/gas/GASClient.ts

export class GASClient {
  // CSVのみ取得
  async fetchCSV(region: string, industry: string, count?: number): Promise<Buffer>;

  // CSV + スプレッドシート同時作成
  async fetchBoth(
    region: string,
    industry: string,
    count?: number,
    folderId?: string
  ): Promise<{csvBuffer: Buffer; spreadsheetUrl?: string; rowCount: number}>;

  // スプレッドシートのみ作成
  async createSpreadsheet(
    region: string,
    industry: string,
    count?: number,
    folderId?: string
  ): Promise<GASSpreadsheetResponse>;
}
```

#### GAS WebApp リクエスト/レスポンス

```typescript
// src/infrastructure/gas/GASTypes.ts

export interface GASRequest {
  region: string;
  industry: string;
  count?: number;
  outputFormat?: 'csv' | 'spreadsheet' | 'both';
  folderId?: string;
}

export interface GASBothResponse {
  status: 'success' | 'error';
  message?: string;
  csvBase64: string;          // CSV（Base64エンコード）
  spreadsheetId?: string;
  spreadsheetUrl?: string;
  rowCount?: number;
}
```

---

## 7. エラーハンドリング戦略

### 7.1 エラー分類（実装済み）

```typescript
// src/utils/errors.ts

export class AIShineError extends Error {
  constructor(
    message: string,
    public code: string,
    public retryable: boolean = false
  ) {
    super(message);
    this.name = 'AIShineError';
  }
}

// ネットワークエラー（リトライ可能）
export class NetworkError extends AIShineError {
  constructor(message: string) {
    super(message, 'NETWORK_ERROR', true);
  }
}

// タイムアウトエラー（リトライ可能）
export class TimeoutError extends AIShineError {
  constructor(message: string) {
    super(message, 'TIMEOUT_ERROR', true);
  }
}

// バリデーションエラー（リトライ不可）
export class ValidationError extends AIShineError {
  constructor(message: string) {
    super(message, 'VALIDATION_ERROR', false);
  }
}

// AI社員未発見エラー（リトライ不可）
export class AIEmployeeNotFoundError extends AIShineError {
  constructor(mention: string) {
    super(`AI社員が見つかりません: ${mention}`, 'AI_EMPLOYEE_NOT_FOUND', false);
  }
}
```

### 7.2 リトライ戦略（実装済み）

```typescript
// src/application/WorkflowOrchestrator.ts

private async retryWithBackoff<T>(
  fn: () => Promise<T>,
  maxRetries: number
): Promise<T> {
  let lastError: Error | unknown;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;

      // リトライ不可なエラーの場合は即座にthrow
      if (error instanceof AIShineError && !error.retryable) {
        throw error;
      }

      // 最後の試行でない場合はリトライ
      if (attempt < maxRetries) {
        const delay = Math.pow(2, attempt) * 1000; // 1秒, 2秒, 4秒...
        await this.sleep(delay);
      }
    }
  }

  throw lastError;
}
```

---

## 8. 拡張性への配慮

### 8.1 新しいプラットフォームの追加

**例: LINE対応を追加する場合**

1. `src/interfaces/line/LINEAdapter.ts` を作成
2. `PlatformAdapter` インターフェースを実装
3. `src/index.ts` で初期化して追加

```typescript
// 既存コードへの影響なし
const lineAdapter = new LINEAdapter(config);

lineAdapter.onMention(async (event) => {
  // 同じハンドラロジックを使用可能
});
```

### 8.2 新しいAI社員の追加

**コード変更不要！データベースにレコード追加のみ**

```sql
INSERT INTO ai_employees (
  id, name, "botMention", platform, "channelId",
  "difyWorkflowId", "difyApiEndpoint", "isActive"
) VALUES (
  gen_random_uuid(),
  '経理AI',
  '@経理AI',
  'SLACK',
  'C987654321',
  'legacy-field',
  'legacy-field',
  true
);
```

### 8.3 新しいワークフローの追加

GAS WebApp側で新しいエンドポイントを追加し、環境変数で切り替え可能。

---

## 9. セキュリティ考慮事項

### 9.1 認証・認可

- 環境変数で管理（`.env` ファイル、Git管理外）
- Railway環境変数で本番用トークンを管理
- Slack Signing Secretでリクエスト検証

### 9.2 データ保護

- ログにAPIキーや機密情報を含めない
- ユーザー入力のサニタイゼーション
- SQLインジェクション対策（Prismaが自動対応）

### 9.3 レート制限対応

- GAS WebAppの実行制限を考慮
- 指数バックオフでリトライ
- 順次処理で同時実行を制限

---

## 10. パフォーマンス最適化

### 10.1 データベース

- 適切なインデックス設定
  - `execution_logs.aiEmployeeId` (FK)
  - `execution_logs.createdAt` (時系列クエリ用)

### 10.2 非同期処理

- ワークフロー実行は非同期
- ユーザーには即座に「処理開始」を通知（スレッド作成）
- 完了後にスレッド内で結果を返信

### 10.3 イベント重複防止

- `processedEvents` Setで処理済みイベントを追跡
- メモリリーク防止のため古いエントリを定期的にクリア

---

## 11. 監視・ログ

### 11.1 ログレベル

- **DEBUG**: 開発時の詳細情報
- **INFO**: 通常の動作ログ（リクエスト受信、処理完了）
- **WARN**: 警告（リトライ発生）
- **ERROR**: エラー（失敗、例外）

### 11.2 構造化ログ（実装済み）

```typescript
// src/utils/logger.ts
export interface Logger {
  debug(message: string, context?: Record<string, unknown>): void;
  info(message: string, context?: Record<string, unknown>): void;
  warn(message: string, context?: Record<string, unknown>): void;
  error(message: string, error?: Error, context?: Record<string, unknown>): void;
}
```

---

## 12. 変更履歴

| 日付 | バージョン | 変更内容 |
|---|---|---|
| 2026-01-19 | 1.0 | 初版作成（Difyベース設計） |
| 2026-02-06 | 2.0 | Phase 1完了版（GASベース、スレッド返信、Google Sheets連携） |

---

**承認**
- [x] アーキテクト
- [x] 技術リード
- [x] 開発チーム
