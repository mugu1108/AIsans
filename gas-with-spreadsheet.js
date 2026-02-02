// ====================================
// 定数・設定
// ====================================

const GOOGLE_API_KEY = PropertiesService.getScriptProperties().getProperty('GOOGLE_API_KEY');
const SEARCH_ENGINE_ID = PropertiesService.getScriptProperties().getProperty('SEARCH_ENGINE_ID');
const OUTPUT_FOLDER_ID = PropertiesService.getScriptProperties().getProperty('OUTPUT_FOLDER_ID') || '';

const EXCLUDE_DOMAINS = [
  'indeed.com', 'indeed.jp', 'mynavi.jp', 'rikunabi.com', 'doda.jp',
  'en-japan.com', 'baitoru.com', 'careerconnection.jp', 'jobchange.jp', 'hatarako.net',
  'yahoo.co.jp', 'news.yahoo.co.jp', 'nikkei.com', 'asahi.com', 'yomiuri.co.jp',
  'mainichi.jp', 'sankei.com', 'facebook.com', 'twitter.com', 'instagram.com',
  'youtube.com', 'tiktok.com', 'wikipedia.org', 'ja.wikipedia.org',
  'google.com', 'amazon.co.jp', 'rakuten.co.jp', 'linkedin.com',
  'bizmap.jp', 'baseconnect.in', 'wantedly.com', 'vorkers.com', 'openwork.jp',
  'bigcompany.jp', 'matching.', 'monodukuri-yokohama.com',
  '.lg.jp', '.go.jp', 'city.yokohama', '.or.jp', 'idec.or.jp', 'xn--'
];

const EXCLUDE_URL_PATTERNS = [
  '//list/', '/companies/', '/company/',
  '/keyword/', '/area/', '/city/', '/topics'
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
    const outputFormat = requestData.outputFormat || 'csv';
    const folderId = requestData.folderId || OUTPUT_FOLDER_ID;

    if (!region || !industry) {
      return createJsonResponse({ status: 'error', message: 'region/industry必須' });
    }

    // 出力形式に応じて処理を分岐
    if (outputFormat === 'both') {
      // CSV + スプレッドシートの両方を作成（1回の検索で）
      return generateBothResponse(region, industry, count, folderId);
    } else if (outputFormat === 'spreadsheet') {
      return generateSpreadsheetResponse(region, industry, count, folderId);
    } else {
      return generateCSVResponse(region, industry, count);
    }

  } catch (error) {
    Logger.log('エラー発生: ' + error.toString());
    return createJsonResponse({ status: 'error', message: error.toString() });
  }
}

// ====================================
// CSV + スプレッドシート両方を生成（1回の検索）
// ====================================

