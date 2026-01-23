import axios, { AxiosInstance, AxiosError } from 'axios';
import { DifyWorkflowRequest, DifyWorkflowResponse, DifyErrorResponse } from './DifyTypes';
import { DifyAPIError, NetworkError, TimeoutError } from '../../utils/errors';
import { Logger, ConsoleLogger } from '../../utils/logger';

/**
 * Dify APIクライアント
 *
 * Difyワークフローの実行を担当
 */
export class DifyClient {
  private client: AxiosInstance;
  private logger: Logger;

  constructor(apiKey: string, logger?: Logger) {
    this.logger = logger || new ConsoleLogger();
    this.client = axios.create({
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
      },
      timeout: 300000, // 5分
    });
  }

  /**
   * ワークフローを実行
   *
   * @param endpoint - Dify APIエンドポイント
   * @param request - リクエストパラメータ
   * @returns ワークフロー実行結果
   * @throws DifyAPIError, NetworkError, TimeoutError
   */
  async callWorkflow(
    endpoint: string,
    request: DifyWorkflowRequest
  ): Promise<DifyWorkflowResponse> {
    this.logger.debug('Difyワークフローを呼び出し中', { endpoint });

    try {
      const response = await this.client.post<DifyWorkflowResponse>(
        endpoint,
        request
      );

      // ステータスチェック
      if (response.data.data.status === 'failed') {
        const errorMsg = response.data.data.error || 'ワークフロー実行に失敗しました';
        this.logger.error('Difyワークフローが失敗', new Error(errorMsg), {
          endpoint,
          status: response.data.data.status,
        });
        throw new DifyAPIError(errorMsg, response.status);
      }

      this.logger.info('Difyワークフロー実行完了', {
        endpoint,
        status: response.data.data.status,
      });

      return response.data;
    } catch (error) {
      this.handleError(error);
      throw error; // TypeScriptの型チェックのため
    }
  }

  /**
   * エラーハンドリング
   *
   * @param error - キャッチされたエラー
   * @throws 適切なカスタムエラー
   */
  private handleError(error: unknown): never {
    // Axiosエラーの場合
    if (axios.isAxiosError(error)) {
      const axiosError = error as AxiosError<DifyErrorResponse>;

      // タイムアウトエラー
      if (axiosError.code === 'ECONNABORTED' || axiosError.code === 'ETIMEDOUT') {
        const timeoutError = new TimeoutError('Dify APIのタイムアウトが発生しました');
        this.logger.error('Dify APIタイムアウト', timeoutError, {
          code: axiosError.code,
        });
        throw timeoutError;
      }

      // ネットワークエラー
      if (!axiosError.response) {
        const networkError = new NetworkError('Dify APIへの接続に失敗しました');
        this.logger.error('Dify API接続エラー', networkError);
        throw networkError;
      }

      // HTTPエラー
      const statusCode = axiosError.response.status;
      const errorMessage = axiosError.response.data?.message || axiosError.message;
      const apiError = new DifyAPIError(`Dify APIエラー: ${errorMessage}`, statusCode);

      this.logger.error('Dify APIエラー', apiError, {
        statusCode,
        errorMessage,
      });
      throw apiError;
    }

    // その他のエラー
    if (error instanceof Error) {
      const networkError = new NetworkError(error.message);
      this.logger.error('不明なエラー', networkError);
      throw networkError;
    }

    const unknownError = new NetworkError('不明なエラーが発生しました');
    this.logger.error('不明なエラー', unknownError);
    throw unknownError;
  }
}
