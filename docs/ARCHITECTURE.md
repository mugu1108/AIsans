# AI-Shine アーキテクチャ設計書

**バージョン**: 1.0
**作成日**: 2026-01-19
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

AI-Shineは以下の設計原則に基づいて構築されます：

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

### 2.1 全体像

```
┌───────────────────────────────────────────────────────────┐
│                    Interface Layer                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │SlackAdapter  │  │ LINEAdapter  │  │TeamsAdapter  │    │
│  │(implements   │  │(implements   │  │(implements   │    │
│  │PlatformIfc)  │  │PlatformIfc)  │  │PlatformIfc)  │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
└───────────────────────────────────────────────────────────┘
                            ↓
┌───────────────────────────────────────────────────────────┐
│                   Application Layer                        │
│  ┌──────────────────┐  ┌────────────────────────────┐    │
│  │ MessageHandler   │  │ WorkflowOrchestrator       │    │
│  │ - handleMention  │  │ - executeWorkflow          │    │
│  │ - routeToService │  │ - retryOnFailure           │    │
│  └──────────────────┘  └────────────────────────────┘    │
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
│  │ PrismaClient     │  │ DifyAPIClient              │    │
│  │ - database ops   │  │ - callWorkflow             │    │
│  │                  │  │ - handleResponse           │    │
│  └──────────────────┘  └────────────────────────────┘    │
└───────────────────────────────────────────────────────────┘
```

### 2.2 レイヤーの責務

#### 2.2.1 Interface Layer（インターフェース層）
**責務**: 外部システム（Slack、LINE等）との通信を担当

- プラットフォーム固有のSDKを使用
- メッセージの受信・送信
- ファイルのアップロード
- 共通インターフェース `PlatformAdapter` を実装

**依存関係**: Application Layer に依存

#### 2.2.2 Application Layer（アプリケーション層）
**責務**: ビジネスロジックの調整・オーケストレーション

- メッセージルーティング
- ワークフロー実行の制御
- エラーハンドリング・リトライ
- レスポンスのフォーマット

**依存関係**: Domain Layer に依存

#### 2.2.3 Domain Layer（ドメイン層）
**責務**: コアビジネスロジックとエンティティ

- AI社員の管理
- 実行ログの記録・取得
- ビジネスルールの実装
- データモデルの定義

**依存関係**: Infrastructure Layer に依存（DI経由）

#### 2.2.4 Infrastructure Layer（インフラ層）
**責務**: 外部リソースへのアクセス

- データベースアクセス（Prisma）
- 外部API呼び出し（Dify）
- ファイルシステム操作
- 環境変数管理

**依存関係**: 外部ライブラリのみに依存

---

## 3. ディレクトリ構造

```
ai-shain/
├── README.md
├── REQUIREMENTS.md
├── ARCHITECTURE.md
├── IMPLEMENTATION_PLAN.md
├── package.json
├── tsconfig.json
├── .env.example
├── .gitignore
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
│   │   ├── slack/
│   │   │   ├── SlackAdapter.ts
│   │   │   └── SlackMessageFormatter.ts
│   │   ├── line/               # (Phase 2)
│   │   └── teams/              # (Phase 2)
│   │
│   ├── application/            # Application Layer
│   │   ├── MessageHandler.ts
│   │   ├── WorkflowOrchestrator.ts
│   │   └── ResponseFormatter.ts
│   │
│   ├── domain/                 # Domain Layer
│   │   ├── entities/
│   │   │   ├── AIEmployee.ts
│   │   │   └── ExecutionLog.ts
│   │   ├── services/
│   │   │   ├── AIEmployeeService.ts
│   │   │   └── LogService.ts
│   │   └── types/
│   │       └── index.ts        # 共通型定義
│   │
│   ├── infrastructure/         # Infrastructure Layer
│   │   ├── database/
│   │   │   ├── prisma.ts       # Prismaクライアント初期化
│   │   │   └── repositories/
│   │   │       ├── AIEmployeeRepository.ts
│   │   │       └── LogRepository.ts
│   │   ├── dify/
│   │   │   ├── DifyClient.ts
│   │   │   └── DifyTypes.ts
│   │   └── csv/
│   │       └── CSVGenerator.ts
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

### 4.1 正常系フロー（営業リスト作成）

```
[ユーザー] @営業AI 横浜市に工場を持つ製造業
    ↓
[Slack] app_mention イベント発火
    ↓
[SlackAdapter] イベント受信
    ↓ (1) メッセージパース
[MessageHandler] handleMention()
    ↓ (2) AI社員を特定
[AIEmployeeService] findByMention("営業AI")
    ↓ (3) DB問い合わせ
[AIEmployeeRepository] Prismaでクエリ
    ↓ (4) AI社員情報を返却
[MessageHandler] ← AIEmployee entity
    ↓ (5) ワークフロー実行依頼
