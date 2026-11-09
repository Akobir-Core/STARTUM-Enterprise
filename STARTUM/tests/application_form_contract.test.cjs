const assert = require('node:assert/strict');
const fs = require('node:fs');
const html = fs.readFileSync('frontend/index.html', 'utf8');
const js = fs.readFileSync('frontend/script.js', 'utf8');
const css = fs.readFileSync('frontend/premium-experience.css', 'utf8');
const api = fs.readFileSync('backend/api.py', 'utf8');
const db = fs.readFileSync('backend/database/db.py', 'utf8');
const admin = fs.readFileSync('backend/admin_panel/admin.js', 'utf8');

const form = html.split('<form class="lead-form" id="leadForm"')[1].split('</form>')[0];
for (const retiredField of ['name="level"', 'name="preferred_time"']) {
  assert.ok(!form.includes(retiredField), `${retiredField} must not be shown in the public form`);
}
for (const retiredKey of ['form.level', 'form.preferredTime', 'form.chooseOptional', 'form.timeMorning']) {
  assert.ok(!js.includes(`"${retiredKey}"`), `${retiredKey} must not remain as unused public form copy`);
}
assert.ok(!js.includes('preferred_time:'));
assert.ok(!js.includes('level: (() =>'));
// The API keeps optional legacy input fields and DB columns so old applications remain compatible.
assert.match(api, /level:\s*str\s*=\s*Field\(default="", max_length=60\)/);
assert.match(api, /preferred_time:\s*str\s*=\s*Field\(default="", max_length=120\)/);
assert.match(db, /INSERT INTO web_applications\([^\n]*level,preferred_time,message/);
assert.ok(admin.includes('optionalApplicationDetails'), 'old application records retain optional details when present');
assert.ok(!admin.includes('Uchrashuv vaqti</span><b>${escapeHTML(item.preferred_time ||'), 'empty preferred-time label is no longer rendered');

// The contact section remains functional, but its pseudo-step eyebrow is removed.
const contact = html.split('<section class="section contact-section" id="contact">')[1].split('</section>')[0];
assert.ok(!contact.includes('section.contact'));
assert.ok(contact.includes('data-contact-phone-card'));
assert.ok(!html.includes('contact-visual'));

// Theme and geometry are explicitly invariant for hero and teacher layouts.
assert.ok(css.includes('theme-invariant geometry and mobile overflow safety'));
assert.match(css, /\.teacher-photo,[\s\S]*?aspect-ratio: 4 \/ 5/);
assert.match(css, /\.teacher-photo img\.teacher-placeholder-image[\s\S]*?filter: none/);
assert.match(css, /:root\[data-theme="light"\] \.special-card\s*\{[\s\S]*?background: #ffffff/);
assert.match(css, /:root\[data-theme="dark"\] \.special-card\s*\{[\s\S]*?background: #10343c/);
assert.match(css, /\.hero \.hero-frame,[\s\S]*?aspect-ratio: 16 \/ 9/);
for (const locale of ['ru', 'en']) assert.ok(css.includes(`data-locale="${locale}"`));

// Header buttons remain theme-token based and the form retains usable control styles.
for (const token of [
  '--premium-nav-hover-bg', '--premium-nav-hover-text',
  '--premium-nav-primary-bg', '--premium-nav-primary-hover-bg',
  '--premium-nav-primary-text', '--premium-nav-primary-hover-text'
]) assert.ok(css.includes(`var(${token})`), `${token} must be consumed`);
assert.match(css, /\.lead-form input:not\(\[type="hidden"\]\), \.lead-form textarea, \.lead-form \.select-btn/);
assert.match(css, /#contact \.lead-form \.form-footer \.btn/);

console.log('STARTUM simplified application form + theme/layout contract: PASS');
