const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const html = fs.readFileSync('frontend/index.html', 'utf8');
const js = fs.readFileSync('frontend/script.js', 'utf8');
const css = fs.readFileSync('frontend/premium-experience.css', 'utf8');
const config = fs.readFileSync('frontend/startum.config.js', 'utf8');

// The official Telegram channel is linked only from footer social networks.
const footer = html.split('<footer class="footer">')[1].split('</footer>')[0];
const socialBlock = footer.split('<div class="footer-social">')[1].split('</div>')[0];
assert.ok(socialBlock.includes('https://t.me/StartumEducation'));
assert.ok(!html.split('<header')[1]?.split('</header>')[0]?.includes('t.me/'));
assert.ok(!html.includes('telegramExperience'));
assert.ok(!js.includes('https://t.me/StartumEducation'));
assert.ok(!html.includes('telegramExperience'));
assert.ok(!html.includes('class="contact-note"'));
assert.ok(!html.includes('contact.note'));
assert.ok(!config.includes('botUsername:'));

// Dark Mode uses its separately integrated generated image; the protected original remains on disk.
assert.ok(js.includes('"assets/images/startum-dark-hero.webp"'));
assert.ok(!js.includes('"assets/images/startum-aeline-student.jpg"'));
assert.ok(!html.includes('hero-complement-image'));
assert.ok(!html.includes('learning-world'));
assert.ok(!html.includes('class="hero-tag'));
assert.ok(!html.includes('class="orbit'));
assert.ok(!html.includes('tilt-card'));
assert.ok(!js.includes('const tilt = $(".tilt-card")'));
assert.ok(!css.includes('.learning-world'));
assert.ok(css.includes(':root[data-theme="dark"] .hero #heroThemeImage'));
assert.ok(css.includes('object-fit: contain'));

// Course modal action stays on the page and routes to the application form.
assert.ok(/href="#contact" class="btn btn-mint" data-course-modal-enroll/.test(html));
assert.ok(!js.includes('window.open(link, "_blank", "noopener")'));
assert.ok(js.includes('closeLayer($("#courseModal"))'));

// Internal schedule notes are removed. The daily frequency is shown without
// guessing a two-hour slot for Russian or the non-Monday English rows.
for (const obsolete of ['schedule.sample', 'schedule.languageNote', 'schedule-note']) {
  assert.ok(!html.includes(obsolete));
  assert.ok(!js.includes(obsolete));
}
assert.ok(js.includes('["Har kuni", "Rus tili", ""]'));
assert.ok(js.includes('["Har kuni", "Ingliz tili", ""]'));
assert.ok(js.includes('["15:00–16:20", "English", "STARTUM guruhi"]'));
assert.ok(js.includes('["16:00–18:00", "Nemis tili", "Dush / Chor / Juma"]'));

// Application form accessible validation and localized server errors.
for (const id of ['nameError', 'phoneError', 'telegramError', 'courseError', 'messageError']) {
  assert.ok(html.includes(`id="${id}"`), `${id} must exist`);
}
assert.ok(html.includes('aria-describedby="nameError"'));
assert.ok(html.includes('aria-describedby="phoneError"'));
assert.ok(html.includes('aria-describedby="telegramHelp telegramError"'));
assert.ok(html.includes('aria-describedby="courseError"'));
assert.ok(html.includes('aria-describedby="messageError"'));
assert.ok(css.includes('.lead-form .is-invalid'));
for (const key of ['form.duplicate', 'form.unprocessable', 'form.rateLimit', 'form.timeout', 'form.network', 'form.server']) {
  assert.ok((js.match(new RegExp(`"${key}"`, 'g')) || []).length >= 3, `${key} must be translated in uz/ru/en`);
}
assert.ok(html.includes('data-i18n="form.submit">Arizani yuborish'));
assert.ok(js.includes('response.status === 422') || js.includes('status === 422'));
assert.ok(js.includes('status === 429'));
assert.ok(js.includes('status === 409'));
assert.ok(js.includes('setFormStatus(t("form.success"), "success")'));

// Mobile/tablet responsive rules, compact cards and accessible touch targets.
for (const breakpoint of ['max-width: 960px', 'max-width: 680px', 'max-width: 430px', 'max-width: 359px']) {
  assert.ok(css.includes(breakpoint), `responsive breakpoint ${breakpoint} exists`);
}
assert.ok(css.includes('grid-template-columns: minmax(0, 1fr)'));
assert.ok(css.includes('min-height: 48px'));
assert.ok(css.includes('safe-area-inset-top'));
assert.ok(css.includes('prefers-reduced-motion: reduce'));
assert.ok(css.includes('.brand-strip-track { animation: none'));

console.log('STARTUM final mobile UX/accessibility acceptance: PASS');