function generateBothResponse(region, industry, targetCount, folderId) {
  const startTime = new Date();
  Logger.log('CSV+スプレッドシート作成開始: ' + region + ' ' + industry + ' 目標' + targetCount + '件');

  // 企業データを1回だけ収集
  const companies = collectCompanyData(region, industry, targetCount);

  if (companies.length === 0) {
    return createJsonResponse({
      status: 'error',
      message: '企業データを収集できませんでした'
    });
  }

  // CSV生成
  const csv = generateCSV(companies);
  const csvBase64 = Utilities.base64Encode(csv, Utilities.Charset.UTF_8);

  // スプレッドシート作成
  const timestamp = Utilities.formatDate(new Date(), 'Asia/Tokyo', 'yyyyMMdd_HHmmss');
  const sheetName = '営業リスト_' + region + '_' + industry + '_' + timestamp;

  const spreadsheet = SpreadsheetApp.create(sheetName);
  const sheet = spreadsheet.getActiveSheet();

  // ヘッダー行を設定
  const headers = ['企業名', '企業URL', 'お問い合わせURL', '電話番号'];
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
  sheet.getRange(1, 1, 1, headers.length).setBackground('#4285f4');
  sheet.getRange(1, 1, 1, headers.length).setFontColor('white');

  // データを書き込み
  if (companies.length > 0) {
    const dataRows = companies.map(function(c) {
      return [
        c.company_name || '',
        c.base_url || '',
        c.contact_url || '',
        c.phone || ''
      ];
    });
    sheet.getRange(2, 1, dataRows.length, headers.length).setValues(dataRows);
  }

  // 列幅を自動調整
  for (var i = 1; i <= headers.length; i++) {
    sheet.autoResizeColumn(i);
  }

  // 指定フォルダに移動
  const spreadsheetId = spreadsheet.getId();
  const spreadsheetUrl = spreadsheet.getUrl();

  if (folderId) {
    try {
      const file = DriveApp.getFileById(spreadsheetId);
      const folder = DriveApp.getFolderById(folderId);
      folder.addFile(file);
      DriveApp.getRootFolder().removeFile(file);
      Logger.log('スプレッドシートをフォルダに移動完了');
    } catch (e) {
      Logger.log('フォルダ移動エラー（続行）: ' + e.toString());
    }
  }

  const elapsed = new Date() - startTime;
  Logger.log('CSV+スプレッドシート作成完了: ' + elapsed + 'ms, ' + companies.length + '件');

  // CSV（Base64）とスプレッドシート情報を両方返す
  return createJsonResponse({
    status: 'success',
    csvBase64: csvBase64,
    spreadsheetId: spreadsheetId,
    spreadsheetUrl: spreadsheetUrl,
    title: sheetName,
    rowCount: companies.length,
    processingTime: elapsed
  });
}

// ====================================
// スプレッドシートのみ生成
// ====================================

function generateSpreadsheetResponse(region, industry, targetCount, folderId) {
  const startTime = new Date();
  Logger.log('スプレッドシート作成開始: ' + region + ' ' + industry + ' 目標' + targetCount + '件');

  const companies = collectCompanyData(region, industry, targetCount);

  if (companies.length === 0) {
    return createJsonResponse({
      status: 'error',
      message: '企業データを収集できませんでした'
    });
  }

  const timestamp = Utilities.formatDate(new Date(), 'Asia/Tokyo', 'yyyyMMdd_HHmmss');
  const sheetName = '営業リスト_' + region + '_' + industry + '_' + timestamp;

  const spreadsheet = SpreadsheetApp.create(sheetName);
  const sheet = spreadsheet.getActiveSheet();

  const headers = ['企業名', '企業URL', 'お問い合わせURL', '電話番号'];
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
  sheet.getRange(1, 1, 1, headers.length).setBackground('#4285f4');
  sheet.getRange(1, 1, 1, headers.length).setFontColor('white');

  if (companies.length > 0) {
    const dataRows = companies.map(function(c) {
      return [c.company_name || '', c.base_url || '', c.contact_url || '', c.phone || ''];
    });
    sheet.getRange(2, 1, dataRows.length, headers.length).setValues(dataRows);
  }

  for (var i = 1; i <= headers.length; i++) {
    sheet.autoResizeColumn(i);
  }

  const spreadsheetId = spreadsheet.getId();
  const spreadsheetUrl = spreadsheet.getUrl();

  if (folderId) {
    try {
      const file = DriveApp.getFileById(spreadsheetId);
      const folder = DriveApp.getFolderById(folderId);
      folder.addFile(file);
      DriveApp.getRootFolder().removeFile(file);
    } catch (e) {
      Logger.log('フォルダ移動エラー: ' + e.toString());
    }
  }

  const elapsed = new Date() - startTime;

  return createJsonResponse({
    status: 'success',
    spreadsheetId: spreadsheetId,
    spreadsheetUrl: spreadsheetUrl,
    title: sheetName,
    rowCount: companies.length,
    processingTime: elapsed
  });
}

// ====================================
// CSVのみ生成
// ====================================

