# AI-Shine システム図解

**最終更新**: 2026-01-21
**進捗**: Phase 1 - 67%完了

---

## 目次

1. [アーキテクチャ概要図](#1-アーキテクチャ概要図)
2. [レイヤー依存関係図](#2-レイヤー依存関係図)
3. [データフロー図（正常系）](#3-データフロー図正常系)
4. [クラス図（実装済みコンポーネント）](#4-クラス図実装済みコンポーネント)
5. [データベースER図](#5-データベースer図)
6. [進捗状況図](#6-進捗状況図)
7. [ディレクトリ構造図](#7-ディレクトリ構造図)
8. [エラーハンドリングフロー図](#8-エラーハンドリングフロー図)

---

## 1. アーキテクチャ概要図

```mermaid
graph TB
    subgraph "External Systems"
        Slack[Slack Platform]
        Dify[Dify API]
        DB[(PostgreSQL<br/>Supabase)]
    end

    subgraph "AI-Shine System"
        subgraph "Interface Layer"
            SA[SlackAdapter]
            PA[PlatformAdapter<br/>Interface]
        end

        subgraph "Application Layer"
            WO[WorkflowOrchestrator]
        end

        subgraph "Domain Layer"
            AE[AIEmployee<br/>Entity]
            EL[ExecutionLog<br/>Entity]
            AES[AIEmployeeService<br/>未実装]
            LS[LogService<br/>未実装]
        end

        subgraph "Infrastructure Layer"
            DC[DifyClient]
            CSV[CSVGenerator]
            PC[Prisma Client<br/>未実装]
            AER[AIEmployeeRepository<br/>未実装]
            LR[LogRepository<br/>未実装]
        end
    end

    Slack <--> SA
    SA -.implements.-> PA
    SA --> WO
    WO --> AES
    WO --> DC
    WO --> CSV
    AES --> AER
    LS --> LR
    DC --> Dify
    AER --> PC
    LR --> PC
    PC --> DB

    style SA fill:#90EE90
    style PA fill:#90EE90
    style WO fill:#90EE90
    style DC fill:#90EE90
    style CSV fill:#90EE90
    style AE fill:#90EE90
    style EL fill:#90EE90
    style AES fill:#FFB6C1
    style LS fill:#FFB6C1
    style PC fill:#FFB6C1
    style AER fill:#FFB6C1
    style LR fill:#FFB6C1
```

**凡例**:
- 🟢 緑: 実装済み
- 🔴 ピンク: 未実装（Task 11-12）

---

## 2. レイヤー依存関係図

```mermaid
graph TD
    Interface[Interface Layer<br/>プラットフォーム固有]
    Application[Application Layer<br/>オーケストレーション]
    Domain[Domain Layer<br/>ビジネスロジック]
    Infrastructure[Infrastructure Layer<br/>外部連携]

    Interface --> Application
    Application --> Domain
    Domain --> Infrastructure

    style Interface fill:#E6F3FF
    style Application fill:#FFF4E6
    style Domain fill:#E8F5E9
    style Infrastructure fill:#FFF0F5
```

**ルール**:
- ❌ 上位レイヤーへの依存禁止
- ❌ レイヤーのスキップ禁止
- ✅ 下位レイヤーのみ依存可能

---

## 3. データフロー図（正常系）

```mermaid
sequenceDiagram
    actor User
    participant Slack
    participant SlackAdapter
    participant WorkflowOrchestrator
    participant AIEmployeeService
    participant AIEmployeeRepository
    participant DifyClient
    participant DifyAPI
    participant CSVGenerator
    participant LogService
    participant LogRepository
    participant Database

    User->>Slack: @営業AI 横浜市に工場を持つ製造業
    Slack->>SlackAdapter: app_mention event
    SlackAdapter->>SlackAdapter: parseMessage()
    SlackAdapter->>AIEmployeeService: findByMention("@営業AI")
    AIEmployeeService->>AIEmployeeRepository: findByMention("@営業AI")
    AIEmployeeRepository->>Database: SELECT * FROM ai_employees
    Database-->>AIEmployeeRepository: AIEmployee data
    AIEmployeeRepository-->>AIEmployeeService: AIEmployee entity
    AIEmployeeService-->>SlackAdapter: AIEmployee entity

    SlackAdapter->>Slack: "了解しました！営業リスト作成を開始..."

    SlackAdapter->>WorkflowOrchestrator: executeWorkflow(employee, keyword)
    WorkflowOrchestrator->>DifyClient: callWorkflow(endpoint, request)
    DifyClient->>DifyAPI: POST /v1/workflows/run
    DifyAPI-->>DifyClient: workflow response
    DifyClient-->>WorkflowOrchestrator: DifyWorkflowResponse

    WorkflowOrchestrator->>CSVGenerator: generate(companies)
    CSVGenerator-->>WorkflowOrchestrator: CSV Buffer

    WorkflowOrchestrator->>LogService: recordExecution(log)
    LogService->>LogRepository: create(log)
    LogRepository->>Database: INSERT INTO execution_logs
    Database-->>LogRepository: success
    LogRepository-->>LogService: success
    LogService-->>WorkflowOrchestrator: success

    WorkflowOrchestrator-->>SlackAdapter: WorkflowExecutionResult
    SlackAdapter->>Slack: sendFile(csv, "sales_list.csv")
    Slack-->>User: ✅ 完了！CSVファイル
```

---

## 4. クラス図（実装済みコンポーネント）

```mermaid
classDiagram
    %% Interface Layer
    class PlatformAdapter {
        <<interface>>
        +sendMessage(channelId, text) Promise~void~
        +sendFile(channelId, file, filename, comment) Promise~void~
        +sendErrorWithRetry(channelId, errorMessage, threadTs) Promise~void~
        +onMention(handler) void
    }

    class SlackAdapter {
        -app: App
        +constructor(botToken, signingSecret)
        +start(port) Promise~void~
        +sendMessage(channelId, text) Promise~void~
        +sendFile(channelId, file, filename, comment) Promise~void~
        +sendErrorWithRetry(channelId, errorMessage, threadTs) Promise~void~
        +onMention(handler) void
        -extractMention(text) string
    }

    %% Application Layer
    class WorkflowOrchestrator {
        -difyClient: DifyClient
        -csvGenerator: CSVGenerator
        +constructor(difyClient, csvGenerator)
        +executeWorkflow(endpoint, keyword) Promise~WorkflowExecutionResult~
        -retryWithBackoff(fn, maxRetries) Promise~T~
    }

    %% Domain Layer
    class AIEmployee {
        +id: string
        +name: string
        +botMention: string
        +platform: Platform
        +channelId: string
        +difyWorkflowId: string
        +difyApiEndpoint: string
        +isActive: boolean
        +createdAt: Date
        +updatedAt: Date
    }

    class ExecutionLog {
        +id: string
        +aiEmployeeId: string
        +userId: string
        +userName: string
        +platform: Platform
        +channelId: string
        +inputKeyword: string
        +status: ExecutionStatus
        +resultCount: number
        +processingTimeSeconds: number
        +errorMessage: string
        +createdAt: Date
    }

    %% Infrastructure Layer
    class DifyClient {
        -client: AxiosInstance
        -apiKey: string
        +constructor(apiKey)
        +callWorkflow(endpoint, request) Promise~DifyWorkflowResponse~
    }

    class CSVGenerator {
        +generate(data) Buffer
    }

    %% Utils
    class AIShineError {
        +code: string
        +retryable: boolean
        +constructor(message, code, retryable)
    }

    class NetworkError {
        +constructor(message)
    }

    class TimeoutError {
        +constructor(message)
    }

    class DifyAPIError {
        +statusCode: number
        +constructor(message, statusCode)
    }

    %% Relationships
    SlackAdapter ..|> PlatformAdapter
    WorkflowOrchestrator --> DifyClient
    WorkflowOrchestrator --> CSVGenerator
    NetworkError --|> AIShineError
    TimeoutError --|> AIShineError
    DifyAPIError --|> AIShineError
```

---

## 5. データベースER図

```mermaid
erDiagram
    AI_EMPLOYEES ||--o{ EXECUTION_LOGS : has

    AI_EMPLOYEES {
        uuid id PK
        varchar name
        varchar bot_mention UK
        enum platform
        varchar channel_id
        varchar dify_workflow_id
        text dify_api_endpoint
        boolean is_active
        timestamp created_at
        timestamp updated_at
    }

    EXECUTION_LOGS {
        uuid id PK
        uuid ai_employee_id FK
        varchar user_id
        varchar user_name
        enum platform
        varchar channel_id
        text input_keyword
        enum status
        int result_count
        float processing_time_seconds
        text error_message
        timestamp created_at
    }
```

**Enums**:
- `Platform`: SLACK, LINE, TEAMS
- `ExecutionStatus`: SUCCESS, ERROR, TIMEOUT

---

## 6. 進捗状況図

```mermaid
graph LR
    subgraph "Phase 1: コアレイヤー ✅ 100%"
        T1[Task 1: 型定義]
        T2[Task 2: エラークラス]
        T3[Task 3: DifyClient]
        T4[Task 4: CSVGenerator]
        T5[Task 5: Orchestrator]
        T6[Task 6: PlatformAdapter]
        T7[Task 7: SlackAdapter]
    end

    subgraph "Phase 1: Database基盤 ✅ 100%"
        T8[Task 8: Schema]
        T9[Task 9: Migration]
        T10[Task 10: Seed]
    end

    subgraph "Phase 2: データアクセス 🔄 0%"
        T11[Task 11: Repository層]
        T12[Task 12: Service層]
    end

    subgraph "Phase 3: 統合 ⏳ 0%"
        T13[Task 13: 環境変数 ✅]
        T14[Task 14: index.ts]
        T15[Task 15: テスト]
    end

    T1 --> T11
    T8 --> T11
    T9 --> T11
    T11 --> T12
    T12 --> T14
    T13 --> T14
    T14 --> T15

    style T1 fill:#90EE90
    style T2 fill:#90EE90
    style T3 fill:#90EE90
    style T4 fill:#90EE90
    style T5 fill:#90EE90
    style T6 fill:#90EE90
    style T7 fill:#90EE90
    style T8 fill:#90EE90
    style T9 fill:#90EE90
    style T10 fill:#90EE90
    style T13 fill:#90EE90
    style T11 fill:#FFD700
    style T12 fill:#FFD700
    style T14 fill:#D3D3D3
    style T15 fill:#D3D3D3
```

**凡例**:
- 🟢 緑: 完了
- 🟡 黄: 進行中（別の人が担当）
- ⚪ 灰: 未着手

**進捗率**: 67% (10/15 タスク)

---

## 7. ディレクトリ構造図

```mermaid
graph TD
    Root[ai-shain/]

    Root --> Src[src/]
    Root --> Prisma[prisma/]
    Root --> Docs[docs/]
    Root --> Tasks[tasks/]

    Src --> Interfaces[interfaces/]
    Src --> Application[application/]
    Src --> Domain[domain/]
    Src --> Infrastructure[infrastructure/]
    Src --> Config[config/]
    Src --> Utils[utils/]

    Interfaces --> Slack[slack/]
    Interfaces --> PlatformAdapterTS["PlatformAdapter.ts ✅"]
    Slack --> SlackAdapterTS["SlackAdapter.ts ✅"]

    Application --> WorkflowOrchestratorTS["WorkflowOrchestrator.ts ✅"]

    Domain --> Entities[entities/]
    Domain --> Services[services/]
    Domain --> Types[types/]

    Entities --> AIEmployeeTS["AIEmployee.ts ✅"]
    Entities --> ExecutionLogTS["ExecutionLog.ts ✅"]

    Services --> AIEmployeeServiceTS["AIEmployeeService.ts ⏳"]
    Services --> LogServiceTS["LogService.ts ⏳"]

    Types --> IndexTS["index.ts ✅"]

    Infrastructure --> Database[database/]
    Infrastructure --> Dify[dify/]
    Infrastructure --> CSV[csv/]

    Database --> Repositories[repositories/]
    Database --> PrismaTS["prisma.ts ⏳"]
    Repositories --> AIEmployeeRepositoryTS["AIEmployeeRepository.ts ⏳"]
    Repositories --> LogRepositoryTS["LogRepository.ts ⏳"]

    Dify --> DifyClientTS["DifyClient.ts ✅"]
    Dify --> DifyTypesTS["DifyTypes.ts ✅"]

    CSV --> CSVGeneratorTS["CSVGenerator.ts ✅"]

    Config --> EnvTS["env.ts ✅"]
    Utils --> ErrorsTS["errors.ts ✅"]

    Prisma --> SchemaPrisma["schema.prisma ✅"]
    Prisma --> Migrations["migrations/ ✅"]
    Prisma --> SeedTS["seed.ts ✅"]

    style PlatformAdapterTS fill:#90EE90
    style SlackAdapterTS fill:#90EE90
    style WorkflowOrchestratorTS fill:#90EE90
    style AIEmployeeTS fill:#90EE90
    style ExecutionLogTS fill:#90EE90
    style IndexTS fill:#90EE90
    style DifyClientTS fill:#90EE90
    style DifyTypesTS fill:#90EE90
    style CSVGeneratorTS fill:#90EE90
    style EnvTS fill:#90EE90
    style ErrorsTS fill:#90EE90
    style SchemaPrisma fill:#90EE90
    style Migrations fill:#90EE90
    style SeedTS fill:#90EE90
    style AIEmployeeServiceTS fill:#FFD700
    style LogServiceTS fill:#FFD700
    style PrismaTS fill:#FFD700
    style AIEmployeeRepositoryTS fill:#FFD700
    style LogRepositoryTS fill:#FFD700
```

---

## 8. エラーハンドリングフロー図

```mermaid
flowchart TD
    Start[API呼び出し開始] --> Try{Try}
    Try -->|成功| Success[結果を返す]
    Try -->|失敗| CatchError[エラーキャッチ]

    CatchError --> CheckRetryable{retryable?}

    CheckRetryable -->|Yes| CheckAttempts{リトライ回数<br/>< maxRetries?}
    CheckRetryable -->|No| ThrowError[即座にthrow]

    CheckAttempts -->|Yes| Backoff[指数バックオフ<br/>2^attempt * 1000ms]
    CheckAttempts -->|No| ThrowError

    Backoff --> Wait[待機]
    Wait --> Try

    ThrowError --> LogError[エラーログ記録]
    LogError --> NotifyUser[ユーザーに通知]
    NotifyUser --> End[終了]

    Success --> LogSuccess[成功ログ記録]
    LogSuccess --> ReturnResult[結果返却]
    ReturnResult --> End

    style Success fill:#90EE90
    style ThrowError fill:#FFB6C1
    style Backoff fill:#FFD700
```

**エラー分類**:
- `NetworkError` (retryable: ✅)
- `TimeoutError` (retryable: ✅)
- `DifyAPIError` (500番台のみ retryable: ✅)
- `ValidationError` (retryable: ❌)

---

## 図の利用方法

### GitHub/GitLabで表示
このマークダウンファイルをGitHubにプッシュすると、Mermaid図が自動的にレンダリングされます。

### VS Codeで表示
拡張機能「Markdown Preview Mermaid Support」をインストールすると、プレビューで図が表示されます。

### draw.ioにインポート
1. [draw.io](https://app.diagrams.net/)を開く
2. "Arrange" > "Insert" > "Advanced" > "Mermaid"
3. Mermaidコードを貼り付け

### オンラインビューア
[Mermaid Live Editor](https://mermaid.live/)でリアルタイム編集・プレビュー可能

---

**作成日**: 2026-01-21
**バージョン**: 1.0
**作成者**: Claude Sonnet 4.5
