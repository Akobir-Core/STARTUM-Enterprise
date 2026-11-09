const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');
const html = read('frontend/index.html');
const js = read('frontend/script.js');
const sw = read('frontend/sw.js');
const api = read('backend/api.py');
const admin = read('backend/admin_panel/index.html');

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

expect(html.includes('id="languagePickerMenu"') && html.includes('data-language-option="ru"'), 'custom multilingual dropdown missing');
expect(html.includes('id="subjectSearch"') && html.includes('id="subjectSearchSubmit"'), 'catalogue search controls missing');
expect(html.includes('id="globalSearchKind"') && html.includes('value="subjects"') && html.includes('value="courses"'), 'catalogue type filters missing');
expect(html.includes('id="globalSearchSort"') && html.includes('value="newest"') && html.includes('value="az"'), 'catalogue sorting choices missing');
expect(html.includes('data-filter="special"'), 'special-program category filter missing');
expect(js.includes('function applyCatalogFilters()'), 'catalogue filtering function missing');
expect(js.includes('timer = window.setTimeout(() => applyCatalogFilters(), 180)'), 'debounced catalogue search missing');
expect(js.includes('fetch(`${API_BASE_URL}/catalog`'), 'catalogue is not loaded from the backend data source');
expect(js.includes('normalizeCatalogText(card.dataset.search || "").includes(query)'), 'multilingual catalogue text matching missing');
expect(!html.includes('value="packages"'), 'unsupported packages must not be advertised as searchable');
expect(api.includes('"created_at": c["created_at"]') && api.includes('"active": c["active"]'), 'catalogue API must expose stored creation metadata and active status');
expect(read('frontend/premium-experience.css').includes('.empty-state[hidden]') && read('frontend/premium-experience.css').includes('#special[hidden]'), 'catalogue hidden and empty states must obey hidden semantics');
expect(sw.includes('uploads|media\\/private'), 'PWA does not exclude uploads');
expect(sw.includes('isPublicBrandAsset'), 'PWA public asset allowlist missing');
expect(!/\/api\/.+cache\.put/.test(sw), 'PWA appears to cache API responses');
expect(api.includes("r.publication_status='published'") && api.includes('r.group_id IS NULL'), 'public resources access scope missing');
expect(admin.includes('data-view="groups"') && admin.includes('data-view="calendar"') && admin.includes('data-view="exports"'), 'enterprise admin modules missing');
expect(js.includes('"search.scope":') && js.includes('"search.sort":') && js.includes('"form.privacyNote":'), 'multilingual UI strings missing');
console.log('STARTUM enterprise frontend/API integration checks: PASS');
