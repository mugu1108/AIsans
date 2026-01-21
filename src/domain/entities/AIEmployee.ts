import { Platform, UpdatableEntity } from '../types';

/**
 * AI社員エンティティ
 *
 * 各プラットフォームで動作するAI社員の設定と情報を保持
 */
export interface AIEmployee extends UpdatableEntity {
  /**
   * AI社員の表示名（例: "営業AI"）
   */
  name: string;

  /**
   * メンション文字列（例: "@営業AI"）
   */
  botMention: string;

  /**
   * 動作するプラットフォーム
   */
  platform: Platform;

  /**
   * 対象チャンネルID
   */
  channelId: string;

  /**
   * DifyワークフローID
   */
  difyWorkflowId: string;

  /**
   * Dify APIエンドポイント
   */
  difyApiEndpoint: string;

  /**
   * 有効/無効フラグ
   */
  isActive: boolean;
}
