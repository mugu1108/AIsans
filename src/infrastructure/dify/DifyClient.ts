import axios, { AxiosInstance, AxiosError } from 'axios';
import { DifyWorkflowRequest, DifyWorkflowResponse, DifyErrorResponse } from './DifyTypes';
import { DifyAPIError, NetworkError, TimeoutError } from '../../utils/errors';

/**
 * Dify APIクライアント
 *
 * Difyワークフローの実行を担当
 */
export class DifyClient {
  private client: AxiosInstance;

  constructor(apiKey: string) {
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
    try {
      const response = await this.client.post<DifyWorkflowResponse>(
        endpoint,
        request
      );

      // ステータスチェック
      if (response.data.data.status === 'failed') {
        throw new DifyAPIError(
          response.data.data.error || 'ワークフロー実行に失敗しました',
          response.status
        );
      }

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
        throw new TimeoutError('Dify APIのタイムアウトが発生しました');
      }

      // ネットワークエラー
      if (!axiosError.response) {
        throw new NetworkError('Dify APIへの接続に失敗しました');
      }

      // HTTPエラー
      const statusCode = axiosError.response.status;
      const errorMessage = axiosError.response.data?.message || axiosError.message;

      throw new DifyAPIError(
        `Dify APIエラー: ${errorMessage}`,
        statusCode
      );
    }

    // その他のエラー
    if (error instanceof Error) {
      throw new NetworkError(error.message);
    }

    throw new NetworkError('不明なエラーが発生しました');
  }
}
