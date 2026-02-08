import axios, { AxiosInstance, AxiosError } from 'axios';
import {
  PythonSearchRequest,
  PythonSearchJobResponse,
  PythonJobStatusResponse,
  PythonHealthResponse,
  PythonErrorResponse,
} from './PythonAPITypes';
import { NetworkError, TimeoutError } from '../../utils/errors';
import { Logger, ConsoleLogger } from '../../utils/logger';

/**
 * Python API クライアント
 *
 * Python検索APIとの通信を担当
 */
export class PythonAPIClient {
  private client: AxiosInstance;
  private logger: Logger;

  constructor(apiUrl: string, logger?: Logger) {
    this.logger = logger || new ConsoleLogger();
    this.client = axios.create({
      baseURL: apiUrl,
      headers: {
        'Content-Type': 'application/json',
      },
      timeout: 30000, // 30秒（ジョブ開始はすぐにレスポンスが返る）
    });
  }

  /**
   * ヘルスチェック
   *
   * @returns ヘルスチェックレスポンス
   */
  async healthCheck(): Promise<PythonHealthResponse> {
    try {
      const response = await this.client.get<PythonHealthResponse>('/health');
      return response.data;
    } catch (error) {
      this.handleError(error, 'healthCheck');
      throw error;
    }
  }

  /**
   * 非同期検索ジョブを開始
   *
   * @param searchKeyword - 検索キーワード
   * @param targetCount - 目標件数
   * @param gasWebhookUrl - GAS Webhook URL
   * @param slackChannelId - Slackチャンネル ID
   * @param slackThreadTs - Slackスレッド タイムスタンプ
   * @param queries - 検索クエリ（オプション、指定しなければ自動生成）
   * @returns ジョブ開始レスポンス
   */
  async startSearch(
    searchKeyword: string,
    targetCount: number,
    gasWebhookUrl: string,
    slackChannelId: string,
    slackThreadTs: string,
    queries?: string[]
  ): Promise<PythonSearchJobResponse> {
    this.logger.debug('Python API 検索ジョブを開始', {
      searchKeyword,
      targetCount,
      slackChannelId,
    });

    try {
      const request: PythonSearchRequest = {
        search_keyword: searchKeyword,
        target_count: targetCount,
        gas_webhook_url: gasWebhookUrl,
        slack_channel_id: slackChannelId,
        slack_thread_ts: slackThreadTs,
      };

      if (queries && queries.length > 0) {
        request.queries = queries;
      }

      const response = await this.client.post<PythonSearchJobResponse>(
        '/search',
        request
      );

      this.logger.info('Python API ジョブ開始成功', {
        jobId: response.data.job_id,
        message: response.data.message,
      });

      return response.data;
    } catch (error) {
      this.handleError(error, 'startSearch');
      throw error;
    }
  }

  /**
   * ジョブステータスを取得
   *
   * @param jobId - ジョブID
   * @returns ジョブステータスレスポンス
   */
  async getJobStatus(jobId: string): Promise<PythonJobStatusResponse> {
    try {
      const response = await this.client.get<PythonJobStatusResponse>(
        `/jobs/${jobId}`
      );
      return response.data;
    } catch (error) {
      this.handleError(error, 'getJobStatus');
      throw error;
    }
  }

  /**
   * ジョブの完了を待機
   *
   * @param jobId - ジョブID
   * @param pollIntervalMs - ポーリング間隔（ミリ秒）
   * @param timeoutMs - タイムアウト（ミリ秒）
   * @returns 最終ステータス
   */
  async waitForCompletion(
    jobId: string,
    pollIntervalMs: number = 5000,
    timeoutMs: number = 600000
  ): Promise<PythonJobStatusResponse> {
    const startTime = Date.now();

    while (Date.now() - startTime < timeoutMs) {
      const status = await this.getJobStatus(jobId);

      this.logger.debug('ジョブステータス確認', {
        jobId,
        status: status.status,
        progress: status.progress,
      });

      if (status.status === 'completed' || status.status === 'failed') {
        return status;
      }

      await this.sleep(pollIntervalMs);
    }

    throw new TimeoutError(`ジョブ ${jobId} がタイムアウトしました`);
  }

  /**
   * エラーハンドリング
   */
  private handleError(error: unknown, operation: string): never {
    if (axios.isAxiosError(error)) {
      const axiosError = error as AxiosError<PythonErrorResponse>;

      // タイムアウト
      if (axiosError.code === 'ECONNABORTED' || axiosError.code === 'ETIMEDOUT') {
        const timeoutError = new TimeoutError(
          `Python API タイムアウト: ${operation}`
        );
        this.logger.error('Python API タイムアウト', timeoutError, { operation });
        throw timeoutError;
      }

      // ネットワークエラー
      if (!axiosError.response) {
        const networkError = new NetworkError(
          `Python API 接続エラー: ${operation}`
        );
        this.logger.error('Python API 接続エラー', networkError, { operation });
        throw networkError;
      }

      // HTTPエラー
      const statusCode = axiosError.response.status;
      const errorMessage =
        axiosError.response.data?.detail || axiosError.message;
      const networkError = new NetworkError(
        `Python API エラー (${statusCode}): ${errorMessage}`
      );
      this.logger.error('Python API エラー', networkError, {
        operation,
        statusCode,
      });
      throw networkError;
    }

    // その他のエラー
    if (error instanceof Error) {
      const networkError = new NetworkError(error.message);
      this.logger.error('Python API 不明なエラー', networkError, { operation });
      throw networkError;
    }

    const unknownError = new NetworkError('不明なエラーが発生しました');
    this.logger.error('Python API 不明なエラー', unknownError, { operation });
    throw unknownError;
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}
