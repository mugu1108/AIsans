import { google, sheets_v4, drive_v3 } from 'googleapis';
import { JWT } from 'google-auth-library';
import * as fs from 'fs/promises';
import { Logger, ConsoleLogger } from '../../utils/logger';
import { AIShineError } from '../../utils/errors';

/**
 * Googleスプレッドシート作成エラー
 */
export class GoogleSheetsError extends AIShineError {
  constructor(message: string, retryable: boolean = false) {
    super(message, 'GOOGLE_SHEETS_ERROR', retryable);
    this.name = 'GoogleSheetsError';
  }
}

/**
 * スプレッドシート作成結果
 */
export interface SpreadsheetResult {
  /**
   * スプレッドシートID
   */
  spreadsheetId: string;

  /**
   * スプレッドシートURL
   */
  spreadsheetUrl: string;

  /**
   * スプレッドシート名
   */
  title: string;
}

/**
 * Googleスプレッドシートクライアント
 *
 * Google Sheets API / Drive APIを使用してスプレッドシートを作成・管理
 */
export class GoogleSheetsClient {
  private logger: Logger;
  private auth: JWT | null = null;
  private sheetsApi: sheets_v4.Sheets | null = null;
  private driveApi: drive_v3.Drive | null = null;

  constructor(
    private serviceAccountKeyPath: string,
    private targetFolderId: string,
    logger?: Logger
  ) {
    this.logger = logger || new ConsoleLogger();
  }

  /**
   * 認証を初期化
   */
  private async initializeAuth(): Promise<void> {
    if (this.auth) {
      return; // 既に初期化済み
    }

    try {
      this.logger.debug('Google認証を初期化中', { keyPath: this.serviceAccountKeyPath });

      // サービスアカウントキーを読み込み
      const keyFileContent = await fs.readFile(this.serviceAccountKeyPath, 'utf-8');
      const keyFile = JSON.parse(keyFileContent);

      // JWTクライアントを作成
      this.auth = new google.auth.JWT({
        email: keyFile.client_email,
        key: keyFile.private_key,
        scopes: [
          'https://www.googleapis.com/auth/spreadsheets',
          'https://www.googleapis.com/auth/drive.file',
        ],
      });

      // APIクライアントを初期化
      this.sheetsApi = google.sheets({ version: 'v4', auth: this.auth });
      this.driveApi = google.drive({ version: 'v3', auth: this.auth });

      this.logger.info('Google認証を初期化完了');
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error));
      this.logger.error('Google認証の初期化エラー', err);
      throw new GoogleSheetsError(
        `Google認証の初期化に失敗しました: ${err.message}`,
        false
      );
    }
  }

  /**
   * CSVデータからスプレッドシートを作成
   *
   * @param csvBuffer - CSVデータのバッファ
   * @param title - スプレッドシートのタイトル
   * @returns スプレッドシート作成結果
   */
  async createSpreadsheetFromCSV(
    csvBuffer: Buffer,
    title: string
  ): Promise<SpreadsheetResult> {
    await this.initializeAuth();

    if (!this.sheetsApi || !this.driveApi) {
      throw new GoogleSheetsError('Google APIクライアントが初期化されていません', false);
    }

    try {
      this.logger.info('スプレッドシートを作成中', { title });

      // CSVをパース
      const csvText = csvBuffer.toString('utf-8').replace(/^\uFEFF/, ''); // BOM削除
      const rows = csvText.split('\n').map((line) => this.parseCSVLine(line));

      // 空の行を除外
      const validRows = rows.filter((row) => row.length > 0 && row.some((cell) => cell !== ''));

      if (validRows.length === 0) {
        throw new GoogleSheetsError('CSVデータが空です', false);
      }

      // スプレッドシートを作成
      const createResponse = await this.sheetsApi.spreadsheets.create({
        requestBody: {
          properties: {
            title,
          },
          sheets: [
            {
              properties: {
                title: 'Sheet1',
                gridProperties: {
                  rowCount: validRows.length,
                  columnCount: Math.max(...validRows.map((row) => row.length)),
                },
              },
            },
          ],
        },
      });

      const spreadsheetId = createResponse.data.spreadsheetId!;
      const spreadsheetUrl = createResponse.data.spreadsheetUrl!;

      this.logger.debug('スプレッドシートを作成完了', { spreadsheetId });

      // データを書き込み
      await this.sheetsApi.spreadsheets.values.update({
        spreadsheetId,
        range: 'Sheet1!A1',
        valueInputOption: 'RAW',
        requestBody: {
          values: validRows,
        },
      });

      this.logger.debug('データを書き込み完了', { rowCount: validRows.length });

      // 指定フォルダに移動
      await this.moveToFolder(spreadsheetId);

      this.logger.info('スプレッドシート作成完了', {
        spreadsheetId,
        spreadsheetUrl,
        title,
      });

      return {
        spreadsheetId,
        spreadsheetUrl,
        title,
      };
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error));
      this.logger.error('スプレッドシート作成エラー', err);

      if (error instanceof GoogleSheetsError) {
        throw error;
      }

      throw new GoogleSheetsError(
        `スプレッドシート作成に失敗しました: ${err.message}`,
        true
      );
    }
  }

  /**
   * スプレッドシートを指定フォルダに移動
   *
   * @param spreadsheetId - スプレッドシートID
   */
  private async moveToFolder(spreadsheetId: string): Promise<void> {
    if (!this.driveApi) {
      throw new GoogleSheetsError('Google Drive APIクライアントが初期化されていません', false);
    }

    try {
      this.logger.debug('スプレッドシートをフォルダに移動中', {
        spreadsheetId,
        folderId: this.targetFolderId,
      });

      // 現在の親フォルダを取得
      const file = await this.driveApi.files.get({
        fileId: spreadsheetId,
        fields: 'parents',
        supportsAllDrives: true,
      });

      const previousParents = file.data.parents?.join(',') || '';

      // 新しいフォルダに移動
      await this.driveApi.files.update({
        fileId: spreadsheetId,
        addParents: this.targetFolderId,
        removeParents: previousParents,
        fields: 'id, parents',
        supportsAllDrives: true,
      });

      this.logger.debug('スプレッドシートをフォルダに移動完了');
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error));
      this.logger.error('フォルダ移動エラー', err);
      throw new GoogleSheetsError(
        `フォルダへの移動に失敗しました: ${err.message}`,
        true
      );
    }
  }

  /**
   * CSV行をパース
   *
   * @param line - CSV行文字列
   * @returns パースされたセル配列
   */
  private parseCSVLine(line: string): string[] {
    const result: string[] = [];
    let current = '';
    let inQuotes = false;

    for (let i = 0; i < line.length; i++) {
      const char = line[i];
      const nextChar = line[i + 1];

      if (char === '"') {
        if (inQuotes && nextChar === '"') {
          // エスケープされたダブルクォート
          current += '"';
          i++; // 次の文字をスキップ
        } else {
          // クォートの開始/終了
          inQuotes = !inQuotes;
        }
      } else if (char === ',' && !inQuotes) {
        // カンマ区切り
        result.push(current);
        current = '';
      } else {
        current += char;
      }
    }

    // 最後のセルを追加
    result.push(current);

    return result;
  }
}
