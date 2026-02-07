// ====================================
// 営業リスト作成GAS v7
// 変更点（v6→v7）:
// - create_spreadsheet アクション追加（個別シート作成のみ）
//   → Difyワークフローから直接呼び出し可能
//   → マスターシート更新不要、スクレイピング結果を受け取ってシート作成
//
// 変更点（v4→v6）:
// - スクレイピング機能をすべて削除（Python APIに移行）
// - doPostは基本情報保存+個別シート作成のみ
// - update_scraped アクション追加（Python API結果でシート更新）
// ====================================

// ====================================
// 定数・設定
// ====================================

const MASTER_SHEET_ID = PropertiesService.getScriptProperties().getProperty('MASTER_SHEET_ID');
const MASTER_SHEET_NAME = '営業リスト_マスタ';
const OUTPUT_FOLDER_ID = PropertiesService.getScriptProperties().getProperty('OUTPUT_FOLDER_ID') || '';

const EXCLUDE_DOMAINS = [
  // 求人サイト
  'indeed.com', 'indeed.jp', 'mynavi.jp', 'rikunabi.com', 'doda.jp',
  'en-japan.com', 'baitoru.com', 'careerconnection.jp', 'jobchange.jp', 'hatarako.net',
  // ニュース・メディア
  'yahoo.co.jp', 'news.yahoo.co.jp', 'nikkei.com', 'asahi.com', 'yomiuri.co.jp',
  'mainichi.jp', 'sankei.com',
  // SNS
  'facebook.com', 'twitter.com', 'x.com', 'instagram.com',
  'youtube.com', 'tiktok.com', 'linkedin.com',
  // 百科事典
  'wikipedia.org', 'ja.wikipedia.org',
  // EC・大手
  'google.com', 'amazon.co.jp', 'rakuten.co.jp',
  // 企業情報・口コミサイト
  'bizmap.jp', 'baseconnect.in', 'wantedly.com', 'vorkers.com', 'openwork.jp',
  // 地図・ナビ・施設検索
  'navitime.co.jp', 'mapion.co.jp', 'mapfan.com', 'ekiten.jp',
  'hotpepper.jp', 'tabelog.com', 'gnavi.co.jp', 'retty.me',
  // 転職・キャリア系ポータル
  'career-x.co.jp', 'type.jp', 'green-japan.com', 'mid-tenshoku.com',
  // ブログ・技術系
  'note.com', 'qiita.com', 'zenn.dev', 'hateblo.jp', 'ameblo.jp',
  // プレスリリース
  'prtimes.jp', 'atpress.ne.jp',
  // 企業リスト・まとめ・その他
  'geekly.co.jp', 'imitsu.jp', 'houjin.jp',
  'factoring.southagency.co.jp', 'mics.city.shinagawa.tokyo.jp',
  'best100.v-tsushin.jp', 'isms.jp', 'itnabi.com',
  'appstars.io', 'ikesai.com', 'rekaizen.com',
  'careerforum.net', 'startupclass.co.jp', 'herp.careers', 'readycrew.jp',
  // 企業検索・マッチングサイト
  'biz.ne.jp', 'web-kanji.com', 'ipros.com'
];

// ====================================
// GET リクエスト（既存企業リスト取得）
// ====================================

function doGet(e) {
  try {
    const action = e.parameter.action || 'get_existing';
    
    if (action === 'get_existing') {
      const existing = getExistingCompanies();
      return createJsonResponse({
        status: 'success',
        data: {
          names: existing.names,
          domains: existing.domains,
          count: existing.names.length
        }
      });
    }
    
    return createJsonResponse({
      status: 'error',
      message: 'Unknown action'
    });
    
  } catch (error) {
    Logger.log('doGet エラー: ' + error.toString());
    return createJsonResponse({
      status: 'error',
      message: error.toString()
    });
  }
}

// ====================================
// POST リクエスト（メインエントリーポイント）
// v7: action で処理を分岐
//   - デフォルト: 基本情報保存 + 個別シート作成
//   - update_scraped: Python APIの結果でシート更新
//   - create_spreadsheet: 個別シート作成のみ（Difyから直接呼び出し用）
// ====================================

