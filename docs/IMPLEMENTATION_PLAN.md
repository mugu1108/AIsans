# AI-Shine 実装計画書

**バージョン**: 1.0
**作成日**: 2026-01-19
**プロジェクト**: AI-Shine（AI社員システム）

---

## 目次

1. [実装概要](#1-実装概要)
2. [Git Worktree戦略](#2-git-worktree戦略)
3. [Phase 1: 並列タスク分解](#3-phase-1-並列タスク分解)
4. [タスク詳細](#4-タスク詳細)
5. [統合手順](#5-統合手順)
6. [テスト戦略](#6-テスト戦略)
7. [デプロイ手順](#7-デプロイ手順)

---

## 1. 実装概要

### 1.1 実装戦略

AI-Shineの実装は**並列開発**を最大限活用し、開発速度を向上させます。

- **Git worktree** を使用して複数ブランチを同時に作業
- **4つの独立したタスク**を並行して実装
- **最終的に統合**して動作確認

### 1.2 前提条件

- Git 2.5以上（worktree機能サポート）
- Node.js 18.x以上
- pnpm または npm
- Supabaseアカウント
- Slackワークスペース
- Difyアカウント

---

## 2. Git Worktree戦略

### 2.1 ブランチ構成

```
main (本番)
  ↑
develop (開発統合)
  ↑
  ├─ feature/database-schema
  ├─ feature/core-domain
  ├─ feature/dify-integration
  └─ feature/slack-adapter
       ↓
  feature/integration (統合ブランチ)
       ↓
     develop
       ↓
      main
```

### 2.2 Worktree作成手順

#### ステップ1: メインリポジトリの確認

```bash
cd /Users/seiji/Desktop/dev/ai-shain
git branch -a
git checkout main  # または develop作成
git checkout -b develop
git push -u origin develop
```

#### ステップ2: Worktreeディレクトリ作成

```bash
# 親ディレクトリに戻る
cd /Users/seiji/Desktop/dev

# 各featureブランチ用のworktreeを作成
git -C ai-shain worktree add -b feature/database-schema ../ai-shain-database develop
git -C ai-shain worktree add -b feature/core-domain ../ai-shain-core develop
git -C ai-shain worktree add -b feature/dify-integration ../ai-shain-dify develop
git -C ai-shain worktree add -b feature/slack-adapter ../ai-shain-slack develop
```

#### ステップ3: Worktree確認

```bash
git -C ai-shain worktree list
```

**出力例**:
```
/Users/seiji/Desktop/dev/ai-shain            abc1234 [main]
/Users/seiji/Desktop/dev/ai-shain-database   def5678 [feature/database-schema]
/Users/seiji/Desktop/dev/ai-shain-core       ghi9012 [feature/core-domain]
/Users/seiji/Desktop/dev/ai-shain-dify       jkl3456 [feature/dify-integration]
/Users/seiji/Desktop/dev/ai-shain-slack      mno7890 [feature/slack-adapter]
```

### 2.3 Worktreeの削除（作業完了後）

```bash
cd /Users/seiji/Desktop/dev/ai-shain
git worktree remove ../ai-shain-database
git worktree remove ../ai-shain-core
git worktree remove ../ai-shain-dify
git worktree remove ../ai-shain-slack
```

---

## 3. Phase 1: 並列タスク分解

### 3.1 タスク一覧

| Task | ブランチ | Worktree | 担当Agent | 推定時間 | 依存関係 |
|---|---|---|---|---|---|
| **Task A** | feature/database-schema | ai-shain-database | Database Agent | - | なし |
| **Task B** | feature/core-domain | ai-shain-core | Backend Agent | - | Task A |
| **Task C** | feature/dify-integration | ai-shain-dify | Integration Agent | - | なし |
| **Task D** | feature/slack-adapter | ai-shain-slack | Slack Agent | - | なし |
| **Task E** | feature/integration | ai-shain-integration | Integration Agent | - | A+B+C+D |

### 3.2 並列実行タイミング

```
Time  →
  0     [Task A: Database] ────────────→ 完了
        [Task C: Dify] ─────────────────→ 完了
        [Task D: Slack] ────────────────→ 完了

  +1h   [Task B: Core Domain] ──────────→ 完了 (Task A完了後)

  +2h   [Task E: Integration] ──────────→ 完了 (全タスク完了後)
```

---

## 4. タスク詳細

### 4.1 Task A: データベース基盤（`feature/database-schema`）

**Worktree**: `ai-shain-database`
**優先度**: 最高（他タスクの依存元）

#### チェックリスト

- [ ] **Step 1**: Supabaseプロジェクト作成
  ```bash
  # Supabase CLI使用（または手動でWeb作成）
  npx supabase init
  ```

- [ ] **Step 2**: Prisma初期化
  ```bash
  cd /Users/seiji/Desktop/dev/ai-shain-database
  npm init -y
  npm install -D prisma typescript ts-node @types/node
  npx prisma init
  ```

- [ ] **Step 3**: `prisma/schema.prisma` 作成
  ```prisma
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

- [ ] **Step 4**: `.env` 設定
  ```env
  DATABASE_URL="postgresql://postgres:[password]@[host]:5432/postgres?pgbouncer=true"
  DIRECT_URL="postgresql://postgres:[password]@[host]:5432/postgres"
  ```

- [ ] **Step 5**: マイグレーション実行
  ```bash
  npx prisma migrate dev --name init
  npx prisma generate
  ```

- [ ] **Step 6**: Seedデータ作成（`prisma/seed.ts`）
  ```typescript
  import { PrismaClient } from '@prisma/client';

  const prisma = new PrismaClient();

  async function main() {
    // 営業AI作成
    await prisma.aIEmployee.create({
      data: {
        name: '営業AI',
        botMention: '@営業AI',
        platform: 'slack',
        channelId: 'C01234567', // 後で実際のIDに変更
        difyWorkflowId: 'workflow-sales-123',
        difyApiEndpoint: 'https://api.dify.ai/v1/workflows/run',
        isActive: true,
      },
    });
  }

  main()
    .then(async () => {
      await prisma.$disconnect();
    })
    .catch(async (e) => {
      console.error(e);
      await prisma.$disconnect();
      process.exit(1);
    });
  ```

- [ ] **Step 7**: Seed実行
  ```bash
  npx prisma db seed
  ```

- [ ] **Step 8**: コミット＆プッシュ
  ```bash
  git add .
  git commit -m "feat: setup database schema with Prisma

  - Add AIEmployee and ExecutionLog models
  - Add migration files
  - Add seed data for 営業AI

  Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

  git push -u origin feature/database-schema
  ```

---

### 4.2 Task B: コアドメイン層（`feature/core-domain`）

**Worktree**: `ai-shain-core`
**依存**: Task A完了後に開始

#### チェックリスト

- [ ] **Step 1**: TypeScriptプロジェクト初期化
  ```bash
  cd /Users/seiji/Desktop/dev/ai-shain-core
  npm init -y
  npm install -D typescript @types/node ts-node
  npx tsc --init
  ```

- [ ] **Step 2**: ディレクトリ構造作成
  ```bash
  mkdir -p src/{domain/{entities,services,types},infrastructure/database/repositories}
  ```

- [ ] **Step 3**: `src/domain/entities/AIEmployee.ts`
  ```typescript
  export interface AIEmployee {
    id: string;
    name: string;
    botMention: string;
    platform: 'slack' | 'line' | 'teams';
    channelId: string;
    difyWorkflowId: string;
    difyApiEndpoint: string;
    isActive: boolean;
    createdAt: Date;
    updatedAt: Date;
  }
  ```

- [ ] **Step 4**: `src/domain/entities/ExecutionLog.ts`
  ```typescript
  export interface ExecutionLog {
    id: string;
    aiEmployeeId: string;
    userId: string;
    userName: string;
    platform: 'slack' | 'line' | 'teams';
    channelId: string;
    inputKeyword: string;
    status: 'success' | 'error' | 'timeout';
    resultCount?: number;
    processingTimeSeconds?: number;
    errorMessage?: string;
    createdAt: Date;
  }
  ```

- [ ] **Step 5**: `src/infrastructure/database/prisma.ts`
  ```typescript
  import { PrismaClient } from '@prisma/client';

  export const prisma = new PrismaClient();
  ```

- [ ] **Step 6**: `src/infrastructure/database/repositories/AIEmployeeRepository.ts`
  ```typescript
  import { prisma } from '../prisma';
  import { AIEmployee } from '../../../domain/entities/AIEmployee';

  export class AIEmployeeRepository {
    async findByMention(mention: string): Promise<AIEmployee | null> {
      return await prisma.aIEmployee.findUnique({
        where: { botMention: mention },
      });
    }

    async findByChannelId(channelId: string): Promise<AIEmployee[]> {
      return await prisma.aIEmployee.findMany({
        where: { channelId, isActive: true },
      });
    }

    async getActiveEmployees(): Promise<AIEmployee[]> {
      return await prisma.aIEmployee.findMany({
        where: { isActive: true },
      });
    }
  }
  ```

- [ ] **Step 7**: `src/infrastructure/database/repositories/LogRepository.ts`
  ```typescript
  import { prisma } from '../prisma';
  import { ExecutionLog } from '../../../domain/entities/ExecutionLog';

  export class LogRepository {
    async create(log: Omit<ExecutionLog, 'id' | 'createdAt'>): Promise<ExecutionLog> {
      return await prisma.executionLog.create({
        data: log,
      });
    }

    async findByAIEmployee(aiEmployeeId: string, limit: number = 50): Promise<ExecutionLog[]> {
      return await prisma.executionLog.findMany({
        where: { aiEmployeeId },
        orderBy: { createdAt: 'desc' },
        take: limit,
      });
    }
  }
  ```

- [ ] **Step 8**: `src/domain/services/AIEmployeeService.ts`
  ```typescript
  import { AIEmployeeRepository } from '../../infrastructure/database/repositories/AIEmployeeRepository';
  import { AIEmployee } from '../entities/AIEmployee';

  export class AIEmployeeService {
    constructor(private repository: AIEmployeeRepository) {}

    async findByMention(mention: string): Promise<AIEmployee | null> {
      // @営業AI → 営業AI に変換
      const cleanMention = mention.replace('@', '');
      return await this.repository.findByMention(`@${cleanMention}`);
    }

    async getActiveEmployees(): Promise<AIEmployee[]> {
      return await this.repository.getActiveEmployees();
    }
  }
  ```

- [ ] **Step 9**: `src/domain/services/LogService.ts`
  ```typescript
  import { LogRepository } from '../../infrastructure/database/repositories/LogRepository';
  import { ExecutionLog } from '../entities/ExecutionLog';

  export class LogService {
    constructor(private repository: LogRepository) {}

    async recordExecution(log: Omit<ExecutionLog, 'id' | 'createdAt'>): Promise<void> {
      await this.repository.create(log);
    }

    async getExecutionHistory(aiEmployeeId: string): Promise<ExecutionLog[]> {
      return await this.repository.findByAIEmployee(aiEmployeeId);
    }
  }
  ```

- [ ] **Step 10**: コミット＆プッシュ
  ```bash
  git add .
  git commit -m "feat: implement core domain layer

  - Add AIEmployee and ExecutionLog entities
  - Add repository layer with Prisma
  - Add domain services

  Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

  git push -u origin feature/core-domain
  ```

---

### 4.3 Task C: Dify連携層（`feature/dify-integration`）

**Worktree**: `ai-shain-dify`
**依存**: なし（並列実行可能）

#### チェックリスト

- [ ] **Step 1**: プロジェクト初期化
  ```bash
  cd /Users/seiji/Desktop/dev/ai-shain-dify
  npm init -y
  npm install axios
  npm install -D typescript @types/node @types/axios
  ```

- [ ] **Step 2**: ディレクトリ作成
  ```bash
  mkdir -p src/{infrastructure/dify,infrastructure/csv,utils,application}
  ```

- [ ] **Step 3**: `src/infrastructure/dify/DifyTypes.ts`
  ```typescript
  export interface DifyWorkflowRequest {
    inputs: {
      keyword: string;
    };
  }

  export interface DifyWorkflowResponse {
    workflow_run_id: string;
    task_id: string;
    data: {
      id: string;
      workflow_id: string;
      status: string;
      outputs: any;
      error?: string;
      elapsed_time: number;
      total_tokens: number;
      created_at: number;
    };
  }
  ```

- [ ] **Step 4**: `src/infrastructure/dify/DifyClient.ts`
  ```typescript
  import axios, { AxiosInstance } from 'axios';
  import { DifyWorkflowRequest, DifyWorkflowResponse } from './DifyTypes';

  export class DifyClient {
    private client: AxiosInstance;

    constructor(private apiKey: string) {
      this.client = axios.create({
        headers: {
          'Authorization': `Bearer ${apiKey}`,
          'Content-Type': 'application/json',
        },
        timeout: 300000, // 5分
      });
    }

    async callWorkflow(
      endpoint: string,
      request: DifyWorkflowRequest
    ): Promise<DifyWorkflowResponse> {
      const response = await this.client.post<DifyWorkflowResponse>(
        endpoint,
        request
      );
      return response.data;
    }
  }
  ```

- [ ] **Step 5**: `src/infrastructure/csv/CSVGenerator.ts`
  ```typescript
  export interface CompanyData {
    companyName: string;
    companyUrl: string;
    contactUrl: string;
    [key: string]: any;
  }

  export class CSVGenerator {
    generate(data: CompanyData[]): Buffer {
      const headers = Object.keys(data[0] || {});
      const csv = [
        headers.join(','),
        ...data.map(row => headers.map(h => `"${row[h] || ''}"`).join(','))
      ].join('\n');

      // UTF-8 BOM付き
      return Buffer.concat([
        Buffer.from('\uFEFF', 'utf8'),
        Buffer.from(csv, 'utf8')
      ]);
    }
  }
  ```

- [ ] **Step 6**: `src/utils/errors.ts`
  ```typescript
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

  export class NetworkError extends AIShineError {
    constructor(message: string) {
      super(message, 'NETWORK_ERROR', true);
    }
  }

  export class TimeoutError extends AIShineError {
    constructor(message: string) {
      super(message, 'TIMEOUT_ERROR', true);
    }
  }

  export class DifyAPIError extends AIShineError {
    constructor(message: string, public statusCode: number) {
      super(message, 'DIFY_API_ERROR', statusCode >= 500);
    }
  }
  ```

- [ ] **Step 7**: `src/application/WorkflowOrchestrator.ts`
  ```typescript
  import { DifyClient } from '../infrastructure/dify/DifyClient';
  import { CSVGenerator, CompanyData } from '../infrastructure/csv/CSVGenerator';
  import { AIShineError, NetworkError, TimeoutError } from '../utils/errors';

  export interface WorkflowExecutionResult {
    success: boolean;
    csvBuffer?: Buffer;
    resultCount?: number;
    processingTimeSeconds: number;
    errorMessage?: string;
  }

  export class WorkflowOrchestrator {
    constructor(
      private difyClient: DifyClient,
      private csvGenerator: CSVGenerator
    ) {}

    async executeWorkflow(
      endpoint: string,
      keyword: string
    ): Promise<WorkflowExecutionResult> {
      const startTime = Date.now();

      try {
        const response = await this.retryWithBackoff(
          () => this.difyClient.callWorkflow(endpoint, { inputs: { keyword } }),
          3
        );

        const companies: CompanyData[] = response.data.outputs.companies || [];
        const csvBuffer = this.csvGenerator.generate(companies);

        return {
          success: true,
          csvBuffer,
          resultCount: companies.length,
          processingTimeSeconds: Math.floor((Date.now() - startTime) / 1000),
        };
      } catch (error) {
        return {
          success: false,
          errorMessage: error.message,
          processingTimeSeconds: Math.floor((Date.now() - startTime) / 1000),
        };
      }
    }

    private async retryWithBackoff<T>(
      fn: () => Promise<T>,
      maxRetries: number
    ): Promise<T> {
      let lastError: Error;

      for (let attempt = 0; attempt <= maxRetries; attempt++) {
        try {
          return await fn();
        } catch (error) {
          lastError = error;

          if (error instanceof AIShineError && !error.retryable) {
            throw error;
          }

          if (attempt < maxRetries) {
            const delay = Math.pow(2, attempt) * 1000;
            await new Promise(resolve => setTimeout(resolve, delay));
          }
        }
      }

      throw lastError;
    }
  }
  ```

- [ ] **Step 8**: コミット＆プッシュ
  ```bash
  git add .
  git commit -m "feat: implement Dify integration layer

  - Add DifyClient with retry logic
  - Add CSVGenerator
  - Add WorkflowOrchestrator
  - Add error handling

  Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

  git push -u origin feature/dify-integration
  ```

---

### 4.4 Task D: Slackアダプター層（`feature/slack-adapter`）

**Worktree**: `ai-shain-slack`
**依存**: なし（並列実行可能）

#### チェックリスト

- [ ] **Step 1**: プロジェクト初期化
  ```bash
  cd /Users/seiji/Desktop/dev/ai-shain-slack
  npm init -y
  npm install @slack/bolt
  npm install -D typescript @types/node
  ```

- [ ] **Step 2**: ディレクトリ作成
  ```bash
  mkdir -p src/interfaces/{slack,}
  ```

- [ ] **Step 3**: `src/interfaces/PlatformAdapter.ts`
  ```typescript
  export interface MessageEvent {
    userId: string;
    userName: string;
    channelId: string;
    text: string;
    mention?: string;
  }

  export interface PlatformAdapter {
    sendMessage(channelId: string, text: string): Promise<void>;
    sendFile(channelId: string, file: Buffer, filename: string, comment?: string): Promise<void>;
    sendErrorWithRetry(channelId: string, errorMessage: string, threadTs?: string): Promise<void>;
    onMention(handler: (event: MessageEvent) => Promise<void>): void;
  }
  ```

- [ ] **Step 4**: `src/interfaces/slack/SlackAdapter.ts`
  ```typescript
  import { App } from '@slack/bolt';
  import { PlatformAdapter, MessageEvent } from '../PlatformAdapter';

  export class SlackAdapter implements PlatformAdapter {
    private app: App;

    constructor(botToken: string, signingSecret: string) {
      this.app = new App({
        token: botToken,
        signingSecret: signingSecret,
        socketMode: false,
      });
    }

    async start(port: number = 3000): Promise<void> {
      await this.app.start(port);
      console.log(`⚡️ Slack app is running on port ${port}`);
    }

    async sendMessage(channelId: string, text: string): Promise<void> {
      await this.app.client.chat.postMessage({
        channel: channelId,
        text,
      });
    }

    async sendFile(
      channelId: string,
      file: Buffer,
      filename: string,
      comment?: string
    ): Promise<void> {
      await this.app.client.files.uploadV2({
        channel_id: channelId,
        file: file,
        filename: filename,
        initial_comment: comment,
      });
    }

    async sendErrorWithRetry(
      channelId: string,
      errorMessage: string,
      threadTs?: string
    ): Promise<void> {
      await this.app.client.chat.postMessage({
        channel: channelId,
        thread_ts: threadTs,
        text: `❌ エラーが発生しました`,
        blocks: [
          {
            type: 'section',
            text: {
              type: 'mrkdwn',
              text: `*エラー詳細*\n${errorMessage}`,
            },
          },
          {
            type: 'actions',
            elements: [
              {
                type: 'button',
                text: { type: 'plain_text', text: 'リトライ' },
                action_id: 'retry_workflow',
                style: 'primary',
              },
              {
                type: 'button',
                text: { type: 'plain_text', text: 'キャンセル' },
                action_id: 'cancel_workflow',
              },
            ],
          },
        ],
      });
    }

    onMention(handler: (event: MessageEvent) => Promise<void>): void {
      this.app.event('app_mention', async ({ event, say }) => {
        const messageEvent: MessageEvent = {
          userId: event.user,
          userName: '', // 後でuser.infoから取得
          channelId: event.channel,
          text: event.text,
          mention: this.extractMention(event.text),
        };

        await handler(messageEvent);
      });
    }

    private extractMention(text: string): string | undefined {
      const match = text.match(/@([^\s]+)/);
      return match ? match[1] : undefined;
    }
  }
  ```

- [ ] **Step 5**: コミット＆プッシュ
  ```bash
  git add .
  git commit -m "feat: implement Slack adapter layer

  - Add PlatformAdapter interface
  - Add SlackAdapter implementation
  - Add error message with retry blocks

  Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

  git push -u origin feature/slack-adapter
  ```

---

## 5. 統合手順

### 5.1 統合ブランチ作成

```bash
cd /Users/seiji/Desktop/dev/ai-shain
git checkout develop
git checkout -b feature/integration
```

### 5.2 各ブランチをマージ

```bash
# Task A: Database
git merge feature/database-schema

# Task B: Core Domain
git merge feature/core-domain

# Task C: Dify Integration
git merge feature/dify-integration

# Task D: Slack Adapter
git merge feature/slack-adapter
```

### 5.3 統合コード作成

#### `src/index.ts`（メインエントリーポイント）

```typescript
import { SlackAdapter } from './interfaces/slack/SlackAdapter';
import { AIEmployeeService } from './domain/services/AIEmployeeService';
import { LogService } from './domain/services/LogService';
import { AIEmployeeRepository } from './infrastructure/database/repositories/AIEmployeeRepository';
import { LogRepository } from './infrastructure/database/repositories/LogRepository';
import { DifyClient } from './infrastructure/dify/DifyClient';
import { CSVGenerator } from './infrastructure/csv/CSVGenerator';
import { WorkflowOrchestrator } from './application/WorkflowOrchestrator';

async function main() {
  // 環境変数
  const SLACK_BOT_TOKEN = process.env.SLACK_BOT_TOKEN!;
  const SLACK_SIGNING_SECRET = process.env.SLACK_SIGNING_SECRET!;
  const DIFY_API_KEY = process.env.DIFY_API_KEY!;
  const PORT = parseInt(process.env.PORT || '3000');

  // Repository
  const aiEmployeeRepo = new AIEmployeeRepository();
  const logRepo = new LogRepository();

  // Service
  const aiEmployeeService = new AIEmployeeService(aiEmployeeRepo);
  const logService = new LogService(logRepo);

  // Infrastructure
  const difyClient = new DifyClient(DIFY_API_KEY);
  const csvGenerator = new CSVGenerator();

  // Application
  const orchestrator = new WorkflowOrchestrator(difyClient, csvGenerator);

  // Interface
  const slackAdapter = new SlackAdapter(SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET);

  // イベントハンドラ
  slackAdapter.onMention(async (event) => {
    const employee = await aiEmployeeService.findByMention(event.mention!);

    if (!employee) {
      await slackAdapter.sendMessage(event.channelId, 'AI社員が見つかりません');
      return;
    }

    await slackAdapter.sendMessage(event.channelId, '了解しました！営業リスト作成を開始します...⏳');

    const result = await orchestrator.executeWorkflow(employee.difyApiEndpoint, event.text);

    if (result.success) {
      await slackAdapter.sendFile(
        event.channelId,
        result.csvBuffer!,
        `sales_list_${Date.now()}.csv`,
        `✅ 完了しました！${result.resultCount}社のリストを作成しました`
      );

      await logService.recordExecution({
        aiEmployeeId: employee.id,
        userId: event.userId,
        userName: event.userName,
        platform: 'slack',
        channelId: event.channelId,
        inputKeyword: event.text,
        status: 'success',
        resultCount: result.resultCount,
        processingTimeSeconds: result.processingTimeSeconds,
      });
    } else {
      await slackAdapter.sendErrorWithRetry(event.channelId, result.errorMessage!);

      await logService.recordExecution({
        aiEmployeeId: employee.id,
        userId: event.userId,
        userName: event.userName,
        platform: 'slack',
        channelId: event.channelId,
        inputKeyword: event.text,
        status: 'error',
        processingTimeSeconds: result.processingTimeSeconds,
        errorMessage: result.errorMessage,
      });
    }
  });

  await slackAdapter.start(PORT);
}

main().catch(console.error);
```

### 5.4 統合コミット

```bash
git add .
git commit -m "feat: integrate all layers

- Connect all components in main entry point
- Add full workflow from Slack to Dify to Database

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

git push -u origin feature/integration
```

---

## 6. テスト戦略

### 6.1 単体テスト

各worktreeで実装時にテストを作成

```bash
npm install -D jest @types/jest ts-jest
```

### 6.2 統合テスト

`feature/integration`ブランチでE2Eテスト

---

## 7. デプロイ手順

### 7.1 Railway設定

```bash
# Railway CLI
npm i -g @railway/cli
railway login
railway init
railway link
```

### 7.2 環境変数設定

Railwayダッシュボードで設定：
- `DATABASE_URL`
- `DIRECT_URL`
- `SLACK_BOT_TOKEN`
- `SLACK_SIGNING_SECRET`
- `DIFY_API_KEY`
- `PORT`
- `NODE_ENV=production`

### 7.3 デプロイ

```bash
git checkout develop
git merge feature/integration
git push origin develop

# Railwayが自動デプロイ
```

---

**承認**
- [ ] プロジェクトマネージャー
- [ ] 技術リード
- [ ] 各Agent担当者
