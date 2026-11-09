const assert = require('node:assert/strict');
const fs = require('node:fs');
const html = fs.readFileSync('frontend/index.html', 'utf8');
const js = fs.readFileSync('frontend/script.js', 'utf8');
const css = fs.readFileSync('frontend/premium-experience.css', 'utf8');
const serviceWorker = fs.readFileSync('frontend/sw.js', 'utf8');
const darkImagePath = 'frontend/assets/images/startum-dark-hero.webp';
const darkImage = fs.readFileSync(darkImagePath);

assert.equal(darkImage.subarray(0, 4).toString('ascii'), 'RIFF');
assert.equal(darkImage.subarray(8, 12).toString('ascii'), 'WEBP');
assert.ok(darkImage.length > 20_000, 'generated Dark Mode image must be a real optimized asset');
assert.ok(js.includes('assets/images/startum-dark-hero.webp'));
assert.ok(js.includes('assets/images/startum-day-hero.webp'));
assert.ok(!js.includes('assets/images/startum-aeline-student.jpg'), 'protected original is no longer the active Dark Mode hero');

// The hero image alt text is localized for every supported language.
const dictSections = {
  uz: js.match(/\n  uz: \{([\s\S]*?)\n  \},\n  ru: \{/),
  ru: js.match(/\n  ru: \{([\s\S]*?)\n  \},\n  en: \{/),
  en: js.match(/\n  en: \{([\s\S]*?)\n  \},\n\};*/),
};
for (const [locale, match] of Object.entries(dictSections)) {
  assert.ok(match, `I18N ${locale} dictionary exists`);
  const keys = new Set([...match[1].matchAll(/^\s*"([^"]+)"\s*:/gm)].map((m) => m[1]));
  for (const key of ['hero.imageAltLight', 'hero.imageAltDark']) {
    assert.ok(keys.has(key), `${locale} must define ${key}`);
  }
}
const htmlKeys = [...html.matchAll(/data-i18n(?:-html|-placeholder|-aria)?="([^"]+)"/g)].map((m) => m[1]);
const scriptTranslationCalls = [...js.matchAll(/\bt\(\s*["']([^"']+)["']\s*\)/g)].map((m) => m[1]);
for (const [locale, match] of Object.entries(dictSections)) {
  const keys = new Set([...match[1].matchAll(/^\s*"([^"]+)"\s*:/gm)].map((m) => m[1]));
  const missingHtml = [...new Set(htmlKeys)].filter((key) => !keys.has(key));
  const missingScript = [...new Set(scriptTranslationCalls)].filter((key) => !keys.has(key));
  assert.deepEqual(missingHtml, [], `all static HTML strings must be translated in ${locale}`);
  assert.deepEqual(missingScript, [], `all literal script translation calls must be translated in ${locale}`);
}
assert.match(
  js,
  /heroThemeImage\.alt\s*=\s*t\(\s*currentTheme\s*===\s*["']dark["']\s*\?\s*["']hero\.imageAltDark["']\s*:\s*["']hero\.imageAltLight["']\s*,?\s*\)/,
  'hero image alt text must follow the active theme and locale',
);

// Scroll stability: background glows travel with the document; only intended controls stay sticky/fixed.
assert.match(css, /body\s*\{[^}]*position:\s*relative;[^}]*isolation:\s*isolate;[^}]*overflow-x:\s*clip;/s);
assert.match(css, /\.ambient\s*\{[^}]*position:\s*absolute;/s);
assert.match(css, /:root\[data-theme="dark"\] \.hero-visual::after\s*\{[^}]*animation:\s*none\s*!important;/s);
assert.match(css, /:root\[data-theme="dark"\] \.reveal\s*\{[^}]*transform:\s*none;/s);
assert.match(css, /:root\[data-theme="dark"\] \.hero-visual\.reveal,[\s\S]*?animation:\s*none\s*!important;/);

// The application image is intentionally not faked while generation is unavailable.
const contactSection = html.split('<section class="section contact-section" id="contact">')[1].split('</section>')[0];
assert.ok(contactSection, 'application/contact section exists');
assert.ok(!/<img\b/i.test(contactSection), 'no unrelated placeholder image is inserted into the application section');

assert.ok(serviceWorker.includes("startum-public-v2"), 'theme-asset cache version is advanced');
assert.ok(serviceWorker.includes("'./assets/images/startum-dark-hero.webp'"));
assert.ok(serviceWorker.includes("'./assets/images/startum-day-hero.webp'"));

console.log('STARTUM theme image, locale coverage and scroll-stability contract: PASS');