function doPost(e) {
  try {
    const requestData = JSON.parse(e.postData.contents);
    const action = requestData.action || 'save_basic';

    if (action === 'update_scraped') {
      return handleUpdateScraped(requestData);
    }

    if (action === 'create_spreadsheet') {
      return handleCreateSpreadsheet(requestData);
    }

    // デフォルト: 基本情報保存フロー
    return handleSaveBasic(requestData);

  } catch (error) {
    Logger.log('エラー発生: ' + error.toString());
    return createJsonResponse({
      status: 'error',
      message: error.toString()
    });
  }
}

// ====================================
// 個別シート作成のみ（Difyワークフローから直接呼び出し用）
// マスターシート更新なし、スクレイピング結果からシートを作成
// ====================================

function handleCreateSpreadsheet(requestData) {
  Logger.log('=== 個別シート作成フロー開始 ===');

  const results = requestData.results || [];
  const searchKeyword = requestData.search_keyword || '';

  if (results.length === 0) {
    return createJsonResponse({
      status: 'error',
      message: 'results配列が必要です'
    });
  }

  Logger.log('受信データ件数: ' + results.length);

  // 個別リスト作成
  var spreadsheetUrl = createIndividualSheet(results, searchKeyword);

  var successCount = results.filter(function(r) {
    return r.contact_url || r.phone;
  }).length;

  Logger.log('個別シート作成完了: ' + spreadsheetUrl);

  return createJsonResponse({
    status: 'success',
    totalCount: results.length,
    successCount: successCount,
    spreadsheetUrl: spreadsheetUrl
  });
}

// ====================================
// 基本情報保存フロー（デフォルトアクション）
// Difyから呼ばれる最初のPOST
// ====================================

function handleSaveBasic(requestData) {
  Logger.log('=== 基本情報保存フロー開始 ===');

  const companies = requestData.companies || [];
  const searchKeyword = requestData.search_keyword || '';
  const targetCount = parseInt(requestData.target_count) || 30;

  if (!companies || companies.length === 0) {
    return createJsonResponse({
      status: 'error',
      message: 'companies配列が必要です'
    });
  }

  Logger.log('受信データ件数: ' + companies.length);

  // ========== STEP 1: 重複チェック ==========
  Logger.log('STEP 1: 重複チェック');
  const existingCompanies = getExistingCompanies();
  const uniqueCompanies = filterDuplicates(companies, existingCompanies);
  const duplicateSkipped = companies.length - uniqueCompanies.length;
  Logger.log('重複除外後: ' + uniqueCompanies.length + '件（' + duplicateSkipped + '件スキップ）');

  const targetCompanies = uniqueCompanies.slice(0, targetCount);

  if (targetCompanies.length === 0) {
    return createJsonResponse({
      status: 'success',
      data: [],
      totalCount: 0,
      savedCount: 0,
      duplicateSkipped: duplicateSkipped,
      message: '全て既存企業のため新規保存なし'
    });
  }

  // ========== STEP 2: 基本情報を保存 ==========
  Logger.log('STEP 2: 基本情報保存（' + targetCompanies.length + '件）');
  var timestamp = Utilities.formatDate(new Date(), 'Asia/Tokyo', 'yyyy-MM-dd');
  var saveResult = saveBasicInfo(targetCompanies, searchKeyword, timestamp);
  Logger.log('基本情報保存完了: ' + saveResult.savedCount + '件');

  // ========== レスポンス ==========
  // Python APIに渡すための企業リストも返す
  var companiesForScraping = [];
  for (var i = 0; i < targetCompanies.length; i++) {
    companiesForScraping.push({
      company_name: targetCompanies[i].company_name || '',
      url: normalizeToTopPage(targetCompanies[i].url || '')
    });
  }

  return createJsonResponse({
    status: 'success',
    totalCount: targetCompanies.length,
    savedCount: saveResult.savedCount,
    duplicateSkipped: duplicateSkipped,
    startRow: saveResult.startRow,
    masterSheetUrl: saveResult.masterSheetUrl,
    search_keyword: searchKeyword,
    companies: companiesForScraping
  });
}

// ====================================
// スクレイピング結果更新フロー
// Python APIの結果を受け取ってシートを更新
// ====================================

