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
 * 検索パラメータ（地域と業種）
 */
export interface SearchParams {
  region: string;
  industry: string;
}
