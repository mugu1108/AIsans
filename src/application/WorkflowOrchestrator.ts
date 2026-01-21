import { DifyClient } from '../infrastructure/dify/DifyClient';
import { CSVGenerator } from '../infrastructure/csv/CSVGenerator';
import { CompanyData } from '../infrastructure/dify/DifyTypes';
import { AIShineError } from '../utils/errors';
import { Logger, ConsoleLogger } from '../utils/logger';

/**
 * ワークフロー実行結果
 */
export interface WorkflowExecutionResult {
  /**
   * 実行成功フラグ
   */
  success: boolean;

  /**
   * CSV生成結果（成功時）
   */
  csvBuffer?: Buffer;

  /**
   * 結果件数（成功時）
   */
  resultCount?: number;

  /**
   * 処理時間（秒）
   */
  processingTimeSeconds: number;

  /**
   * エラーメッセージ（失敗時）
   */
  errorMessage?: string;
}

/**
 * ワークフローオーケストレーター
 *
 * Difyワークフロー実行とCSV生成を調整
 */
export class WorkflowOrchestrator {
  private logger: Logger;

  constructor(
    private difyClient: DifyClient,
    private csvGenerator: CSVGenerator,
    logger?: Logger
  ) {
    this.logger = logger || new ConsoleLogger();
  }

  /**
   * ワークフローを実行
   *
   * @param endpoint - Dify APIエンドポイント
   * @param keyword - 検索キーワード
   * @param maxRetries - 最大リトライ回数（デフォルト: 3）
   * @returns 実行結果
   */
  async executeWorkflow(
    endpoint: string,
    keyword: string,
    maxRetries: number = 3
  ): Promise<WorkflowExecutionResult> {
    const startTime = Date.now();

    try {
      // リトライ付きでDifyワークフロー実行
      const response = await this.retryWithBackoff(
        () => this.difyClient.callWorkflow(endpoint, {
          inputs: { keyword },
          response_mode: 'blocking',
        }),
        maxRetries
      );

      // 企業データを取得
      const companies: CompanyData[] = response.data.outputs.companies || [];

      if (companies.length === 0) {
        return {
          success: false,
          errorMessage: '検索結果が0件でした',
          processingTimeSeconds: this.calculateProcessingTime(startTime),
        };
      }

      // CSVに変換
      const csvBuffer = this.csvGenerator.generate(companies);

      return {
        success: true,
        csvBuffer,
        resultCount: companies.length,
        processingTimeSeconds: this.calculateProcessingTime(startTime),
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : '不明なエラー';

      return {
        success: false,
        errorMessage,
        processingTimeSeconds: this.calculateProcessingTime(startTime),
      };
    }
  }

  /**
   * 指数バックオフ付きリトライ
   *
   * @param fn - 実行する関数
   * @param maxRetries - 最大リトライ回数
   * @returns 関数の実行結果
   * @throws 最後のエラー
   */
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
          this.logger.warn(`リトライ ${attempt + 1}/${maxRetries} - ${delay}ms後に再試行...`);
          await this.sleep(delay);
        }
      }
    }

    throw lastError;
  }

  /**
   * スリープ
   *
   * @param ms - スリープ時間（ミリ秒）
   */
  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  /**
   * 処理時間を計算
   *
   * @param startTime - 開始時刻（ミリ秒）
   * @returns 処理時間（秒）
   */
  private calculateProcessingTime(startTime: number): number {
    return Math.floor((Date.now() - startTime) / 1000);
  }
}
