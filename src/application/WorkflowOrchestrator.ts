import { GASClient } from '../infrastructure/gas/GASClient';
import { parseQuery } from '../infrastructure/gas/queryParser';
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
 * GAS Webアプリとの連携を調整
 */
export class WorkflowOrchestrator {
  private logger: Logger;

  constructor(
    private gasClient: GASClient,
    logger?: Logger
  ) {
    this.logger = logger || new ConsoleLogger();
  }

  /**
   * ワークフローを実行
   *
   * @param query - 検索クエリ（自然言語）
   * @param maxRetries - 最大リトライ回数（デフォルト: 3）
   * @param folderId - スプレッドシート保存先フォルダID（オプション）
   * @returns 実行結果
   */
  async executeWorkflow(
    query: string,
    maxRetries: number = 3,
    folderId?: string
  ): Promise<WorkflowExecutionResult> {
    const startTime = Date.now();

    this.logger.info('ワークフロー実行を開始', {
      query,
      maxRetries,
      folderId,
    });

    try {
      // クエリを地域と業種に分解
      const params = parseQuery(query);
      this.logger.debug('クエリをパース', { query, params });

      // folderIdが指定されている場合はCSV+スプレッドシートを同時作成
      if (folderId) {
        this.logger.debug('GAS Webアプリを呼び出し中（CSV+スプレッドシート）');
        const bothResult = await this.retryWithBackoff(
          () => this.gasClient.fetchBoth(params.region, params.industry, 30, folderId),
          maxRetries
        );

        this.logger.debug(`CSVデータを取得: ${bothResult.csvBuffer.length}バイト`);

        if (bothResult.csvBuffer.length === 0) {
          this.logger.warn('CSVデータが空でした', { query });
          return {
            success: false,
            errorMessage: '検索結果が0件でした',
            processingTimeSeconds: this.calculateProcessingTime(startTime),
          };
        }

        const result = {
          success: true,
          csvBuffer: bothResult.csvBuffer,
          resultCount: bothResult.rowCount,
          spreadsheetUrl: bothResult.spreadsheetUrl,
          processingTimeSeconds: this.calculateProcessingTime(startTime),
        };

        this.logger.info('ワークフロー実行完了（CSV+スプレッドシート）', {
          resultCount: result.resultCount,
          spreadsheetUrl: result.spreadsheetUrl,
          processingTimeSeconds: result.processingTimeSeconds,
        });

        return result;
      }

      // folderIdが指定されていない場合はCSVのみ
      this.logger.debug('GAS Webアプリを呼び出し中（CSVのみ）');
      const csvBuffer = await this.retryWithBackoff(
        () => this.gasClient.fetchCSV(params.region, params.industry, 30),
        maxRetries
      );

      this.logger.debug(`CSVデータを取得: ${csvBuffer.length}バイト`);

      if (csvBuffer.length === 0) {
        this.logger.warn('CSVデータが空でした', { query });
        return {
          success: false,
          errorMessage: '検索結果が0件でした',
          processingTimeSeconds: this.calculateProcessingTime(startTime),
        };
      }

      // CSVの行数をカウント（ヘッダー除く）
      const csvText = csvBuffer.toString('utf-8');
      const lines = csvText.trim().split('\n');
      const resultCount = Math.max(0, lines.length - 1); // ヘッダー行を除く

      const result = {
        success: true,
        csvBuffer,
        resultCount,
        processingTimeSeconds: this.calculateProcessingTime(startTime),
      };

      this.logger.info('ワークフロー実行完了', {
        resultCount: result.resultCount,
        processingTimeSeconds: result.processingTimeSeconds,
      });

      return result;
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