function generateCSVResponse(region, industry, targetCount) {
  const startTime = new Date();
  Logger.log('検索開始: ' + region + ' ' + industry + ' 目標' + targetCount + '件');

  const companies = collectCompanyData(region, industry, targetCount);
  const csv = generateCSV(companies);

  const elapsed = new Date() - startTime;
  Logger.log('処理時間: ' + elapsed + 'ms');

  return ContentService
    .createTextOutput(csv)
    .setMimeType(ContentService.MimeType.CSV);
}

// ====================================
// 企業データ収集（共通処理）
// ====================================

function collectCompanyData(region, industry, targetCount) {
  const searchQueries = [
    region + ' ' + industry + ' 株式会社',
    region + ' ' + industry + ' 企業',
    region + ' ' + industry + ' 有限会社',
    region + ' ' + industry + ' 工場',
    region + ' ' + industry + ' メーカー',
    region + ' ' + industry + ' 会社',
    industry + ' ' + region + ' 株式会社',
    industry + ' ' + region + ' 企業',
    region + ' ' + industry + ' 本社',
    region + ' ' + industry + ' 工業',
    region + ' ' + industry + ' 産業',
    industry + ' 企業 ' + region + '市',
    industry + ' 会社 ' + region + '県',
    region + ' ' + industry + ' 法人',
    region + ' ' + industry + ' 商会',
    region + ' ' + industry + ' 製造'
  ];

  const seenDomains = {};
  const confirmedCompanies = [];
  const pendingCandidates = [];

  for (var qi = 0; qi < searchQueries.length; qi++) {
    if (confirmedCompanies.length >= targetCount) break;

    var query = searchQueries[qi];
    Logger.log('検索クエリ: ' + query);
    var searchResults = performGoogleSearchBatch(query, 30);
    var newCandidates = filterCompanyCandidates(searchResults, seenDomains);

    Logger.log('新規候補: ' + newCandidates.length + '件');

    if (newCandidates.length === 0) continue;

    var verified = fetchAndVerifyCompanies(newCandidates, targetCount);

    for (var ci = 0; ci < verified.confirmed.length; ci++) {
      if (confirmedCompanies.length >= targetCount) break;
      confirmedCompanies.push(verified.confirmed[ci]);
    }

    for (var pi = 0; pi < verified.pending.length; pi++) {
      pendingCandidates.push(verified.pending[pi]);
    }

    Logger.log('確認済み: ' + confirmedCompanies.length + '/' + targetCount + '件');
  }

  if (confirmedCompanies.length < targetCount && pendingCandidates.length > 0) {
    var needed = targetCount - confirmedCompanies.length;
    var additionalVerified = fetchAndVerifyCompanies(pendingCandidates, needed);

    for (var ai = 0; ai < additionalVerified.confirmed.length; ai++) {
      if (confirmedCompanies.length >= targetCount) break;
      confirmedCompanies.push(additionalVerified.confirmed[ai]);
    }
  }

  if (confirmedCompanies.length < targetCount && pendingCandidates.length > 0) {
    var existingUrls = {};
    for (var ei = 0; ei < confirmedCompanies.length; ei++) {
      existingUrls[confirmedCompanies[ei].base_url] = true;
    }

    for (var gi = 0; gi < pendingCandidates.length; gi++) {
      if (confirmedCompanies.length >= targetCount) break;
      var candidate = pendingCandidates[gi];
      if (existingUrls[candidate.base_url]) continue;

      confirmedCompanies.push({
        company_name: candidate.company_name,
        base_url: candidate.base_url,
        contact_url: guessContactUrl(candidate.base_url),
        phone: ''
      });
    }
  }

  Logger.log('最終件数: ' + confirmedCompanies.length + '件');
  return confirmedCompanies;
}

// ====================================
// 並列Google検索
// ====================================

