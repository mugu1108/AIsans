/**
 * Difyワークフローリクエスト
 */
export interface DifyWorkflowRequest {
  /**
   * 入力パラメータ
   */
  inputs: {
    /**
     * 検索キーワード（レガシーモード用、例: "東京のIT企業"）
     */
    user_input?: string;
    /**
     * 検索キーワード（ハイブリッドモード用、例: "東京 IT企業"）
     */
    search_keyword?: string;
    /**
     * 目標件数（任意、デフォルト: 30）
     */
    target_count?: number;
  };

  /**
   * レスポンスモード
   */
  response_mode: 'blocking' | 'streaming';

  /**
   * ユーザー識別子
   */
  user: string;
}

/**
 * Difyワークフローレスポンス
 */
export interface DifyWorkflowResponse {
  /**
   * ワークフロー実行ID
   */
  workflow_run_id: string;

  /**
   * タスクID
   */
  task_id: string;

  /**
   * 実行データ
   */
  data: {
    /**
     * データID
     */
    id: string;

    /**
     * ワークフローID
     */
    workflow_id: string;

    /**
     * 実行ステータス
     */
    status: 'running' | 'succeeded' | 'failed' | 'stopped';

    /**
     * 出力結果
     */
    outputs?: {
      /**
       * CSVデータ（文字列）- レガシーモード用
       */
      summary?: string;
      /**
       * 結果件数 - ハイブリッドモード用
       */
      result_count?: string;
      /**
       * スプレッドシートURL - ハイブリッドモード用
       */
      spreadsheet_url?: string;
      /**
       * メッセージ - ハイブリッドモード用
       */
      message?: string;
    };

    /**
     * エラーメッセージ（失敗時）
     */
    error?: string;

    /**
     * 実行時間（秒）
     */
    elapsed_time: number;

    /**
     * 使用トークン数
     */
    total_tokens: number;

    /**
     * 作成日時（Unixタイムスタンプ）
     */
    created_at: number;
  };
}

/**
 * 企業データ（CSV生成用）
 */
export interface CompanyData {
  /**
   * 企業名
   */
  companyName: string;

  /**
   * 企業URL
   */
  companyUrl: string;

  /**
   * お問い合わせURL
   */
  contactUrl: string;

  /**
   * その他の動的フィールド
   */
  [key: string]: string | number | boolean | undefined;
}

/**
 * Dify APIエラーレスポンス
 */
export interface DifyErrorResponse {
  /**
   * エラーコード
   */
  code: string;

  /**
   * エラーメッセージ
   */
  message: string;

  /**
   * HTTPステータスコード
   */
  status: number;
}
