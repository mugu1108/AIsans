/**
 * Python API 型定義
 */

/**
 * 検索リクエスト
 */
export interface PythonSearchRequest {
  search_keyword: string;
  target_count: number;
  queries?: string[];
  gas_webhook_url: string;
  slack_channel_id: string;
  slack_thread_ts: string;
}

/**
 * 検索ジョブ開始レスポンス
 */
export interface PythonSearchJobResponse {
  status: string;
  job_id: string;
  message: string;
}

/**
 * ジョブステータスレスポンス
 */
export interface PythonJobStatusResponse {
  id: string;
  status: string;
  progress: number;
  message: string;
  error?: string;
  result_count: number;
  spreadsheet_url?: string;
}

/**
 * ヘルスチェックレスポンス
 */
export interface PythonHealthResponse {
  status: string;
  message: string;
  env_status?: {
    SERPER_API_KEY: string;
    SLACK_BOT_TOKEN: string;
    GAS_WEBHOOK_URL: string;
  };
}

/**
 * エラーレスポンス
 */
export interface PythonErrorResponse {
  detail: string;
}

/**
 * 同期検索レスポンス（Dify用）
 */
export interface PythonSearchSyncResponse {
  status: string;
  search_keyword: string;
  target_count: number;
  result_count: number;
  search_count: number;
  scrape_count: number;
  success_count: number;
  spreadsheet_url: string;
  results: CompanyResult[];
  message: string;
}

/**
 * 企業結果
 */
export interface CompanyResult {
  company_name: string;
  base_url: string;
  contact_url: string;
  phone: string;
  domain: string;
}
