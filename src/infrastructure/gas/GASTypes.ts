/**
 * GAS APIリクエスト
 */
export interface GASRequest {
  /**
   * 検索キーワード（自然言語）
   */
  query: string;
}

/**
 * GAS APIエラーレスポンス
 */
export interface GASErrorResponse {
  error?: string;
  message?: string;
}
