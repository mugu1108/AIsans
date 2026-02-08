/**
 * AI-Shine メインエントリーポイント
 *
 * 全レイヤーの統合とアプリケーション起動を担当
 */

import 'dotenv/config';
import { SlackAdapter } from './interfaces/slack/SlackAdapter';
import { AIEmployeeService } from './domain/services/AIEmployeeService';
import { LogService } from './domain/services/LogService';
import { AIEmployeeRepository } from './infrastructure/database/repositories/AIEmployeeRepository';
import { LogRepository } from './infrastructure/database/repositories/LogRepository';
import { DifyClient } from './infrastructure/dify/DifyClient';
import { PythonAPIClient } from './infrastructure/python/PythonAPIClient';
import { WorkflowOrchestrator } from './application/WorkflowOrchestrator';
import { getEnvConfig, logEnvironmentSummary } from './config/env';
import { disconnectPrisma } from './infrastructure/database/prisma';
import { ConsoleLogger } from './utils/logger';
import { AIEmployeeNotFoundError } from './utils/errors';

/**
 * アプリケーション起動
 */
async function main(): Promise<void> {
  console.log('🚀 AI-Shine starting...');
  const logger = new ConsoleLogger();

  try {
    // 環境変数の検証と読み込み
    console.log('Loading environment variables...');
    logger.info('環境変数を読み込んでいます...');
    const env = getEnvConfig();
    logEnvironmentSummary();

    // Repository層の初期化
    logger.info('Repository層を初期化しています...');
    const aiEmployeeRepo = new AIEmployeeRepository(logger);
    const logRepo = new LogRepository(logger);

    // Service層の初期化
    logger.info('Service層を初期化しています...');
    const aiEmployeeService = new AIEmployeeService(aiEmployeeRepo, logger);
    const logService = new LogService(logRepo, logger);

    // Infrastructure層の初期化
    logger.info('Infrastructure層を初期化しています...');
    const difyClient = new DifyClient(env.DIFY_API_URL, env.DIFY_API_KEY, logger);

    // Python API クライアントの初期化（設定されている場合）
    let pythonClient: PythonAPIClient | undefined;
    const usePythonAPI = !!env.PYTHON_API_URL && !!env.GAS_WEBHOOK_URL;

    if (usePythonAPI) {
      pythonClient = new PythonAPIClient(env.PYTHON_API_URL!, logger);
      logger.info('Python API モードを有効化しました', {
        apiUrl: env.PYTHON_API_URL,
        gasWebhookUrl: env.GAS_WEBHOOK_URL,
      });
    } else {
      logger.info('Dify モードで動作します（Python API未設定）');
    }

    // スプレッドシート機能のフォルダID（環境変数から取得）
    const spreadsheetFolderId = env.GOOGLE_DRIVE_FOLDER_ID;
    if (spreadsheetFolderId) {
      logger.info('スプレッドシート機能を有効化しました（GAS経由）', { folderId: spreadsheetFolderId });
    } else {
      logger.info('スプレッドシート機能は無効です（GOOGLE_DRIVE_FOLDER_ID未設定）');
    }

    // Application層の初期化
    logger.info('Application層を初期化しています...');
    const orchestrator = new WorkflowOrchestrator(difyClient, logger, pythonClient);

    // Interface層の初期化
    logger.info('Slackアダプターを初期化しています...');
    const slackAdapter = new SlackAdapter(
      env.SLACK_BOT_TOKEN,
      env.SLACK_SIGNING_SECRET,
      env.SLACK_APP_TOKEN,
      logger
    );

    // 件数上限（Python API: 300件、Dify: 50件）
    const MAX_COUNT = usePythonAPI ? 300 : 50;
    logger.info(`件数上限: ${MAX_COUNT}件`);

    // イベントハンドラの登録
    logger.info('イベントハンドラを登録しています...');
    slackAdapter.onMention(async (event) => {
      const startTime = Date.now();

      try {
        logger.info('メンションイベントを処理開始', {
          userId: event.userId,
          userName: event.userName,
          channelId: event.channelId,
          mention: event.mention,
        });

        // AI社員を検索
        const employee = await aiEmployeeService.findByMention(event.mention!);

        if (!employee) {
          logger.warn('AI社員が見つかりませんでした', { mention: event.mention });
          // エラー時は元のメッセージにスレッドで返信
          const errorThreadTs = event.threadTs || event.ts;
          await slackAdapter.sendMessage(
            event.channelId,
            `申し訳ございません。"${event.mention}" に対応するAI社員が見つかりませんでした。`,
            errorThreadTs
          );
          throw new AIEmployeeNotFoundError(event.mention!);
        }

        // 処理開始通知を送信し、そのメッセージのtsを取得（これがスレッドのルートになる）
        const startMessageTs = await slackAdapter.sendMessage(
          event.channelId,
          '了解しました！営業リスト作成を開始します...⏳'
        );

        // 以降のメッセージはこのスレッド内に投稿
        const threadTs = startMessageTs;

        // メンション部分を削除してクエリを抽出
        let query = event.text.replace(/<@[A-Z0-9]+>/g, '').trim();

        // 件数を抽出
        let targetCount = 30; // デフォルト30件
        const countMatch = query.match(/(\d+)\s*件/);
        if (countMatch) {
          const requestedCount = parseInt(countMatch[1], 10);
          if (requestedCount > MAX_COUNT) {
            logger.warn(`指定件数が上限を超えています: ${requestedCount}件 → ${MAX_COUNT}件に制限`, { query });
            query = query.replace(/\d+\s*件/, `${MAX_COUNT}件`);
            targetCount = MAX_COUNT;

            // ユーザーに上限適用を通知
            await slackAdapter.sendMessage(
              event.channelId,
              `※ 指定件数（${requestedCount}件）が上限を超えているため、${MAX_COUNT}件に制限して処理します。`,
              startMessageTs
            );
          } else {
            targetCount = requestedCount;
          }
        }

        logger.debug('クエリを抽出', { originalText: event.text, query, targetCount });

        // Python API モードの場合
        if (usePythonAPI && pythonClient) {
          logger.info('Python API モードで処理開始', { query, targetCount });

          // 検索キーワードを抽出（件数部分を除去）
          const searchKeyword = query.replace(/\d+\s*件/, '').trim();

          const result = await orchestrator.executeSearchJob({
            searchKeyword,
            targetCount,
            gasWebhookUrl: env.GAS_WEBHOOK_URL!,
            slackChannelId: event.channelId,
            slackThreadTs: threadTs,
          });

          if (result.success) {
            // ジョブ開始成功 - バックグラウンドで処理されるため、ここでは開始通知のみ
            logger.info('Python API ジョブ開始成功', { jobId: result.jobId });

            await slackAdapter.sendMessage(
              event.channelId,
              `🔍 検索ジョブを開始しました（ジョブID: ${result.jobId?.slice(0, 8)}...）\n処理完了後、このスレッドに結果を通知します。`,
              threadTs
            );

            // 成功ログの記録（ジョブ開始時点）
            await logService.recordExecution({
              aiEmployeeId: employee.id,
              userId: event.userId,
              userName: event.userName,
              platform: 'slack',
              channelId: event.channelId,
              inputKeyword: event.text,
              status: 'success',
              resultCount: 0, // バックグラウンド処理のため件数は後で更新
              processingTimeSeconds: result.processingTimeSeconds,
            });
          } else {
            // ジョブ開始失敗
            logger.error('Python API ジョブ開始失敗', new Error(result.errorMessage));

            await slackAdapter.sendErrorWithRetry(
              event.channelId,
              result.errorMessage!,
              threadTs
            );

            // エラーログの記録
            await logService.recordExecution({
              aiEmployeeId: employee.id,
              userId: event.userId,
              userName: event.userName,
              platform: 'slack',
              channelId: event.channelId,
              inputKeyword: event.text,
              status: 'error',
              processingTimeSeconds: result.processingTimeSeconds,
              errorMessage: result.errorMessage,
            });
          }
        } else {
          // Dify モード（従来の同期処理）
          logger.info('Dify モードで処理開始', { query });

          // ワークフロー実行（件数はDifyのinput_parseノードでパース）
          // タイムアウト系エラーはリトライしないため、リトライ回数は1に設定
          const result = await orchestrator.executeWorkflow(query, 1, spreadsheetFolderId);

          // 結果処理
          if (result.success) {
            // 成功時
            logger.info('ワークフロー実行成功', {
              resultCount: result.resultCount,
              processingTimeSeconds: result.processingTimeSeconds,
            });

            const timestamp = new Date().toISOString().replace(/[-:.]/g, '').slice(0, 15);
            const filename = `sales_list_${timestamp}.csv`;

            // 完了メッセージを投稿（スプレッドシートURLがある場合は一緒に表示）
            let completeMessage = `✅ 完了しました！${result.resultCount}社のリストを作成しました`;
            if (result.spreadsheetUrl) {
              completeMessage += `\n\n📊 Googleスプレッドシートも作成しました！\n${result.spreadsheetUrl}`;
            }
            await slackAdapter.sendMessage(
              event.channelId,
              completeMessage,
              threadTs
            );

            // その後にCSVファイルを送信
            await slackAdapter.sendFile(
              event.channelId,
              result.csvBuffer!,
              filename,
              undefined, // コメントなし
              threadTs
            );

            // 成功ログの記録
            await logService.recordExecution({
              aiEmployeeId: employee.id,
              userId: event.userId,
              userName: event.userName,
              platform: 'slack',
              channelId: event.channelId,
              inputKeyword: event.text,
              status: 'success',
              resultCount: result.resultCount,
              processingTimeSeconds: result.processingTimeSeconds,
            });
          } else {
            // 失敗時
            logger.error('ワークフロー実行失敗', new Error(result.errorMessage));

            await slackAdapter.sendErrorWithRetry(
              event.channelId,
              result.errorMessage!,
              threadTs
            );

            // エラーログの記録
            await logService.recordExecution({
              aiEmployeeId: employee.id,
              userId: event.userId,
              userName: event.userName,
              platform: 'slack',
              channelId: event.channelId,
              inputKeyword: event.text,
              status: 'error',
              processingTimeSeconds: result.processingTimeSeconds,
              errorMessage: result.errorMessage,
            });
          }
        }

        const totalTime = Math.floor((Date.now() - startTime) / 1000);
        logger.info('メンションイベント処理完了', {
          totalTimeSeconds: totalTime,
          mode: usePythonAPI ? 'python' : 'dify',
        });
      } catch (error) {
        // イベント処理中のエラー
        const err = error instanceof Error ? error : new Error(String(error));
        const totalTime = Math.floor((Date.now() - startTime) / 1000);

        logger.error('メンションイベント処理エラー', err, {
          userId: event.userId,
          channelId: event.channelId,
          totalTimeSeconds: totalTime,
        });

        // AIEmployeeNotFoundError以外のエラーの場合はユーザーに通知
        if (!(error instanceof AIEmployeeNotFoundError)) {
          // エラー時は元のメッセージにスレッドで返信
          const errorThreadTs = event.threadTs || event.ts;
          await slackAdapter.sendMessage(
            event.channelId,
            '申し訳ございません。処理中にエラーが発生しました。しばらく経ってから再度お試しください。',
            errorThreadTs
          );
        }
      }
    });

    // グレースフルシャットダウンの設定
    const shutdown = async (signal: string): Promise<void> => {
      logger.info(`${signal}シグナルを受信しました。シャットダウンを開始します...`);

      try {
        // Prisma接続を切断
        await disconnectPrisma();
        logger.info('Prisma接続を切断しました');

        logger.info('アプリケーションを正常終了しました');
        process.exit(0);
      } catch (error) {
        const err = error instanceof Error ? error : new Error(String(error));
        logger.error('シャットダウン中にエラーが発生しました', err);
        process.exit(1);
      }
    };

    process.on('SIGINT', () => shutdown('SIGINT'));
    process.on('SIGTERM', () => shutdown('SIGTERM'));

    // Slackアプリケーション起動
    logger.info('Slackアプリケーションを起動しています...');
    await slackAdapter.start(env.PORT);

    logger.info('========================================');
    logger.info(`🚀 AI-Shineが正常に起動しました！(${usePythonAPI ? 'Python API' : 'Dify'}モード)`);
    logger.info('========================================');
  } catch (error) {
    const err = error instanceof Error ? error : new Error(String(error));
    logger.error('アプリケーション起動エラー', err);
    process.exit(1);
  }
}

// アプリケーション起動
main().catch((error) => {
  console.error('予期しないエラーが発生しました:', error);
  process.exit(1);
});