[WorkflowOrchestrator] executeWorkflow(employee, keyword)
    ↓ (6) Dify API呼び出し
[DifyClient] callWorkflow(workflowId, keyword)
    ↓ (7) HTTPリクエスト
[Dify API] ワークフロー実行
    ↓ (8) 結果返却（企業リスト）
[DifyClient] ← JSON response
    ↓ (9) CSV変換
[CSVGenerator] generateCSV(data)
    ↓ (10) ログ記録
[LogService] recordExecution(log)
    ↓ (11) DB保存
[LogRepository] Prismaで挿入
    ↓ (12) Slackに返信
[SlackAdapter] sendFile(channelId, csv)
    ↓
[ユーザー] ✅ CSV受信
```

### 4.2 エラー系フロー

```
[DifyClient] callWorkflow() → エラー発生
    ↓
[WorkflowOrchestrator] catch error
    ↓ (1) リトライ判定
    if (retryable) {
        ↓ (2) 指数バックオフで再実行
        retry with backoff
    } else {
        ↓ (3) ログ記録
        [LogService] recordExecution(status: "error")
        ↓ (4) ユーザーに通知
        [SlackAdapter] sendErrorMessage()
        ↓ (5) リトライ提案（Block Kit）
        [ユーザー] [はい] [いいえ]
    }
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
│ bot_mention (VARCHAR, UQ)  │
│ platform (ENUM)            │
│ channel_id (VARCHAR)       │
│ dify_workflow_id (VARCHAR) │
│ dify_api_endpoint (TEXT)   │
│ is_active (BOOLEAN)        │
│ created_at (TIMESTAMP)     │
│ updated_at (TIMESTAMP)     │
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
│ ai_employee_id (UUID, FK)  │
│ user_id (VARCHAR)          │
│ user_name (VARCHAR)        │
│ platform (ENUM)            │
│ channel_id (VARCHAR)       │
│ input_keyword (TEXT)       │
│ status (ENUM)              │
│ result_count (INTEGER)     │
│ processing_time_seconds    │
│ error_message (TEXT)       │
│ created_at (TIMESTAMP)     │
└────────────────────────────┘
```

### 5.2 Prismaスキーマ（抜粋）

```prisma
// prisma/schema.prisma

generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
  directUrl = env("DIRECT_URL")
}

enum Platform {
  slack
  line
  teams
}

enum ExecutionStatus {
  success
  error
  timeout
}

model AIEmployee {
  id                String   @id @default(uuid())
  name              String   @db.VarChar(255)
  botMention        String   @unique @map("bot_mention") @db.VarChar(255)
  platform          Platform
  channelId         String   @map("channel_id") @db.VarChar(255)
  difyWorkflowId    String   @map("dify_workflow_id") @db.VarChar(255)
  difyApiEndpoint   String   @map("dify_api_endpoint") @db.Text
  isActive          Boolean  @default(true) @map("is_active")
  createdAt         DateTime @default(now()) @map("created_at")
  updatedAt         DateTime @updatedAt @map("updated_at")

  executionLogs     ExecutionLog[]

  @@map("ai_employees")
}

model ExecutionLog {
  id                     String          @id @default(uuid())
  aiEmployeeId           String          @map("ai_employee_id")
  userId                 String          @map("user_id") @db.VarChar(255)
  userName               String          @map("user_name") @db.VarChar(255)
  platform               Platform
  channelId              String          @map("channel_id") @db.VarChar(255)
  inputKeyword           String          @map("input_keyword") @db.Text
  status                 ExecutionStatus
  resultCount            Int?            @map("result_count")
  processingTimeSeconds  Int?            @map("processing_time_seconds")
  errorMessage           String?         @map("error_message") @db.Text
  createdAt              DateTime        @default(now()) @map("created_at")

  aiEmployee             AIEmployee      @relation(fields: [aiEmployeeId], references: [id])

  @@map("execution_logs")
}
```

---

## 6. API設計

### 6.1 内部API（レイヤー間通信）

#### PlatformAdapter インターフェース

```typescript
// src/interfaces/PlatformAdapter.ts

export interface MessageEvent {
  userId: string;
  userName: string;
  channelId: string;
  text: string;
  mention?: string;
}

export interface PlatformAdapter {
  /**
   * メッセージを送信
   */
  sendMessage(channelId: string, text: string): Promise<void>;

  /**
   * ファイルを送信
   */
  sendFile(
    channelId: string,
    file: Buffer,
    filename: string,
    comment?: string
  ): Promise<void>;

  /**
   * エラーメッセージを送信（Block Kit対応）
   */
  sendErrorWithRetry(
    channelId: string,
    errorMessage: string,
    onRetry: () => void
  ): Promise<void>;

  /**
   * メンションイベントを購読
   */
  onMention(handler: (event: MessageEvent) => Promise<void>): void;
}
```

#### WorkflowOrchestrator

```typescript
// src/application/WorkflowOrchestrator.ts

