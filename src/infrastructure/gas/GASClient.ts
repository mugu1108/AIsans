import axios, { AxiosInstance, AxiosError } from 'axios';
import { GASRequest, GASErrorResponse, GASSpreadsheetResponse, GASBothResponse } from './GASTypes';
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
   * @param region - 検索地域
   * @param industry - 検索業種
   * @param count - 取得件数（デフォルト: 30）
   * @returns CSVデータ（Buffer）
   * @throws NetworkError, TimeoutError
   */
  async fetchCSV(region: string, industry: string, count: number = 30): Promise<Buffer> {
    this.logger.debug('GAS Webアプリを呼び出し中', { region, industry, count });

    try {
      const response = await this.client.post(
        this.apiUrl,
        { region, industry, count } as GASRequest
      );

      this.logger.info('GAS Webアプリ呼び出し完了', {
        dataSize: response.data.length,
      });

      return Buffer.from(response.data);
    } catch (error) {
      this.handleError(error, region, industry);
      throw error; // TypeScriptの型チェックのため
    }
  }

  /**
   * GAS Webアプリを呼び出してCSVとスプレッドシートを同時に作成
   *
   * @param region - 検索地域
   * @param industry - 検索業種
   * @param count - 取得件数（デフォルト: 30）
   * @param folderId - 保存先フォルダID（オプション）
   * @returns CSV（Buffer）とスプレッドシート情報
   * @throws NetworkError, TimeoutError
   */
  async fetchBoth(
    region: string,
    industry: string,
    count: number = 30,
    folderId?: string
  ): Promise<{ csvBuffer: Buffer; spreadsheetUrl?: string; rowCount: number }> {
    this.logger.debug('GAS Webアプリで CSV+スプレッドシート作成を呼び出し中', {
      region,
      industry,
      count,
      folderId,
    });

    try {
      const jsonClient = axios.create({
        headers: {
          'Content-Type': 'application/json',
        },
        timeout: 300000, // 5分
      });

      const requestData: GASRequest = {
        region,
        industry,
        count,
        outputFormat: 'both',
        folderId,
      };

      const response = await jsonClient.post<GASBothResponse>(
        this.apiUrl,
        requestData
      );

      if (response.data.status !== 'success' || !response.data.csvBase64) {
        throw new NetworkError(response.data.message || 'GAS APIエラー');
      }

      // Base64デコードしてBufferに変換
      const csvBuffer = Buffer.from(response.data.csvBase64, 'base64');

      this.logger.info('GAS Webアプリ CSV+スプレッドシート作成完了', {
        spreadsheetUrl: response.data.spreadsheetUrl,
        rowCount: response.data.rowCount,
      });

      return {
        csvBuffer,
        spreadsheetUrl: response.data.spreadsheetUrl,
        rowCount: response.data.rowCount || 0,
      };
    } catch (error) {
      this.handleError(error, region, industry);
      throw error;
    }
  }

  /**
   * GAS Webアプリを呼び出してスプレッドシートを作成
   *
   * @param region - 検索地域
   * @param industry - 検索業種
   * @param count - 取得件数（デフォルト: 30）
   * @param folderId - 保存先フォルダID（オプション）
   * @returns スプレッドシート作成結果
   * @throws NetworkError, TimeoutError
   */
  async createSpreadsheet(
    region: string,
    industry: string,
    count: number = 30,
    folderId?: string
  ): Promise<GASSpreadsheetResponse> {
    this.logger.debug('GAS Webアプリでスプレッドシート作成を呼び出し中', {
      region,
      industry,
      count,
      folderId,
    });

    try {
      // JSON応答を受け取るための一時的なクライアント
      const jsonClient = axios.create({
        headers: {
          'Content-Type': 'application/json',
        },
        timeout: 300000, // 5分
      });

      const requestData: GASRequest = {
        region,
        industry,
        count,
        outputFormat: 'spreadsheet',
        folderId,
      };

      const response = await jsonClient.post<GASSpreadsheetResponse>(
        this.apiUrl,
        requestData
      );

      this.logger.info('GAS Webアプリ スプレッドシート作成完了', {
        spreadsheetId: response.data.spreadsheetId,
        rowCount: response.data.rowCount,
      });

      return response.data;
    } catch (error) {
      this.handleError(error, region, industry);
      throw error;
    }
  }

  /**
   * エラーハンドリング
   *
   * @param error - キャッチされたエラー
   * @param region - 検索地域
   * @param industry - 検索業種
   * @throws 適切なカスタムエラー
   */
  private handleError(error: unknown, region: string, industry: string): never {
    // Axiosエラーの場合
    if (axios.isAxiosError(error)) {
      const axiosError = error as AxiosError<GASErrorResponse>;

      // タイムアウトエラー
      if (axiosError.code === 'ECONNABORTED' || axiosError.code === 'ETIMEDOUT') {
        const timeoutError = new TimeoutError('GAS APIのタイムアウトが発生しました');
        this.logger.error('GAS APIタイムアウト', timeoutError, {
          code: axiosError.code,
          region,
          industry,
        });
        throw timeoutError;
      }

      // ネットワークエラー
      if (!axiosError.response) {
        const networkError = new NetworkError('GAS APIへの接続に失敗しました');
        this.logger.error('GAS API接続エラー', networkError, { region, industry });
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
        region,
        industry,
      });
      throw networkError;
    }

    // その他のエラー
    if (error instanceof Error) {
      const networkError = new NetworkError(error.message);
      this.logger.error('不明なエラー', networkError, { region, industry });
      throw networkError;
    }

    const unknownError = new NetworkError('不明なエラーが発生しました');
    this.logger.error('不明なエラー', unknownError, { region, industry });
    throw unknownError;
  }
}
