import axios, { AxiosInstance, AxiosError } from 'axios';
import { DifyWorkflowRequest, DifyErrorResponse, DifyWorkflowFinishedEvent } from './DifyTypes';
import { DifyAPIError, NetworkError, TimeoutError } from '../../utils/errors';
import { Logger, ConsoleLogger } from '../../utils/logger';
import { Readable } from 'stream';

/**
 * Dify APIクライアント
 *
 * Difyワークフローの実行を担当（ストリーミングモード対応）
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
      timeout: 600000, // 10分（ストリーミング中もタイムアウト設定は必要）
    });
  }

  /**
   * 営業リスト作成ワークフローを実行してCSVを取得（ストリーミングモード）
   *
   * @param query - 検索クエリ（例: "東京のIT企業 50件"）件数はDify側でパース
   * @param userId - ユーザーID（デフォルト: 'slack-user'）
   * @returns CSVデータ（Buffer）と件数
   * @throws DifyAPIError, NetworkError, TimeoutError
   */
  async executeWorkflow(
    query: string,
    userId: string = 'slack-user'
  ): Promise<{ csvBuffer: Buffer; rowCount: number; spreadsheetUrl?: string }> {
    this.logger.debug('Dify Workflow（ストリーミング）を呼び出し中', { query, userId });

    try {
      const requestBody: DifyWorkflowRequest = {
        inputs: {
          user_input: query,
        },
        response_mode: 'streaming', // ストリーミングモードに変更
        user: userId,
      };

      // ストリーミングレスポンスを取得
      const response = await this.client.post('/workflows/run', requestBody, {
        responseType: 'stream',
        headers: {
          'Accept': 'text/event-stream',
        },
      });

      // SSEストリームを解析して結果を取得
      const result = await this.parseSSEStream(response.data as Readable, query);

      return result;
    } catch (error) {
      this.handleError(error, query);
      throw error; // TypeScriptの型チェックのため
    }
  }

  /**
   * SSEストリームを解析してワークフロー結果を取得
   *
   * @param stream - Readable stream from axios
   * @param query - 検索クエリ（ログ用）
   * @returns CSVデータと件数
   */
  private async parseSSEStream(
    stream: Readable,
    query: string
  ): Promise<{ csvBuffer: Buffer; rowCount: number; spreadsheetUrl?: string }> {
    return new Promise((resolve, reject) => {
      let buffer = '';
      let workflowFinished = false;
      let lastEventData: DifyWorkflowFinishedEvent['data'] | null = null;

      stream.on('data', (chunk: Buffer) => {
        buffer += chunk.toString();

        // SSEイベントを行ごとに処理
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // 最後の不完全な行を保持

        let currentEvent = '';
        let currentData = '';

        for (const line of lines) {
          if (line.startsWith('event:')) {
            currentEvent = line.slice(6).trim();
          } else if (line.startsWith('data:')) {
            currentData = line.slice(5).trim();

            // イベントとデータが揃ったら処理
            if (currentEvent && currentData) {
              this.logger.debug(`SSEイベント受信: ${currentEvent}`);

              if (currentEvent === 'workflow_finished') {
                try {
                  const eventData = JSON.parse(currentData) as DifyWorkflowFinishedEvent['data'];
                  lastEventData = eventData;
                  workflowFinished = true;
                  this.logger.debug('workflow_finished イベントを受信', {
                    status: eventData.status,
                    elapsed_time: eventData.elapsed_time,
                  });
                } catch (parseError) {
                  this.logger.error('workflow_finished データのパースに失敗', parseError as Error);
                }
              } else if (currentEvent === 'error') {
                try {
                  const errorData = JSON.parse(currentData);
                  const errorMsg = errorData.message || 'ストリーミング中にエラーが発生しました';
                  reject(new DifyAPIError(errorMsg, 500));
                  return;
                } catch {
                  reject(new DifyAPIError('ストリーミング中に不明なエラーが発生しました', 500));
                  return;
                }
              }

              // 処理後にリセット
              currentEvent = '';
              currentData = '';
            }
          } else if (line === '' && currentData) {
            // 空行はイベントの区切り
            currentEvent = '';
            currentData = '';
          }
        }
      });

      stream.on('end', () => {
        if (!workflowFinished || !lastEventData) {
          reject(new DifyAPIError('ワークフローが完了しませんでした', 500));
          return;
        }

        const data = lastEventData;

        // ステータスチェック
        if (data.status === 'failed') {
          const errorMsg = data.error || 'ワークフロー実行に失敗しました';
          this.logger.error('Dify Workflowが失敗', new Error(errorMsg), {
            status: data.status,
            query,
          });
          reject(new DifyAPIError(errorMsg, 500));
          return;
        }

        if (data.status !== 'succeeded') {
          reject(new DifyAPIError(`Dify Workflow未完了: status=${data.status}`, 500));
          return;
        }

        // CSV出力を取得
        const csvText = data.outputs?.summary;
        if (!csvText) {
          reject(new DifyAPIError('Dify WorkflowからCSVが返されませんでした', 500));
          return;
        }

        // スプレッドシートURLを取得（オプション）
        const spreadsheetUrl = data.outputs?.spreadsheet_url;

        // CSVの行数をカウント（ヘッダー除く）
        const lines = csvText.trim().split('\n');
        const rowCount = Math.max(0, lines.length - 1);

        // CSVをBufferに変換
        const csvBuffer = Buffer.from(csvText, 'utf-8');

        this.logger.info('Dify Workflow（ストリーミング）実行完了', {
          workflowRunId: data.id,
          rowCount,
          elapsedTime: data.elapsed_time,
          spreadsheetUrl: spreadsheetUrl || '(なし)',
        });

        resolve({
          csvBuffer,
          rowCount,
          spreadsheetUrl,
        });
      });

      stream.on('error', (error: Error) => {
        this.logger.error('SSEストリームエラー', error, { query });
        reject(new NetworkError(`ストリーム読み取りエラー: ${error.message}`));
      });
    });
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