export interface WorkflowExecutionResult {
  success: boolean;
  data?: any;
  resultCount?: number;
  processingTimeSeconds: number;
  errorMessage?: string;
}

export class WorkflowOrchestrator {
  async executeWorkflow(
    employee: AIEmployee,
    keyword: string
  ): Promise<WorkflowExecutionResult> {
    // ワークフロー実行ロジック
  }

  async retryWorkflow(
    employee: AIEmployee,
    keyword: string,
    maxRetries: number = 3
  ): Promise<WorkflowExecutionResult> {
    // リトライロジック
  }
}
```

#### AIEmployeeService

```typescript
// src/domain/services/AIEmployeeService.ts

export class AIEmployeeService {
  async findByMention(mention: string): Promise<AIEmployee | null> {
    // @営業AI → "営業AI" でDB検索
  }

  async findByChannelId(channelId: string): Promise<AIEmployee[]> {
    // チャンネルIDから対象AI社員を取得
  }

  async getActiveEmployees(): Promise<AIEmployee[]> {
    // 有効なAI社員一覧を取得
  }
}
```

### 6.2 外部API（Dify）

#### DifyClient

```typescript
// src/infrastructure/dify/DifyClient.ts

export interface DifyWorkflowRequest {
  inputs: {
    keyword: string;
  };
}

export interface DifyWorkflowResponse {
  data: {
    outputs: any;
  };
}

export class DifyClient {
  async callWorkflow(
    endpoint: string,
    workflowId: string,
    request: DifyWorkflowRequest
  ): Promise<DifyWorkflowResponse> {
    // Dify API呼び出し
  }
}
```

---

## 7. エラーハンドリング戦略

### 7.1 エラー分類

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

// Dify APIエラー
export class DifyAPIError extends AIShineError {
  constructor(message: string, public statusCode: number) {
    super(message, 'DIFY_API_ERROR', statusCode >= 500);
  }
}
```

### 7.2 リトライ戦略

```typescript
// src/application/WorkflowOrchestrator.ts

async retryWithBackoff<T>(
  fn: () => Promise<T>,
  maxRetries: number = 3
): Promise<T> {
  let lastError: Error;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;

      if (error instanceof AIShineError && !error.retryable) {
        throw error; // リトライ不可なら即座にthrow
      }

      if (attempt < maxRetries) {
        const delay = Math.pow(2, attempt) * 1000; // 指数バックオフ
        await new Promise(resolve => setTimeout(resolve, delay));
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
const messageHandler = new MessageHandler(
  aiEmployeeService,
  workflowOrchestrator,
  logService
);

lineAdapter.onMention(async (event) => {
  await messageHandler.handle(event, lineAdapter);
});
```

### 8.2 新しいAI社員の追加

**コード変更不要！データベースにレコード追加のみ**

```sql
INSERT INTO ai_employees (
  id, name, bot_mention, platform, channel_id,
  dify_workflow_id, dify_api_endpoint, is_active
) VALUES (
  gen_random_uuid(),
  '経理AI',
  '@経理AI',
  'slack',
  'C987654321',
  'workflow-accounting-123',
  'https://api.dify.ai/v1/workflows/run',
  true
);
```

### 8.3 新しい機能の追加

**例: スケジュール実行機能**

1. `src/application/SchedulerService.ts` を追加
2. Domain層のサービスを再利用
3. Infrastructure層でcronジョブ設定

**既存コードへの影響**: なし（新しいレイヤーを追加するのみ）

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

- Dify APIのレート制限を考慮
- キュー方式で順次処理
- バックプレッシャー機構（将来実装）

---

## 10. パフォーマンス最適化

### 10.1 データベース

- 適切なインデックス設定
  - `ai_employees.bot_mention` (UNIQUE)
  - `execution_logs.ai_employee_id` (FK)
  - `execution_logs.created_at` (時系列クエリ用)

### 10.2 キャッシング

- AI社員情報のメモリキャッシュ（変更頻度が低い）
- Redis導入（Phase 2以降）

### 10.3 非同期処理

- ワークフロー実行は非同期
- ユーザーには即座に「処理開始」を通知
- 完了後に結果を返信

---

## 11. 監視・ログ

### 11.1 ログレベル

- **DEBUG**: 開発時の詳細情報
- **INFO**: 通常の動作ログ（リクエスト受信、処理完了）
- **WARN**: 警告（リトライ発生）
- **ERROR**: エラー（失敗、例外）

### 11.2 構造化ログ

```json
{
  "timestamp": "2026-01-19T10:30:00Z",
  "level": "INFO",
  "message": "Workflow execution started",
  "context": {
    "aiEmployeeId": "uuid-123",
    "userId": "U123456",
    "keyword": "横浜市に工場を持つ製造業"
  }
}
```

---

**承認**
- [ ] アーキテクト
- [ ] 技術リード
- [ ] 開発チーム
