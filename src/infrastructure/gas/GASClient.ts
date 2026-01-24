import axios, { AxiosInstance, AxiosError } from 'axios';
import { GASRequest, GASErrorResponse } from './GASTypes';
import { NetworkError, TimeoutError } from '../../utils/errors';
import { Logger, ConsoleLogger } from '../../utils/logger';

/**
 * Google Apps Script APIクライアント
 *
 * GAS WebアプリへのHTTPリクエストを担当
 */
export class GASClient {
  private client: AxiosInstance;
  private logger: Logger;
  private apiUrl: string;

  constructor(apiUrl: string, logger?: Logger) {
    this.apiUrl = apiUrl;
    this.logger = logger || new ConsoleLogger();
    this.client = axios.create({
      headers: {
        'Content-Type': 'application/json',
      },
      timeout: 300000, // 5分
      responseType: 'arraybuffer', // CSV（バイナリ）を受け取る
    });
  }

  /**
   * GAS Webアプリを呼び出してCSVを取得
   *
   * @param query - 検索クエリ（自然言語）
   * @returns CSVデータ（Buffer）
   * @throws NetworkError, TimeoutError
   */
  async fetchCSV(query: string): Promise<Buffer> {
    this.logger.debug('GAS Webアプリを呼び出し中', { query });

    try {
      const response = await this.client.post(
        this.apiUrl,
        { query } as GASRequest
      );

      this.logger.info('GAS Webアプリ呼び出し完了', {
        dataSize: response.data.length,
      });

      return Buffer.from(response.data);
    } catch (error) {
      this.handleError(error, query);
      throw error; // TypeScriptの型チェックのため
    }
  }

  /**
   * エラーハンドリング
   *
   * @param error - キャッチされたエラー
   * @param query - リクエストクエリ
   * @throws 適切なカスタムエラー
   */
  private handleError(error: unknown, query: string): never {
    // Axiosエラーの場合
    if (axios.isAxiosError(error)) {
      const axiosError = error as AxiosError<GASErrorResponse>;

      // タイムアウトエラー
      if (axiosError.code === 'ECONNABORTED' || axiosError.code === 'ETIMEDOUT') {
        const timeoutError = new TimeoutError('GAS APIのタイムアウトが発生しました');
        this.logger.error('GAS APIタイムアウト', timeoutError, {
          code: axiosError.code,
          query,
        });
        throw timeoutError;
      }

      // ネットワークエラー
      if (!axiosError.response) {
        const networkError = new NetworkError('GAS APIへの接続に失敗しました');
        this.logger.error('GAS API接続エラー', networkError, { query });
        throw networkError;
      }

      // HTTPエラー
      const statusCode = axiosError.response.status;
      const errorMessage = axiosError.message;
      const networkError = new NetworkError(
        `GAS APIエラー (${statusCode}): ${errorMessage}`
      );

      this.logger.error('GAS APIエラー', networkError, {
        statusCode,
        errorMessage,
        query,
      });
      throw networkError;
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
