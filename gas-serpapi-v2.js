// ====================================
// 定数・設定
// ====================================

const SERPAPI_KEY = PropertiesService.getScriptProperties().getProperty('SERPAPI_KEY');

// 求人サイト・ポータルサイトのみ除外（最小限に）
const EXCLUDE_DOMAINS = [
  'indeed.com', 'indeed.jp', 'mynavi.jp', 'rikunabi.com', 'doda.jp',
  'en-japan.com', 'baitoru.com', 'hatarako.net',
  'facebook.com', 'twitter.com', 'instagram.com',
  'youtube.com', 'tiktok.com', 'wikipedia.org', 'ja.wikipedia.org',
  'google.com', 'amazon.co.jp', 'rakuten.co.jp',
  'bizmap.jp', 'baseconnect.in', 'wantedly.com',
  '.lg.jp', '.go.jp'
];

// 求人ページ・一覧ページのパターンを除外
const EXCLUDE_URL_PATTERNS = [
  '/jobs/', '/job/', '/recruit/entry', '/recruiting/entry', '/career/entry',
  '/saiyou/', '/saiyo/',
  '/list', '/search', '/category', '/tag/', '/keyword/',
  '/matome', '/ranking', '/companies'
];

// 求人サイト・一覧ページ・まとめページのタイトルを除外
const EXCLUDE_TITLE_KEYWORDS = [
  '求人一覧', '求人情報', '転職サイト', '就職サイト', '企業一覧', '会社一覧',
  'ハローワーク', '求人検索',
  '上場企業', 'おすすめ', 'ランキング', 'まとめ',
  '〇選', '選！', '徹底解説', '完全ガイド'
];

// ====================================
// POST リクエスト
// ====================================

function doPost(e) {
  try {
    const requestData = JSON.parse(e.postData.contents);
    Logger.log('受信パラメータ: ' + JSON.stringify(requestData));

    const region = requestData.region || '';
    const industry = requestData.industry || '';
    const count = parseInt(requestData.count) || 30;

    if (!region || !industry) {
      return createJsonResponse({ status: 'error', message: 'region/industry必須' });
    }

    return generateCSVResponse(region, industry, count);

  } catch (error) {
    Logger.log('エラー発生: ' + error.toString());
    return createJsonResponse({ status: 'error', message: error.toString() });
  }
}

// ====================================
// CSV生成メイン処理（2段階方式）
// ====================================