function performGoogleSearchBatch(query, maxResults) {
  const numPerRequest = 10;
  const numRequests = Math.min(Math.ceil(maxResults / numPerRequest), 3);

  const requests = [];
  for (var i = 0; i < numRequests; i++) {
    const startIndex = i * numPerRequest + 1;
    const url = 'https://www.googleapis.com/customsearch/v1?' +
      'key=' + GOOGLE_API_KEY +
      '&cx=' + SEARCH_ENGINE_ID +
      '&q=' + encodeURIComponent(query) +
      '&start=' + startIndex +
      '&num=' + numPerRequest;

    requests.push({ url: url, muteHttpExceptions: true });
  }

  const responses = UrlFetchApp.fetchAll(requests);
  const results = [];

  for (var ri = 0; ri < responses.length; ri++) {
    if (responses[ri].getResponseCode() === 200) {
      try {
        const data = JSON.parse(responses[ri].getContentText());
        if (data.items) {
          for (var di = 0; di < data.items.length; di++) {
            results.push(data.items[di]);
          }
        }
      } catch (e) {}
    }
  }

  return results;
}

// ====================================
// 企業フィルタリング
// ====================================

function filterCompanyCandidates(searchResults, seenDomains) {
  const candidates = [];

  for (var i = 0; i < searchResults.length; i++) {
    const result = searchResults[i];
    const baseUrl = result.link;
    if (!isCompanySite(baseUrl)) continue;

    const domain = extractDomain(baseUrl);
    if (seenDomains[domain]) continue;
    seenDomains[domain] = true;

    const companyName = extractCompanyName(result.title);
    if (!companyName || companyName.length < 2) continue;

    candidates.push({
      company_name: companyName,
      base_url: baseUrl
    });
  }

  return candidates;
}

// ====================================
// サイトアクセスして確認
// ====================================

function fetchAndVerifyCompanies(candidates, maxNeeded) {
  const confirmed = [];
  const pending = [];
  const batchSize = 8;

  for (var i = 0; i < candidates.length; i += batchSize) {
    if (confirmed.length >= maxNeeded) break;

    const batch = candidates.slice(i, i + batchSize);
    const requests = [];
    for (var bi = 0; bi < batch.length; bi++) {
      requests.push({
        url: batch[bi].base_url,
        muteHttpExceptions: true,
        followRedirects: true,
        validateHttpsCertificates: false
      });
    }

    var responses;
    try {
      responses = UrlFetchApp.fetchAll(requests);
    } catch (e) {
      for (var ei = 0; ei < batch.length; ei++) {
        pending.push(batch[ei]);
      }
      continue;
    }

    for (var j = 0; j < batch.length; j++) {
      const candidate = batch[j];
      const response = responses[j];

      var contactUrl = '';
      var phone = '';

      try {
        if (response.getResponseCode() === 200) {
          const html = response.getContentText();
          contactUrl = extractContactFromHtml(html, candidate.base_url);
          phone = extractPhoneFromHtml(html);
        }
      } catch (e) {}

      if (contactUrl) {
        confirmed.push({
          company_name: candidate.company_name,
          base_url: candidate.base_url,
          contact_url: contactUrl,
          phone: phone
        });
      } else {
        pending.push(candidate);
      }
    }
  }

  return { confirmed: confirmed, pending: pending };
}

// ====================================
// 電話番号抽出
// ====================================

