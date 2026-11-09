const assert = require('node:assert/strict');
const fs = require('node:fs');
const html = fs.readFileSync('frontend/index.html', 'utf8');
const publicCss = fs.readFileSync('frontend/premium-experience.css', 'utf8');
const adminHtml = fs.readFileSync('backend/admin_panel/index.html', 'utf8');
const adminJs = fs.readFileSync('backend/admin_panel/admin.js', 'utf8');
const adminCss = fs.readFileSync('backend/admin_panel/admin.css', 'utf8');

assert.ok(adminHtml.includes('id="sidebarBackdrop"'));
assert.ok(adminHtml.includes('aria-controls="sidebar"'));
const navViews = [...adminHtml.matchAll(/data-view="([^"]+)"/g)].map(match => match[1]);
assert.equal(new Set(navViews).size, 13, 'all 13 existing admin views remain available');
assert.ok(adminHtml.includes('data-nav-group'), 'admin navigation is grouped without removing views');
assert.ok(adminJs.includes('function setMobileSidebar(open)'));
assert.ok(adminJs.includes("event.key === 'Escape'"));
assert.ok(adminJs.includes('sidebar.inert = isMobile && !shouldOpen'));
assert.ok(adminJs.includes("setAttribute('aria-hidden'"));
assert.ok(adminJs.includes("window.matchMedia('(max-width: 780px)')"));
assert.ok(adminJs.includes("setAttribute('aria-expanded'"));
assert.ok(adminCss.includes('.sidebar-backdrop:not([hidden])'));
assert.ok(adminCss.includes('body.admin-nav-open'));
assert.ok(adminCss.includes('.nav-group-label'));
assert.ok(adminCss.includes('.application-detail-row[hidden]'));
assert.ok(adminCss.includes('env(safe-area-inset-bottom)'));

for (const width of ['max-width: 960px', 'max-width: 680px', 'max-width: 359px']) {
  assert.ok(publicCss.includes(width), `public responsive breakpoint ${width} exists`);
}
assert.ok(publicCss.includes('grid-template-columns: repeat(2, minmax(0, 1fr))'));
assert.ok(publicCss.includes('text-wrap: pretty'));
assert.ok(publicCss.includes('prefers-reduced-motion: reduce'));
assert.ok(html.includes('type="tel"'));
assert.ok(publicCss.includes('overscroll-behavior: contain'));

console.log('STARTUM final stabilization/mobile drawer contract: PASS');