function generateCSVResponse(region, industry, targetCount) {
  const startTime = new Date();
  Logger.log(`検索開始: ${region} ${industry} 目標${targetCount}件`);

  // 検索クエリ（企業サイトにヒットしやすいように最適化）
  const searchQueries = [
    `${region} ${industry} 株式会社`,
    `${region} ${industry} 有限会社`,
    `${region} ${industry} 会社概要`,
    `${region} ${industry} 企業情報`,
    `${industry} ${region} 株式会社`,
    `${industry} ${region} メーカー`,
    `${region} ${industry} 製造`,
    `${region} ${industry} site:co.jp`
  ];

  const seenDomains = new Set();
  const candidates = [];

  // ========================================
  // Phase 1: 高速フィルタリングで候補を収集
  // （サイトアクセスなし、URLとタイトルのみで判定）
  // ========================================
  Logger.log('=== Phase 1: 候補収集（サイトアクセスなし）===');

  const targetCandidates = targetCount * 4; // 目標の4倍まで候補を収集
  let totalSearched = 0;

  for (const query of searchQueries) {
    if (candidates.length >= targetCandidates) {
      Logger.log(`目標候補数${targetCandidates}件に到達。検索終了。`);
      break;
    }

    Logger.log(`検索クエリ: ${query}`);
    const results = performSerpAPISearch(query, 50); // 1クエリあたり最大50件取得
    totalSearched += results.length;

    let addedInQuery = 0;
    let rejectedStats = { domain: 0, site: 0, extract: 0, quality: 0 };

    for (const result of results) {
      if (candidates.length >= targetCandidates) break;

      const url = result.link;
      const title = result.title || '';

      // 1. ドメイン抽出
      const domain = extractDomain(url);
      if (!domain) {
        rejectedStats.domain++;
        continue;
      }

      if (seenDomains.has(domain)) continue;

      // 2. 企業サイトかチェック
      if (!isValidCompanySite(url, title)) {
        rejectedStats.site++;
        continue;
      }

      // 3. 企業名抽出
      const companyName = extractCompanyName(title);
      if (!companyName || companyName.length < 2) {
        rejectedStats.extract++;
        continue;
      }

      // 4. 企業名品質チェック
      if (!isValidCompanyName(companyName)) {
        rejectedStats.quality++;
        continue;
      }

      // 合格
      seenDomains.add(domain);
      candidates.push({
        company_name: companyName,
        base_url: url
      });
      addedInQuery++;

      if (candidates.length % 10 === 0) {
        Logger.log(`  進捗: ${candidates.length}/${targetCandidates}件`);
      }
    }

    Logger.log(`  除外内訳: サイト判定=${rejectedStats.site}件, 企業名抽出失敗=${rejectedStats.extract}件, 品質チェック=${rejectedStats.quality}件`);

    Logger.log(`  このクエリで追加: ${addedInQuery}件 (累計: ${candidates.length}件)`);
  }

  Logger.log(`Phase 1完了: ${candidates.length}件の候補を収集 (${totalSearched}件中)`);

  // ========================================
  // Phase 2: 上位30件のみ詳細確認
  // （サイトアクセスしてお問い合わせURL・電話取得）
  // ========================================
  Logger.log('=== Phase 2: 詳細確認（上位30件のみ）===');

  const finalCompanies = [];
  const top30Candidates = candidates.slice(0, targetCount);

  // バッチ処理でタイムアウト対策
  const batchSize = 5;
  for (let i = 0; i < top30Candidates.length; i += batchSize) {
    const batch = top30Candidates.slice(i, i + batchSize);
    const requests = batch.map(c => ({
      url: c.base_url,
      muteHttpExceptions: true,
      followRedirects: true,
      validateHttpsCertificates: false
    }));

    let responses;
    try {
      responses = UrlFetchApp.fetchAll(requests);
    } catch (e) {
      Logger.log(`バッチ取得エラー: ${e}`);
      // エラーでもURLは返す
      for (const candidate of batch) {
        finalCompanies.push({
          company_name: candidate.company_name,
          base_url: candidate.base_url,
          contact_url: guessContactUrl(candidate.base_url),
          phone: ''
        });
      }
      continue;
    }

    for (let j = 0; j < batch.length; j++) {
      const candidate = batch[j];
      const response = responses[j];

      let contactUrl = '';
      let phone = '';

      try {
        if (response.getResponseCode() === 200) {
          const html = response.getContentText();
          contactUrl = extractContactFromHtml(html, candidate.base_url);
          phone = extractPhoneFromHtml(html);
        }
      } catch (e) {
        Logger.log(`HTML解析エラー: ${e}`);
      }

      // お問い合わせURLが見つからなくても推測URLで返す
      if (!contactUrl) {
        contactUrl = guessContactUrl(candidate.base_url);
      }

      finalCompanies.push({
        company_name: candidate.company_name,
        base_url: candidate.base_url,
        contact_url: contactUrl,
        phone: phone
      });

      Logger.log(`✓ [${finalCompanies.length}/${targetCount}] ${candidate.company_name}`);
    }
  }

  Logger.log(`最終件数: ${finalCompanies.length}件`);

  const csv = generateCSV(finalCompanies);
  const elapsed = new Date() - startTime;
  Logger.log(`処理時間: ${elapsed}ms`);

  return ContentService
    .createTextOutput(csv)
    .setMimeType(ContentService.MimeType.CSV);
}

// ====================================
// 企業サイト判定（ログ付き）
// ====================================