function extractPhoneFromHtml(html) {
  const patterns = [
    /(?:TEL|Tel|tel|電話|☎|📞|℡)[\s:：]*?(0\d{1,4}[-\s]?\d{1,4}[-\s]?\d{3,4})/,
    /href=["']tel:(0\d{1,4}[-\s]?\d{1,4}[-\s]?\d{3,4})["']/,
    /(0\d{1,4}[-−‐ー\s]?\d{1,4}[-−‐ー\s]?\d{3,4})/
  ];

  for (var i = 0; i < patterns.length; i++) {
    const match = html.match(patterns[i]);
    if (match && match[1]) {
      var phone = match[1].replace(/[-−‐ー\s]/g, '-');
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
  var csv = '\uFEFF';
  csv += '企業名,企業URL,お問い合わせURL,電話番号\n';

  for (var i = 0; i < companies.length; i++) {
    var c = companies[i];
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
  var str = String(value);
  if (str.indexOf(',') !== -1 || str.indexOf('\n') !== -1 || str.indexOf('"') !== -1) {
    return '"' + str.replace(/"/g, '""') + '"';
  }
  return str;
}

// ====================================
// ユーティリティ
// ====================================

function isCompanySite(url) {
  if (!url) return false;
  const lower = url.toLowerCase();
  for (var i = 0; i < EXCLUDE_DOMAINS.length; i++) {
    if (lower.indexOf(EXCLUDE_DOMAINS[i]) !== -1) return false;
  }
  for (var j = 0; j < EXCLUDE_URL_PATTERNS.length; j++) {
    if (lower.indexOf(EXCLUDE_URL_PATTERNS[j]) !== -1) return false;
  }
  return lower.indexOf('.co.jp') !== -1 || lower.indexOf('.jp') !== -1 || lower.indexOf('.com') !== -1;
}

function extractDomain(url) {
  const match = url.match(/^https?:\/\/([^\/]+)/);
  return match ? match[1] : url;
}

function extractCompanyName(title) {
  const seps = ['｜', '|', ' - ', '－'];
  for (var i = 0; i < seps.length; i++) {
    if (title.indexOf(seps[i]) !== -1) {
      return title.split(seps[i])[0].trim();
    }
  }
  return title.substring(0, 50).trim();
}

function extractContactFromHtml(html, baseUrl) {
  const keywords = ['contact', 'inquiry', 'お問い合わせ', 'お問合せ', 'toiawase', 'otoiawase', 'form'];
  const pattern = /<a\s+[^>]*href=["']([^"'#]+)["'][^>]*>([\s\S]*?)<\/a>/gi;
  var match;

  while ((match = pattern.exec(html)) !== null) {
    const href = match[1].toLowerCase();
    const text = (match[2] || '').replace(/<[^>]*>/g, '').toLowerCase();

    if (href.indexOf('mailto:') === 0) continue;

    for (var i = 0; i < keywords.length; i++) {
      if (href.indexOf(keywords[i]) !== -1 || text.indexOf(keywords[i]) !== -1) {
        const fullUrl = resolveUrl(baseUrl, match[1]);
        if (isSameDomain(baseUrl, fullUrl)) return fullUrl;
      }
    }
  }
  return '';
}

function resolveUrl(baseUrl, relativeUrl) {
  if (relativeUrl.indexOf('http') === 0) return relativeUrl;
  const match = baseUrl.match(/^(https?:\/\/[^\/]+)/);
  if (!match) return relativeUrl;
  return relativeUrl.indexOf('/') === 0 ? match[1] + relativeUrl : match[1] + '/' + relativeUrl;
}

function isSameDomain(url1, url2) {
  return extractDomain(url1) === extractDomain(url2);
}

function createJsonResponse(data) {
  return ContentService.createTextOutput(JSON.stringify(data)).setMimeType(ContentService.MimeType.JSON);
}

// ====================================
// テスト関数
// ====================================

function testFunction() {
  Logger.log('=== 環境変数確認 ===');
  Logger.log('GOOGLE_API_KEY: ' + (GOOGLE_API_KEY ? '設定あり' : '未設定'));
  Logger.log('SEARCH_ENGINE_ID: ' + (SEARCH_ENGINE_ID ? '設定あり' : '未設定'));
  Logger.log('OUTPUT_FOLDER_ID: ' + (OUTPUT_FOLDER_ID ? OUTPUT_FOLDER_ID : '未設定'));
}

function testBothCreation() {
  Logger.log('=== CSV+スプレッドシート同時作成テスト ===');

  const mockRequest = {
    postData: {
      contents: JSON.stringify({
        region: '横浜市',
        industry: '製造業',
        count: 5,
        outputFormat: 'both',
        folderId: OUTPUT_FOLDER_ID
      })
    }
  };

  const result = doPost(mockRequest);
  Logger.log('結果: ' + result.getContent());
}
