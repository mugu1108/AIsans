import { App } from '@slack/bolt';
import { PlatformAdapter, MessageEvent } from '../PlatformAdapter';
import { Logger, ConsoleLogger } from '../../utils/logger';

/**
 * Slackアダプター
 *
 * PlatformAdapterインターフェースを実装
 */
export class SlackAdapter implements PlatformAdapter {
  private app: App;
  private logger: Logger;
  private processedEvents: Set<string> = new Set(); // イベント重複防止用

  constructor(
    botToken: string,
    signingSecret: string,
    appToken?: string,
    logger?: Logger
  ) {
    this.logger = logger || new ConsoleLogger();
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
    this.logger.info(`⚡️ Slack app is running on port ${port}`);
  }

  /**
   * メッセージを送信
   *
   * @param channelId - 送信先チャンネルID
   * @param text - メッセージ本文
   * @param threadTs - スレッドタイムスタンプ（任意）
   * @returns 送信したメッセージのタイムスタンプ
   */
  async sendMessage(channelId: string, text: string, threadTs?: string): Promise<string> {
    this.logger.debug('メッセージを送信中', { channelId, threadTs });
    const result = await this.app.client.chat.postMessage({
      channel: channelId,
      text,
      thread_ts: threadTs,
    });
    this.logger.debug('メッセージを送信完了', { channelId, ts: result.ts });
    return result.ts!;
  }

  /**
   * ファイルを送信
   *
   * @param channelId - 送信先チャンネルID
   * @param file - ファイルのバッファ
   * @param filename - ファイル名
   * @param comment - コメント（任意）
   * @param threadTs - スレッドタイムスタンプ（任意）
   */
  async sendFile(
    channelId: string,
    file: Buffer,
    filename: string,
    comment?: string,
    threadTs?: string
  ): Promise<void> {
    this.logger.debug('ファイルを送信中', { channelId, filename, threadTs });

    // アップロードパラメータ
    const uploadParams: {
      channel_id: string;
      file: Buffer;
      filename: string;
      thread_ts?: string;
      initial_comment?: string;
    } = {
      channel_id: channelId,
      file: file,
      filename: filename,
      thread_ts: threadTs,
    };

    // commentがある場合のみinitial_commentを追加
    if (comment) {
      uploadParams.initial_comment = comment;
    }

    await this.app.client.files.uploadV2(uploadParams);
    this.logger.info('ファイルを送信完了', { channelId, filename });
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
    this.logger.warn('エラーメッセージを送信中', { channelId, errorMessage });
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
    console.log('📝 onMention ハンドラーを登録しました');
    this.app.event('app_mention', async ({ event, client }) => {
      try {
        // イベント重複チェック
        const eventId = `${event.channel}-${event.ts}`;
        if (this.processedEvents.has(eventId)) {
          console.log('⚠️ 重複イベントをスキップ:', eventId);
          return;
        }
        this.processedEvents.add(eventId);
        // 古いイベントIDを定期的にクリア（メモリリーク防止）
        if (this.processedEvents.size > 1000) {
          const entries = Array.from(this.processedEvents);
          entries.slice(0, 500).forEach(id => this.processedEvents.delete(id));
        }

        console.log('🔔 app_mention イベントを受信しました!');
        console.log('  channelId:', event.channel);
        console.log('  text:', event.text);
        this.logger.debug('メンションイベントを受信', {
          userId: event.user,
          channelId: event.channel,
        });

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
          ts: event.ts!,
          threadTs: event.thread_ts,
        };

        this.logger.info('メンションイベントを処理中', {
          userId: messageEvent.userId,
          userName: messageEvent.userName,
          mention,
        });

        await handler(messageEvent);

        this.logger.debug('メンションイベント処理完了', {
          userId: messageEvent.userId,
        });
      } catch (error) {
        const err = error instanceof Error ? error : new Error(String(error));
        this.logger.error('メンションイベント処理エラー', err);
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
