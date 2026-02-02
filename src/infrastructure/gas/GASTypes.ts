/**
 * GAS APIリクエスト
 */
export interface GASRequest {
  /**
   * 地域（都道府県、市区町村など）
   */
  region: string;

  /**
   * 業種
   */
  industry: string;

  /**
   * 取得件数（デフォルト: 30）
   */
  count?: number;

  /**
   * 出力形式（csv, spreadsheet, both）
   */
  outputFormat?: 'csv' | 'spreadsheet' | 'both';

  /**
   * スプレッドシート保存先フォルダID
   */
  folderId?: string;
}

/**
 * GAS APIエラーレスポンス
 */
export interface GASErrorResponse {
  status?: string;
  error?: string;
  message?: string;
}

/**
 * スプレッドシート作成結果
 */
export interface GASSpreadsheetResponse {
  status: 'success' | 'error';
  spreadsheetId?: string;
  spreadsheetUrl?: string;
  title?: string;
  rowCount?: number;
  processingTime?: number;
  message?: string;
}

/**
 * CSV + スプレッドシート両方の結果
 */
export interface GASBothResponse {
  status: 'success' | 'error';
  csvBase64?: string;
  spreadsheetId?: string;
  spreadsheetUrl?: string;
  title?: string;
  rowCount?: number;
  processingTime?: number;
  message?: string;
}

/**
 * 検索パラメータ（地域と業種）
 */
export interface SearchParams {
  region: string;
  industry: string;
}
