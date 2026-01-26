/**
 * メッセージイベント
 */
export interface MessageEvent {
  /**
   * ユーザーID
   */
  userId: string;

  /**
   * ユーザー表示名
   */
  userName: string;

  /**
   * チャンネルID
   */
  channelId: string;

  /**
   * メッセージ本文
   */
  text: string;

  /**
   * メンション文字列（存在する場合）
   */
  mention?: string;

  /**
   * メッセージのタイムスタンプ
   */
  ts: string;

  /**
   * スレッドタイムスタンプ（スレッド内メッセージの場合）
   */
  threadTs?: string;
}

/**
 * プラットフォームアダプターインターフェース
 *
 * 各プラットフォーム（Slack、LINE、Teams等）の実装は
 * このインターフェースを実装する
 */
export interface PlatformAdapter {
  /**
   * メッセージを送信
   *
   * @param channelId - 送信先チャンネルID
   * @param text - メッセージ本文
   * @param threadTs - スレッドタイムスタンプ（任意）
   * @returns 送信したメッセージのタイムスタンプ
   */
  sendMessage(channelId: string, text: string, threadTs?: string): Promise<string>;

  /**
   * ファイルを送信
   *
   * @param channelId - 送信先チャンネルID
   * @param file - ファイルのバッファ
   * @param filename - ファイル名
   * @param comment - コメント（任意）
   */
  sendFile(
    channelId: string,
    file: Buffer,
    filename: string,
    comment?: string
  ): Promise<void>;

  /**
   * エラーメッセージを送信（リトライボタン付き）
   *
   * @param channelId - 送信先チャンネルID
   * @param errorMessage - エラーメッセージ
   * @param threadTs - スレッドタイムスタンプ（任意）
   */
  sendErrorWithRetry(
    channelId: string,
    errorMessage: string,
    threadTs?: string
  ): Promise<void>;

  /**
   * メンションイベントを購読
   *
   * @param handler - イベントハンドラ関数
   */
  onMention(handler: (event: MessageEvent) => Promise<void>): void;

  /**
   * プラットフォームアダプターを起動
   *
   * @param port - ポート番号（デフォルト: 3000）
   */
  start(port?: number): Promise<void>;
}
