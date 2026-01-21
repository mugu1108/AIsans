import { PrismaClient } from '@prisma/client';
import { getEnvConfig } from '../../config/env';

/**
 * Prismaクライアントのシングルトンインスタンス
 *
 * 開発環境ではホットリロードによる複数インスタンス作成を防ぐため、
 * globalオブジェクトにキャッシュします。
 * 本番環境では通常のシングルトンとして動作します。
 */

// グローバル型定義
declare global {
  // eslint-disable-next-line no-var
  var prisma: PrismaClient | undefined;
}

/**
 * Prismaクライアントインスタンスの取得または作成
 */
const getPrismaClient = (): PrismaClient => {
  if (global.prisma) {
    return global.prisma;
  }

  const env = getEnvConfig();

  const client = new PrismaClient({
    log:
      env.NODE_ENV === 'development'
        ? ['query', 'info', 'warn', 'error']
        : ['error'],
  });

  // 開発環境ではグローバルにキャッシュ
  if (env.NODE_ENV !== 'production') {
    global.prisma = client;
  }

  return client;
};

/**
 * エクスポート用のPrismaクライアントインスタンス
 */
export const prisma = getPrismaClient();

/**
 * アプリケーション終了時のクリーンアップ
 */
export const disconnectPrisma = async (): Promise<void> => {
  await prisma.$disconnect();
};