function isValidCompanySite(url, title, enableLog = false) {
  if (!url) {
    if (enableLog) Logger.log(`    除外: URLなし`);
    return false;
  }

  const lower = url.toLowerCase();
  const titleLower = title.toLowerCase();

  // 1. 除外ドメインチェック
  for (const d of EXCLUDE_DOMAINS) {
    if (lower.includes(d)) {
      if (enableLog) Logger.log(`    除外: ドメイン除外 (${d}) - ${url}`);
      return false;
    }
  }

  // 2. 除外URLパターンチェック
  for (const p of EXCLUDE_URL_PATTERNS) {
    if (lower.includes(p)) {
      if (enableLog) Logger.log(`    除外: URLパターン除外 (${p}) - ${url}`);
      return false;
    }
  }

  // 3. タイトルに除外キーワードが含まれるかチェック
  for (const keyword of EXCLUDE_TITLE_KEYWORDS) {
    if (titleLower.includes(keyword)) {
      if (enableLog) Logger.log(`    除外: タイトルキーワード除外 (${keyword}) - ${title}`);
      return false;
    }
  }

  // 4. ドメイン判定（.co.jp を最優先）
  if (lower.includes('.co.jp')) {
    if (enableLog) Logger.log(`    ✓ 合格: .co.jpドメイン - ${url}`);
    return true;
  }

  // .or.jp（組織・団体）は許可
  if (lower.includes('.or.jp')) {
    // ただし政府系は除外済み（.go.jpは除外リストに含まれる）
    if (enableLog) Logger.log(`    ✓ 合格: .or.jpドメイン - ${url}`);
    return true;
  }

  // .jp, .com は慎重に許可（企業サイトっぽいか確認）
  if (lower.includes('.jp') || lower.includes('.com')) {
    // タイトルに企業っぽい要素があるか確認
    const hasCompanyKeywords =
      titleLower.includes('株式会社') ||
      titleLower.includes('有限会社') ||
      titleLower.includes('合同会社') ||
      titleLower.includes('（株）') ||
      titleLower.includes('(株)') ||
      titleLower.includes('会社概要') ||
      titleLower.includes('企業情報');

    if (hasCompanyKeywords) {
      if (enableLog) Logger.log(`    ✓ 合格: .jp/.comドメイン（企業要素あり） - ${url}`);
      return true;
    } else {
      if (enableLog) Logger.log(`    除外: .jp/.comドメインだが企業要素なし - ${title}`);
      return false;
    }
  }

  if (enableLog) Logger.log(`    除外: 対象外ドメイン - ${url}`);
  return false;
}

// ====================================
// SerpAPI検索（ページネーション対応）
// ====================================

function performSerpAPISearch(query, maxResults) {
  const allResults = [];
  const perPage = 10; // SerpAPIは通常10件ずつ返す
  const maxPages = Math.ceil(Math.min(maxResults, 50) / perPage); // 最大5ページまで

  for (let page = 0; page < maxPages; page++) {
    if (allResults.length >= maxResults) break;

    const start = page * perPage;
    const url = 'https://serpapi.com/search.json?' +
      `q=${encodeURIComponent(query)}` +
      `&api_key=${SERPAPI_KEY}` +
      `&num=${perPage}` +
      `&start=${start}` +
      `&gl=jp` +
      `&hl=ja`;

    try {
      const response = UrlFetchApp.fetch(url, { muteHttpExceptions: true });

      if (response.getResponseCode() === 200) {
        const data = JSON.parse(response.getContentText());

        if (data.organic_results && data.organic_results.length > 0) {
          for (const result of data.organic_results) {
            if (allResults.length >= maxResults) break;
            allResults.push({
              title: result.title || '',
              link: result.link || ''
            });
          }
          Logger.log(`  ページ${page + 1}: ${data.organic_results.length}件取得 (累計: ${allResults.length}件)`);
        } else {
          // 結果がなければ終了
          break;
        }
      } else {
        Logger.log(`SerpAPIエラー (ページ${page + 1}): HTTP ${response.getResponseCode()}`);
        break;
      }

      // API制限対策: 少し待機
      if (page < maxPages - 1) {
        Utilities.sleep(300);
      }

    } catch (e) {
      Logger.log(`SerpAPIエラー (ページ${page + 1}): ${e}`);
      break;
    }
  }

  return allResults;
}

// ====================================
// お問い合わせURL抽出
// ====================================

