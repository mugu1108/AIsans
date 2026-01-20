import { App } from '@slack/bolt';
import { PlatformAdapter, MessageEvent } from '../PlatformAdapter';

/**
 * Slackアダプター
 *
 * PlatformAdapterインターフェースを実装
 */
export class SlackAdapter implements PlatformAdapter {
  private app: App;

  constructor(botToken: string, signingSecret: string, appToken?: string) {
    this.app = new App({
      token: botToken,
      signingSecret: signingSecret,
      socketMode: !!appToken,
      appToken: appToken,
    });
  }

  /**
   * アプリケーションを起動
   *
   * @param port - ポート番号（デフォルト: 3000）
   */
  async start(port: number = 3000): Promise<void> {
    await this.app.start(port);
    console.log(`⚡️ Slack app is running on port ${port}`);
  }

  /**
   * メッセージを送信
   *
   * @param channelId - 送信先チャンネルID
   * @param text - メッセージ本文
   * @param threadTs - スレッドタイムスタンプ（任意）
   */
  async sendMessage(channelId: string, text: string, threadTs?: string): Promise<void> {
    await this.app.client.chat.postMessage({
      channel: channelId,
      text,
      thread_ts: threadTs,
    });
  }

  /**
   * ファイルを送信
   *
   * @param channelId - 送信先チャンネルID
   * @param file - ファイルのバッファ
   * @param filename - ファイル名
   * @param comment - コメント（任意）
   */
  async sendFile(
    channelId: string,
    file: Buffer,
    filename: string,
    comment?: string
  ): Promise<void> {
    await this.app.client.files.uploadV2({
      channel_id: channelId,
      file: file,
      filename: filename,
      initial_comment: comment,
    });
  }

  /**
   * エラーメッセージを送信（リトライボタン付き）
   *
   * @param channelId - 送信先チャンネルID
   * @param errorMessage - エラーメッセージ
   * @param threadTs - スレッドタイムスタンプ（任意）
   */
  async sendErrorWithRetry(
    channelId: string,
    errorMessage: string,
    threadTs?: string
  ): Promise<void> {
    await this.app.client.chat.postMessage({
      channel: channelId,
      thread_ts: threadTs,
      text: `❌ エラーが発生しました`,
      blocks: [
        {
          type: 'section',
          text: {
            type: 'mrkdwn',
            text: `*エラー詳細*\n${errorMessage}`,
          },
        },
        {
          type: 'actions',
          elements: [
            {
              type: 'button',
              text: { type: 'plain_text', text: 'リトライ' },
              action_id: 'retry_workflow',
              style: 'primary',
            },
            {
              type: 'button',
              text: { type: 'plain_text', text: 'キャンセル' },
              action_id: 'cancel_workflow',
            },
          ],
        },
      ],
    });
  }

  /**
   * メンションイベントを購読
   *
   * @param handler - イベントハンドラ関数
   */
  onMention(handler: (event: MessageEvent) => Promise<void>): void {
    this.app.event('app_mention', async ({ event, client }) => {
      try {
        // ユーザー情報を取得
        const userInfo = await client.users.info({
          user: event.user!,
        });

        const userName: string = userInfo.user?.real_name || userInfo.user?.name || 'Unknown';

        // メンションを抽出
        const mention = this.extractMention(event.text);

        const messageEvent: MessageEvent = {
          userId: event.user!,
          userName: userName,
          channelId: event.channel!,
          text: event.text || '',
          mention: mention,
          threadTs: event.thread_ts,
        };

        await handler(messageEvent);
      } catch (error) {
        console.error('メンションイベント処理エラー:', error);
        // エラーをユーザーに通知
        await this.sendMessage(
          event.channel,
          '申し訳ございません。処理中にエラーが発生しました。',
          event.thread_ts
        );
      }
    });
  }

  /**
   * メッセージからメンション文字列を抽出
   *
   * @param text - メッセージ本文
   * @returns メンション文字列（存在しない場合はundefined）
   */
  private extractMention(text: string): string | undefined {
    // Slackのメンションフォーマット: <@U123456> または @username
    const mentionMatch = text.match(/<@([A-Z0-9]+)>/);
    if (mentionMatch) {
      return mentionMatch[0];
    }

    // 通常のメンション形式
    const normalMentionMatch = text.match(/@([^\s]+)/);
    if (normalMentionMatch) {
      return normalMentionMatch[0];
    }

    return undefined;
  }
}
