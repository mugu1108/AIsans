import { SearchParams } from './GASTypes';

/**
 * 自然言語クエリを地域と業種に分解
 *
 * @param query - 自然言語の検索クエリ（例: "横浜市にある製造業"）
 * @returns 地域と業種のパラメータ
 */
export function parseQuery(query: string): SearchParams {
  // クエリをトリム
  const trimmed = query.trim();

  // パターン1: "地域にある業種", "地域の業種"
  const pattern1 = /^(.+?)(?:にある|の|に)(.+)$/;
  const match1 = trimmed.match(pattern1);

  if (match1) {
    const [, region, industry] = match1;
    return {
      region: region.trim(),
      industry: industry.trim(),
    };
  }

  // パターン2: "地域 業種" (スペース区切り)
  const pattern2 = /^(.+?)\s+(.+)$/;
  const match2 = trimmed.match(pattern2);

  if (match2) {
    const [, region, industry] = match2;
    return {
      region: region.trim(),
      industry: industry.trim(),
    };
  }

  // パース失敗時はそのまま返す（全体を業種として扱う）
  return {
    region: '',
    industry: trimmed,
  };
}
