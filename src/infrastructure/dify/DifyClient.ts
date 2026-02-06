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

  constructor(apiUrl: string, apiKey: string, logger?: Logger) {
    this.logger = logger || new ConsoleLogger();
    this.client = axios.create({
      baseURL: apiUrl,
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
      },
      timeout: 600000, // 10分（Difyワークフローは時間がかかる可能性がある）
    });
  }

  /**
   * 営業リスト作成ワークフローを実行してCSVを取得
   *
   * @param query - 検索クエリ（自然言語、例: "東京のIT企業"）
   * @param targetCount - 取得件数（デフォルト: 30）
   * @param userId - ユーザーID（デフォルト: 'slack-user'）
   * @returns CSVデータ（Buffer）と件数
   * @throws DifyAPIError, NetworkError, TimeoutError
   */
  async executeWorkflow(
    query: string,
    targetCount: number = 30,
    userId: string = 'slack-user'
  ): Promise<{ csvBuffer: Buffer; rowCount: number; spreadsheetUrl?: string }> {
    this.logger.debug('Dify Workflowを呼び出し中', { query, targetCount, userId });

    try {
      const requestBody: DifyWorkflowRequest = {
        inputs: {
          user_input: query,
          target_count: targetCount,
        },
        response_mode: 'blocking',
        user: userId,
      };

      const response = await this.client.post<DifyWorkflowResponse>(
        '/workflows/run',
        requestBody
      );

      const { data } = response.data;

      // ステータスチェック
      if (data.status === 'failed') {
        const errorMsg = data.error || 'ワークフロー実行に失敗しました';
        this.logger.error('Dify Workflowが失敗', new Error(errorMsg), {
          status: data.status,
          query,
        });
        throw new DifyAPIError(errorMsg, 500);
      }

      if (data.status !== 'succeeded') {
        throw new DifyAPIError(`Dify Workflow未完了: status=${data.status}`, 500);
      }

      // CSV出力を取得
      const csvText = data.outputs?.summary;
      if (!csvText) {
        throw new DifyAPIError('Dify WorkflowからCSVが返されませんでした', 500);
      }

      // スプレッドシートURLを取得（オプション）
      const spreadsheetUrl = data.outputs?.spreadsheet_url;

      // CSVの行数をカウント（ヘッダー除く）
      const lines = csvText.trim().split('\n');
      const rowCount = Math.max(0, lines.length - 1);

      // CSVをBufferに変換
      const csvBuffer = Buffer.from(csvText, 'utf-8');

      this.logger.info('Dify Workflow実行完了', {
        workflowRunId: data.id,
        rowCount,
        elapsedTime: data.elapsed_time,
        spreadsheetUrl: spreadsheetUrl || '(なし)',
      });

      return {
        csvBuffer,
        rowCount,
        spreadsheetUrl,
      };
    } catch (error) {
      this.handleError(error, query);
      throw error; // TypeScriptの型チェックのため
    }
  }

  /**
   * エラーハンドリング
   *
   * @param error - キャッチされたエラー
   * @param query - 検索クエリ
   * @throws 適切なカスタムエラー
   */
  private handleError(error: unknown, query: string): never {
    // 既にカスタムエラーの場合はそのままthrow
    if (error instanceof DifyAPIError || error instanceof NetworkError || error instanceof TimeoutError) {
      throw error;
    }

    // Axiosエラーの場合
    if (axios.isAxiosError(error)) {
      const axiosError = error as AxiosError<DifyErrorResponse>;

      // タイムアウトエラー
      if (axiosError.code === 'ECONNABORTED' || axiosError.code === 'ETIMEDOUT') {
        const timeoutError = new TimeoutError('Dify APIのタイムアウトが発生しました');
        this.logger.error('Dify APIタイムアウト', timeoutError, {
          code: axiosError.code,
          query,
        });
        throw timeoutError;
      }

      // ネットワークエラー
      if (!axiosError.response) {
        const networkError = new NetworkError('Dify APIへの接続に失敗しました');
        this.logger.error('Dify API接続エラー', networkError, { query });
        throw networkError;
      }

      // HTTPエラー
      const statusCode = axiosError.response.status;
      const errorMessage = axiosError.response.data?.message || axiosError.message;
      const apiError = new DifyAPIError(`Dify APIエラー: ${errorMessage}`, statusCode);

      this.logger.error('Dify APIエラー', apiError, {
        statusCode,
        errorMessage,
        query,
      });
      throw apiError;
    }

    // その他のエラー
    if (error instanceof Error) {
      const networkError = new NetworkError(error.message);
      this.logger.error('不明なエラー', networkError, { query });
      throw networkError;
    }

    const unknownError = new NetworkError('不明なエラーが発生しました');
    this.logger.error('不明なエラー', unknownError, { query });
    throw unknownError;
  }
}
