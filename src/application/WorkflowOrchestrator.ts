import { DifyClient } from '../infrastructure/dify/DifyClient';
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

  /**
   * スプレッドシートURL（成功時、スプレッドシート作成時のみ）
   */
  spreadsheetUrl?: string;
}

/**
 * ワークフローオーケストレーター
 *
 * Dify Workflowとの連携を調整
 */
export class WorkflowOrchestrator {
  private logger: Logger;

  constructor(
    private difyClient: DifyClient,
    logger?: Logger
  ) {
    this.logger = logger || new ConsoleLogger();
  }

  /**
   * ワークフローを実行
   *
   * @param query - 検索クエリ（例: "東京のIT企業 50件"）件数はDify側でパース
   * @param maxRetries - 最大リトライ回数（デフォルト: 3）
   * @param _folderId - スプレッドシート保存先フォルダID（現在未使用、Dify側で処理）
   * @returns 実行結果
   */
  async executeWorkflow(
    query: string,
    maxRetries: number = 3,
    _folderId?: string
  ): Promise<WorkflowExecutionResult> {
    const startTime = Date.now();

    this.logger.info('ワークフロー実行を開始', {
      query,
      maxRetries,
    });

    try {
      // Dify Workflowを呼び出し（件数はDifyのinput_parseノードでパース）
      this.logger.debug('Dify Workflowを呼び出し中');
      const result = await this.retryWithBackoff(
        () => this.difyClient.executeWorkflow(query),
        maxRetries
      );

      this.logger.debug(`CSVデータを取得: ${result.csvBuffer.length}バイト`);

      if (result.csvBuffer.length === 0 || result.rowCount === 0) {
        this.logger.warn('CSVデータが空でした', { query });
        return {
          success: false,
          errorMessage: '検索結果が0件でした',
          processingTimeSeconds: this.calculateProcessingTime(startTime),
        };
      }

      const workflowResult: WorkflowExecutionResult = {
        success: true,
        csvBuffer: result.csvBuffer,
        resultCount: result.rowCount,
        processingTimeSeconds: this.calculateProcessingTime(startTime),
        spreadsheetUrl: result.spreadsheetUrl,
      };

      this.logger.info('ワークフロー実行完了', {
        resultCount: workflowResult.resultCount,
        processingTimeSeconds: workflowResult.processingTimeSeconds,
      });

      return workflowResult;
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error));
      const errorMessage = err.message;

      this.logger.error('ワークフロー実行エラー', err, {
        query,
      });

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