function handleUpdateScraped(requestData) {
  Logger.log('=== スクレイピング結果更新フロー開始 ===');

  const results = requestData.results || [];
  const startRow = parseInt(requestData.start_row) || 0;
  const searchKeyword = requestData.search_keyword || '';

  if (results.length === 0) {
    return createJsonResponse({
      status: 'error',
      message: 'results配列が必要です'
    });
  }

  if (!startRow || startRow < 2) {
    return createJsonResponse({
      status: 'error',
      message: 'start_rowが無効です（2以上必要）'
    });
  }

  Logger.log('更新対象: ' + results.length + '件（開始行: ' + startRow + '）');

  // ========== マスターシート更新 ==========
  updateSheetWithScrapedData(results, startRow);

  // ========== 個別リスト作成 ==========
  var individualUrl = createIndividualSheet(results, searchKeyword);

  var successCount = results.filter(function(r) { 
    return r.contact_url || r.phone; 
  }).length;

  return createJsonResponse({
    status: 'success',
    updatedCount: results.length,
    successCount: successCount,
    spreadsheetUrl: individualUrl
  });
}

// ====================================
// 既存企業リスト取得
// ====================================

function getExistingCompanies() {
  var result = { names: [], domains: [] };

  try {
    if (!MASTER_SHEET_ID) return result;

    var ss = SpreadsheetApp.openById(MASTER_SHEET_ID);
    var sheet = ss.getSheetByName(MASTER_SHEET_NAME);

    if (!sheet) {
      sheet = createMasterSheet(ss);
      return result;
    }

    var lastRow = sheet.getLastRow();
    if (lastRow <= 1) return result;

    var data = sheet.getRange(2, 1, lastRow - 1, 7).getValues();

    for (var i = 0; i < data.length; i++) {
      if (data[i][0]) result.names.push(String(data[i][0]).trim().toLowerCase());
      if (data[i][4]) result.domains.push(String(data[i][4]).trim().toLowerCase());
    }
  } catch (e) {
    Logger.log('既存データ取得エラー: ' + e.toString());
  }

  return result;
}

// ====================================
// マスターシート作成・ヘッダー設定
// ====================================

function createMasterSheet(ss) {
  var sheet = ss.insertSheet(MASTER_SHEET_NAME);
  setSheetHeaders(sheet);
  return sheet;
}

function setSheetHeaders(sheet) {
  var headers = ['企業名', '企業URL', 'お問い合わせURL', '電話番号', 'ドメイン', '検索キーワード', '取得日'];
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
  sheet.getRange(1, 1, 1, headers.length).setBackground('#4285f4');
  sheet.getRange(1, 1, 1, headers.length).setFontColor('white');
  sheet.setColumnWidth(1, 200);
  sheet.setColumnWidth(2, 300);
  sheet.setColumnWidth(3, 300);
  sheet.setColumnWidth(4, 150);
  sheet.setColumnWidth(5, 200);
  sheet.setColumnWidth(6, 200);
  sheet.setColumnWidth(7, 120);
  sheet.setFrozenRows(1);
}

// ====================================
// 重複フィルタリング
// ====================================

function filterDuplicates(companies, existing) {
  var uniqueCompanies = [];
  var seenDomains = {};
  var seenNames = {};

  for (var i = 0; i < existing.domains.length; i++) {
    seenDomains[existing.domains[i].toLowerCase()] = true;
  }
  for (var j = 0; j < existing.names.length; j++) {
    seenNames[existing.names[j].toLowerCase()] = true;
  }

  for (var k = 0; k < companies.length; k++) {
    var company = companies[k];
    var companyName = (company.company_name || '').trim();
    var url = (company.url || '').trim();
    var domain = extractDomain(url).toLowerCase();

    if (companyName && seenNames[companyName.toLowerCase()]) continue;
    if (domain && seenDomains[domain]) continue;

    var isExcluded = false;
    for (var d = 0; d < EXCLUDE_DOMAINS.length; d++) {
      if (domain.indexOf(EXCLUDE_DOMAINS[d]) !== -1) {
        isExcluded = true;
        break;
      }
    }
    if (isExcluded) continue;

    if (domain) seenDomains[domain] = true;
    if (companyName) seenNames[companyName.toLowerCase()] = true;
    uniqueCompanies.push(company);
  }

  return uniqueCompanies;
}

// ====================================
// 基本情報をスプレッドシートに保存
// ====================================