function extractContactFromHtml(html, baseUrl) {
  const keywords = ['contact', 'inquiry', 'お問い合わせ', 'お問合せ', 'toiawase', 'form'];
  const pattern = /<a\s+[^>]*href=["']([^"'#]+)["'][^>]*>([\s\S]*?)<\/a>/gi;
  let match;

  while ((match = pattern.exec(html)) !== null) {
    const href = match[1].toLowerCase();
    const text = (match[2] || '').replace(/<[^>]*>/g, '').toLowerCase();

    if (href.startsWith('mailto:')) continue;

    for (const kw of keywords) {
      if (href.includes(kw) || text.includes(kw)) {
        const fullUrl = resolveUrl(baseUrl, match[1]);
        if (isSameDomain(baseUrl, fullUrl)) return fullUrl;
      }
    }
  }
  return '';
}

// ====================================
// 電話番号抽出
// ====================================

function extractPhoneFromHtml(html) {
  const patterns = [
    /(?:TEL|Tel|tel|電話|☎|📞)[\s:：]*?(0\d{1,4}[-\s]?\d{1,4}[-\s]?\d{3,4})/,
    /href=["']tel:(0\d{1,4}[-\s]?\d{1,4}[-\s]?\d{3,4})["']/,
    /(0\d{1,4}[-−‐ー\s]?\d{1,4}[-−‐ー\s]?\d{3,4})/
  ];

  for (const pattern of patterns) {
    const match = html.match(pattern);
    if (match && match[1]) {
      let phone = match[1].replace(/[-−‐ー\s]/g, '-');
      if (phone.match(/^0\d{1,4}-\d{1,4}-\d{3,4}$/)) {
        return phone;
      }
    }
  }

  return '';
}

// ====================================
// お問い合わせURL推測
// ====================================

function guessContactUrl(baseUrl) {
  try {
    const match = baseUrl.match(/^(https?:\/\/[^\/]+)/);
    if (match) {
      return match[1] + '/contact';
    }
  } catch (e) {}
  return '';
}

// ====================================
// CSV生成
// ====================================

function generateCSV(companies) {
  let csv = '\uFEFF';
  csv += '企業名,企業URL,お問い合わせURL,電話番号\n';

  for (const c of companies) {
    csv += [
      escapeCSV(c.company_name),
      escapeCSV(c.base_url),
      escapeCSV(c.contact_url),
      escapeCSV(c.phone)
    ].join(',') + '\n';
  }

  return csv;
}

function escapeCSV(value) {
  if (!value) return '';
  const str = String(value);
  if (str.includes(',') || str.includes('\n') || str.includes('"')) {
    return '"' + str.replace(/"/g, '""') + '"';
  }
  return str;
}

// ====================================
// ユーティリティ
// ====================================

function extractDomain(url) {
  const match = url.match(/^https?:\/\/([^\/]+)/);
  return match ? match[1] : url;
}

function extractCompanyName(title) {
  if (!title) return '';

  let originalTitle = title;

  // セパレーターで分割（最初の部分が企業名の可能性が高い）
  for (const sep of ['｜', '|', ' - ', '－', '【', '】', '「', '」']) {
    if (title.includes(sep)) {
      title = title.split(sep)[0].trim();
      break;
    }
  }

  // 企業名パターンを優先的に抽出
  // パターン1: 「〜なら株式会社〇〇」のような広告文から企業名を抽出
  if (title.includes('なら') || title.includes('は') || title.includes('を')) {
    // 法人格を含む部分を優先的に抽出
    let match = title.match(/(株式会社|有限会社|合同会社|合資会社)[^\s　。、｜|【】「」]+/);
    if (match) return match[0].trim();

    match = title.match(/[^\s　。、｜|【】「」]+(株式会社|有限会社|合同会社|合資会社)/);
    if (match) return match[0].trim();

    match = title.match(/[^\s　。、｜|【】「」]+[（(]株[）)]/);
    if (match) return match[0].trim();
  }

  // パターン2: 「株式会社〇〇」「〇〇株式会社」（法人格あり）
  let match = title.match(/(株式会社|有限会社|合同会社|合資会社|一般社団法人|一般財団法人|社会福祉法人|医療法人|学校法人)[\s　]*[^\s　。、｜|【】「」]+/);
  if (match) return match[0].trim();

  match = title.match(/[^\s　。、｜|【】「」]+[\s　]*(株式会社|有限会社|合同会社|合資会社)/);
  if (match) return match[0].trim();

  // パターン3: 「〇〇（株）」「〇〇(株)」
  match = title.match(/[^\s　。、｜|【】「」]+[\s　]*[（(]株[）)]/);
  if (match) return match[0].trim();

  // パターン4: 企業名っぽい文字列（法人格なしの場合は慎重に）
  // まず一般的なタイトルでないことを確認
  const genericTitles = [
    '企業情報', '会社情報', '会社概要', '企業概要',
    'TOPページ', 'トップページ', 'ホーム', 'HOME',
    '事業所', '拠点', '営業所', '所在地',
    'について', 'ABOUT', '会社案内', 'COMPANY',
    '企業紹介', '会員', '紹介'
  ];

  let isGenericTitle = false;
  for (const generic of genericTitles) {
    if (title.includes(generic)) {
      isGenericTitle = true;
      break;
    }
  }

  if (!isGenericTitle) {
    match = title.match(/^[ぁ-んァ-ヶ一-龠々\w\s]+/);
    if (match) {
      let name = match[0].trim();
      // 不要な接尾辞を削除
      name = name.replace(/[\s　]*(ホームページ|公式サイト|オフィシャルサイト|HP|Website|サイト).*$/i, '');
      // 長さチェック（法人格なしの場合は最低5文字以上）
      if (name.length >= 5 && name.length <= 60) {
        return name;
      }
    }
  }

  // 法人格がある場合のみ、短い企業名も許可
  if (/株式会社|有限会社|合同会社|合資会社|（株）|\(株\)/.test(originalTitle)) {
    return title.substring(0, 50).trim();
  }

  // それ以外は空文字を返す（品質チェックで弾かれる）
  return '';
}

// ====================================
// 企業名品質チェック
// ====================================

function isValidCompanyName(companyName) {
  if (!companyName || companyName.length < 3) return false;

  // 短すぎる or 長すぎるものを除外
  if (companyName.length < 4 || companyName.length > 80) {
    return false;
  }

  // 一覧・まとめページの典型的なタイトルを除外（日本語は元の文字列でチェック）
  const invalidPatterns = [
    '一覧', 'いちらん', 'リスト', 'まとめ', 'ランキング',
    '上場企業', '中小企業', '大手企業',
    '業界', '産業', 'の企業', 'の会社', 'の法人',
    '県内', '市内', '区内', '地域', 'エリア',
    '検索', '情報サイト',
    'について', '徹底', '解説',
    '製造会社', '製造業者', 'メーカー一覧',
    'おすすめ', 'オススメ',
    '企業情報', '会社情報', '法人情報',
    '会社概要', '企業概要', '事業所', '拠点',
    'TOPページ', 'トップページ', 'ホーム',
    '所在地', '本社', '支社', '営業所',
    '会社案内', '企業案内', 'COMPANY',
    '会員', '紹介', 'メンバー',
    '業務用の', '産業用', '工業用',
    'なら', 'から選ぶ', 'を探す'
  ];

  for (const pattern of invalidPatterns) {
    if (companyName.includes(pattern)) {
      return false;
    }
  }

  // 英語のチェック
  const lower = companyName.toLowerCase();
  const invalidEnglishPatterns = ['search', 'list', 'ranking', 'about', 'home', 'top'];
  for (const pattern of invalidEnglishPatterns) {
    if (lower.includes(pattern)) {
      return false;
    }
  }

  // 地名パターン・業種説明文を除外
  const locationOnlyPatterns = [
    /^(東京|大阪|神奈川|横浜|川崎|名古屋|福岡|札幌|仙台).*(の|にある|に本社)/,
    /^[都道府県市区町村]+$/,
    /(都|道|府|県|市|区|町|村)の(企業|会社|法人|製造)/,
    /(都|道|府|県|市|区|町|村)に(ある|本社|所在)/,
    /^(国内|海外|全国).*(拠点|事業所|営業所)/,
    // 業種説明文・技術説明文を除外
    /^(精密|高精度|業務用|産業用|工業用).*(加工|製造|卸|販売)/,
    /^.*(加工|製造|卸|販売|サービス)(なら|は|を|の)/,
    /^(板金|切削|プレス|金型|成形|溶接).*(加工|製造)/,
    /^.*(食料品|食品|部品|機械|装置)(卸|販売|メーカー)$/
  ];

  for (const pattern of locationOnlyPatterns) {
    if (pattern.test(companyName)) {
      return false;
    }
  }

  // 不完全な企業名を除外（1-3文字のひらがな・カタカナのみ等）
  if (/^[ぁ-んァ-ヶー]{1,3}$/.test(companyName)) {
    return false;
  }

  // 数字だけ、記号だけを除外
  if (/^[\d\s　]+$/.test(companyName) || /^[!-\/:-@\[-`{-~\s　]+$/.test(companyName)) {
    return false;
  }

  // "会社案内"、"COMPANY 会社案内" などの完全一致を除外
  const exactInvalidNames = [
    '会社案内', '企業案内', '会社概要', '企業概要',
    'COMPANY', 'COMPANY 会社案内', 'ABOUT US',
    '企業情報', '会社情報'
  ];

  for (const invalidName of exactInvalidNames) {
    if (companyName === invalidName || companyName.includes(invalidName)) {
      return false;
    }
  }

  return true;
}

function resolveUrl(baseUrl, relativeUrl) {
  if (relativeUrl.startsWith('http')) return relativeUrl;
  const match = baseUrl.match(/^(https?:\/\/[^\/]+)/);
  if (!match) return relativeUrl;
  return relativeUrl.startsWith('/') ? match[1] + relativeUrl : match[1] + '/' + relativeUrl;
}

function isSameDomain(url1, url2) {
  return extractDomain(url1) === extractDomain(url2);
}

function createJsonResponse(data) {
  return ContentService.createTextOutput(JSON.stringify(data)).setMimeType(ContentService.MimeType.JSON);
}

// ====================================
// テスト
// ====================================

function testFunction() {
  Logger.log('=== SerpAPI確認 ===');
  Logger.log('SERPAPI_KEY: ' + (SERPAPI_KEY ? '設定あり' : '未設定'));

  Logger.log('\n=== 検索テスト（詳細ログ有効） ===');
  const results = performSerpAPISearch('横浜市 製造業 株式会社', 20);
  Logger.log(`検索結果: ${results.length}件`);

  Logger.log('\n--- フィルタリング詳細 ---');
  let validCount = 0;
  for (let i = 0; i < Math.min(results.length, 15); i++) {
    const r = results[i];
    Logger.log(`\n${i+1}. タイトル: ${r.title}`);
    Logger.log(`   URL: ${r.link}`);

    // Step 1: サイト判定
    const isSiteValid = isValidCompanySite(r.link, r.title, true);
    if (!isSiteValid) {
      continue;
    }

    // Step 2: 企業名抽出
    const companyName = extractCompanyName(r.title);
    Logger.log(`   企業名抽出: "${companyName}"`);

    // Step 3: 企業名品質チェック
    const isNameValid = isValidCompanyName(companyName);
    Logger.log(`   品質チェック: ${isNameValid ? '✓ 合格' : '✗ 不合格'}`);

    if (isNameValid) {
      validCount++;
      Logger.log(`   → 最終結果: ✓ 採用`);
    } else {
      Logger.log(`   → 最終結果: ✗ 除外`);
    }
  }

  Logger.log(`\n=== 結果サマリー ===`);
  Logger.log(`検索結果: ${results.length}件`);
  Logger.log(`最終合格: ${validCount}件`);
}

// ====================================
// 簡易テスト（実際の処理を実行）
// ====================================

function testActualSearch() {
  const testData = {
    postData: {
      contents: JSON.stringify({
        region: '横浜市',
        industry: '製造業',
        count: 10
      })
    }
  };

  Logger.log('=== 実際の検索処理テスト ===');
  const result = doPost(testData);
  Logger.log('処理完了');
  Logger.log('結果タイプ: ' + result.getMimeType());
}
