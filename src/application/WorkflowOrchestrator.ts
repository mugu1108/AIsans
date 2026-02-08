import { DifyClient } from '../infrastructure/dify/DifyClient';
import { PythonAPIClient } from '../infrastructure/python/PythonAPIClient';
import { AIShineError, TimeoutError, DifyAPIError } from '../utils/errors';
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
   * CSV生成結果（成功時、Difyモードのみ）
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

  /**
   * ジョブID（Python APIモードのみ）
   */
  jobId?: string;
}

/**
 * Python API用検索パラメータ
 */
export interface PythonSearchParams {
  searchKeyword: string;
  targetCount: number;
  gasWebhookUrl: string;
  slackChannelId: string;
  slackThreadTs: string;
  queries?: string[];
}

/**
 * ワークフローオーケストレーター
 *
 * Dify WorkflowまたはPython APIとの連携を調整
 */
export class WorkflowOrchestrator {
  private logger: Logger;
  private pythonClient?: PythonAPIClient;

  constructor(
    private difyClient: DifyClient,
    logger?: Logger,
    pythonClient?: PythonAPIClient
  ) {
    this.logger = logger || new ConsoleLogger();
    this.pythonClient = pythonClient;
  }

  /**
   * Python APIクライアントを設定
   */
  setPythonClient(pythonClient: PythonAPIClient): void {
    this.pythonClient = pythonClient;
  }

  /**
   * Python APIで非同期検索ジョブを開始
   *
   * バックグラウンドで処理され、完了時にSlackに通知される
   *
   * @param params - 検索パラメータ
   * @returns ジョブ開始結果（jobId含む）
   */
  async executeSearchJob(
    params: PythonSearchParams
  ): Promise<WorkflowExecutionResult> {
    const startTime = Date.now();

    if (!this.pythonClient) {
      return {
        success: false,
        errorMessage: 'Python APIクライアントが設定されていません',
        processingTimeSeconds: this.calculateProcessingTime(startTime),
      };
    }

    this.logger.info('Python API 検索ジョブを開始', {
      searchKeyword: params.searchKeyword,
      targetCount: params.targetCount,
    });

    try {
      const response = await this.pythonClient.startSearch(
        params.searchKeyword,
        params.targetCount,
        params.gasWebhookUrl,
        params.slackChannelId,
        params.slackThreadTs,
        params.queries
      );

      this.logger.info('Python API ジョブ開始成功', {
        jobId: response.job_id,
        message: response.message,
      });

      return {
        success: true,
        jobId: response.job_id,
        processingTimeSeconds: this.calculateProcessingTime(startTime),
      };
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error));

      this.logger.error('Python API ジョブ開始エラー', err, {
        searchKeyword: params.searchKeyword,
      });

      return {
        success: false,
        errorMessage: err.message,
        processingTimeSeconds: this.calculateProcessingTime(startTime),
      };
    }
  }

  /**
   * ワークフローを実行（Difyモード - レガシー）
   *
   * @param query - 検索クエリ（例: "東京のIT企業 50件"）件数はDify側でパース
   * @param maxRetries - 最大リトライ回数（デフォルト: 1、タイムアウト系はリトライしない）
   * @param _folderId - スプレッドシート保存先フォルダID（現在未使用、Dify側で処理）
   * @returns 実行結果
   */
  async executeWorkflow(
    query: string,
    maxRetries: number = 1,
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

        // タイムアウトエラー（504含む）はリトライしない（Dify側のタイムアウトは再試行しても失敗する可能性が高い）
        if (error instanceof TimeoutError) {
          this.logger.warn('タイムアウトエラーはリトライしません');
          throw error;
        }

        // 504 Gateway Timeoutもリトライしない
        if (error instanceof DifyAPIError && error.statusCode === 504) {
          this.logger.warn('504 Gateway Timeoutはリトライしません');
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