function saveBasicInfo(companies, searchKeyword, timestamp) {
  var result = { savedCount: 0, startRow: 2, masterSheetUrl: '' };

  if (!MASTER_SHEET_ID) return result;

  try {
    var ss = SpreadsheetApp.openById(MASTER_SHEET_ID);
    var sheet = ss.getSheetByName(MASTER_SHEET_NAME);

    if (!sheet) {
      sheet = createMasterSheet(ss);
    }

    // ヘッダー確認
    var headerRow = sheet.getRange(1, 1, 1, 7).getValues()[0];
    if (headerRow[0] !== '企業名') {
      setSheetHeaders(sheet);
    }

    // 保存直前に再度重複チェック
    var latestExisting = getExistingCompanies();
    var existingDomains = {};
    for (var e = 0; e < latestExisting.domains.length; e++) {
      existingDomains[latestExisting.domains[e]] = true;
    }

    var dataRows = [];
    var savedDomains = {};

    for (var i = 0; i < companies.length; i++) {
      var c = companies[i];
      var domain = extractDomain(c.url || '').toLowerCase();
      var name = (c.company_name || '').trim().toLowerCase();

      if (domain && existingDomains[domain]) continue;
      if (domain && savedDomains[domain]) continue;

      if (domain) savedDomains[domain] = true;

      dataRows.push([
        c.company_name || '',
        normalizeToTopPage(c.url || ''),
        '',   // お問い合わせURL（update_scrapedで更新）
        '',   // 電話番号（update_scrapedで更新）
        domain,
        searchKeyword,
        timestamp
      ]);
    }

    if (dataRows.length > 0) {
      var lastRow = sheet.getLastRow();
      var startRow = Math.max(lastRow + 1, 2);
      sheet.getRange(startRow, 1, dataRows.length, 7).setValues(dataRows);
      result.savedCount = dataRows.length;
      result.startRow = startRow;
      Logger.log('基本情報' + dataRows.length + '件保存（行' + startRow + '〜）');
    }

    result.masterSheetUrl = ss.getUrl();
  } catch (e) {
    Logger.log('基本情報保存エラー: ' + e.toString());
  }

  return result;
}

// ====================================
// スクレイピング結果でマスターシートを更新
// ====================================

function updateSheetWithScrapedData(results, startRow) {
  if (!MASTER_SHEET_ID || !results || results.length === 0) return;

  try {
    var ss = SpreadsheetApp.openById(MASTER_SHEET_ID);
    var sheet = ss.getSheetByName(MASTER_SHEET_NAME);
    if (!sheet) return;

    // C列（お問い合わせURL）とD列（電話番号）を更新
    var updateData = [];
    for (var i = 0; i < results.length; i++) {
      updateData.push([
        results[i].contact_url || '',
        results[i].phone || ''
      ]);
    }

    if (updateData.length > 0) {
      sheet.getRange(startRow, 3, updateData.length, 2).setValues(updateData);
      Logger.log('スクレイピング結果でシート更新完了（' + updateData.length + '行）');
    }
  } catch (e) {
    Logger.log('シート更新エラー: ' + e.toString());
  }
}

// ====================================
// 個別リスト作成
// ====================================

function createIndividualSheet(companies, searchKeyword) {
  try {
    var timestampFull = Utilities.formatDate(new Date(), 'Asia/Tokyo', 'yyyyMMdd_HHmmss');
    var sheetName = '営業リスト_' + searchKeyword + '_' + timestampFull;
    if (sheetName.length > 100) sheetName = sheetName.substring(0, 100);

    var newSS = SpreadsheetApp.create(sheetName);
    var newSheet = newSS.getActiveSheet();

    var headers = ['企業名', '企業URL', 'お問い合わせURL', '電話番号'];
    newSheet.getRange(1, 1, 1, headers.length).setValues([headers]);
    newSheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
    newSheet.getRange(1, 1, 1, headers.length).setBackground('#4285f4');
    newSheet.getRange(1, 1, 1, headers.length).setFontColor('white');

    if (companies.length > 0) {
      var rows = [];
      for (var j = 0; j < companies.length; j++) {
        var comp = companies[j];
        rows.push([
          comp.company_name || '',
          comp.base_url || '',
          comp.contact_url || '',
          comp.phone || ''
        ]);
      }
      newSheet.getRange(2, 1, rows.length, headers.length).setValues(rows);
    }

    for (var k = 1; k <= headers.length; k++) {
      newSheet.autoResizeColumn(k);
    }

    if (OUTPUT_FOLDER_ID) {
      try {
        var file = DriveApp.getFileById(newSS.getId());
        var folder = DriveApp.getFolderById(OUTPUT_FOLDER_ID);
        folder.addFile(file);
        DriveApp.getRootFolder().removeFile(file);
      } catch (e) {
        Logger.log('フォルダ移動エラー: ' + e.toString());
      }
    }

    return newSS.getUrl();
  } catch (e) {
    Logger.log('個別リスト作成エラー: ' + e.toString());
    return '';
  }
}

