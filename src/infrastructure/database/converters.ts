import {
  Platform as PrismaPlatform,
  ExecutionStatus as PrismaExecutionStatus,
} from '@prisma/client';
import { Platform, ExecutionStatus } from '../../domain/types';

/**
 * Prisma型とDomain型の変換ユーティリティ
 */

/**
 * Prisma Platform enumをDomain Platform typeに変換
 *
 * @param platform - Prisma Platform enum
 * @returns Domain Platform type
 */
export function toDomainPlatform(platform: PrismaPlatform): Platform {
  const platformMap: Record<PrismaPlatform, Platform> = {
    [PrismaPlatform.SLACK]: 'slack',
    [PrismaPlatform.LINE]: 'line',
    [PrismaPlatform.TEAMS]: 'teams',
  };

  return platformMap[platform];
}

/**
 * Domain Platform typeをPrisma Platform enumに変換
 *
 * @param platform - Domain Platform type
 * @returns Prisma Platform enum
 */
export function toPrismaPlatform(platform: Platform): PrismaPlatform {
  const platformMap: Record<Platform, PrismaPlatform> = {
    slack: PrismaPlatform.SLACK,
    line: PrismaPlatform.LINE,
    teams: PrismaPlatform.TEAMS,
  };

  return platformMap[platform];
}

/**
 * Prisma ExecutionStatus enumをDomain ExecutionStatus typeに変換
 *
 * @param status - Prisma ExecutionStatus enum
 * @returns Domain ExecutionStatus type
 */
export function toDomainExecutionStatus(
  status: PrismaExecutionStatus
): ExecutionStatus {
  const statusMap: Record<PrismaExecutionStatus, ExecutionStatus> = {
    [PrismaExecutionStatus.SUCCESS]: 'success',
    [PrismaExecutionStatus.ERROR]: 'error',
    [PrismaExecutionStatus.TIMEOUT]: 'timeout',
  };

  return statusMap[status];
}

/**
 * Domain ExecutionStatus typeをPrisma ExecutionStatus enumに変換
 *
 * @param status - Domain ExecutionStatus type
 * @returns Prisma ExecutionStatus enum
 */
export function toPrismaExecutionStatus(
  status: ExecutionStatus
): PrismaExecutionStatus {
  const statusMap: Record<ExecutionStatus, PrismaExecutionStatus> = {
    success: PrismaExecutionStatus.SUCCESS,
    error: PrismaExecutionStatus.ERROR,
    timeout: PrismaExecutionStatus.TIMEOUT,
  };

  return statusMap[status];
}