// ====================================
// ユーティリティ関数
// ====================================

function normalizeToTopPage(url) {
  try {
    var match = url.match(/^(https?:\/\/[^\/]+)/);
    if (match) return match[1] + '/';
  } catch (e) {}
  return url;
}

function extractDomain(url) {
  var match = (url || '').match(/^https?:\/\/([^\/]+)/);
  return match ? match[1] : url;
}

function createJsonResponse(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}

// ====================================
// テスト関数
// ====================================

function testDoGet() {
  var result = doGet({ parameter: { action: 'get_existing' } });
  Logger.log(result.getContent());
}

function testSaveBasic() {
  var testData = {
    companies: [
      { company_name: 'テスト株式会社', url: 'https://www.example.co.jp/' }
    ],
    search_keyword: 'テスト',
    target_count: 30
  };

  var result = doPost({ postData: { contents: JSON.stringify(testData) } });
  Logger.log(result.getContent());
}

function testUpdateScraped() {
  var testData = {
    action: 'update_scraped',
    start_row: 2,
    search_keyword: 'テスト',
    results: [
      {
        company_name: 'テスト株式会社',
        base_url: 'https://www.example.co.jp/',
        contact_url: 'https://www.example.co.jp/contact/',
        phone: '03-1234-5678'
      }
    ]
  };

  var result = doPost({ postData: { contents: JSON.stringify(testData) } });
  Logger.log(result.getContent());
}

// create_spreadsheet アクションのテスト（Difyワークフローから呼ばれる形式）
function testCreateSpreadsheet() {
  var testData = {
    action: 'create_spreadsheet',
    search_keyword: '東京のIT企業',
    results: [
      {
        company_name: 'サンプル株式会社',
        base_url: 'https://www.sample.co.jp/',
        contact_url: 'https://www.sample.co.jp/contact/',
        phone: '03-1234-5678'
      },
      {
        company_name: 'テスト合同会社',
        base_url: 'https://www.test-llc.jp/',
        contact_url: 'https://www.test-llc.jp/inquiry/',
        phone: '06-9876-5432'
      }
    ]
  };

  var result = doPost({ postData: { contents: JSON.stringify(testData) } });
  Logger.log(result.getContent());
}

// ====================================
// メンテナンス用関数
// ====================================

function repairMasterSheetHeaders() {
  if (!MASTER_SHEET_ID) return;
  var ss = SpreadsheetApp.openById(MASTER_SHEET_ID);
  var sheet = ss.getSheetByName(MASTER_SHEET_NAME);
  if (!sheet) return;
  var first = sheet.getRange(1, 1, 1, 7).getValues()[0];
  if (first[0] && first[0] !== '企業名') {
    sheet.insertRowBefore(1);
    setSheetHeaders(sheet);
    Logger.log('ヘッダー挿入完了');
  }
}

function removeDuplicatesFromMaster() {
  if (!MASTER_SHEET_ID) return;
  var ss = SpreadsheetApp.openById(MASTER_SHEET_ID);
  var sheet = ss.getSheetByName(MASTER_SHEET_NAME);
  if (!sheet) return;
  var lastRow = sheet.getLastRow();
  if (lastRow <= 1) return;
  var data = sheet.getRange(2, 1, lastRow - 1, 7).getValues();
  var seenDomains = {};
  var rowsToDelete = [];
  for (var i = 0; i < data.length; i++) {
    var domain = (data[i][4] || '').toString().trim().toLowerCase();
    if (domain && seenDomains[domain]) {
      rowsToDelete.push(i + 2);
    } else if (domain) {
      seenDomains[domain] = true;
    }
  }
  for (var j = rowsToDelete.length - 1; j >= 0; j--) {
    sheet.deleteRow(rowsToDelete[j]);
  }
  Logger.log('重複除去完了: ' + rowsToDelete.length + '行削除');
}

function clearMasterSheet() {
  if (!MASTER_SHEET_ID) return;
  var ss = SpreadsheetApp.openById(MASTER_SHEET_ID);
  var sheet = ss.getSheetByName(MASTER_SHEET_NAME);
  if (!sheet) return;
  var lastRow = sheet.getLastRow();
  if (lastRow <= 1) return;
  sheet.deleteRows(2, lastRow - 1);
  Logger.log('クリア完了: ' + (lastRow - 1) + '行削除');
}