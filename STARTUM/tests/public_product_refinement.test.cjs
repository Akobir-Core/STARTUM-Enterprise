const assert = require('node:assert/strict');
const fs = require('node:fs');
const html = fs.readFileSync('frontend/index.html', 'utf8');
const js = fs.readFileSync('frontend/script.js', 'utf8');
const css = fs.readFileSync('frontend/premium-experience.css', 'utf8');
const bot = fs.readFileSync('backend/handlers/user.py', 'utf8');
const config = fs.readFileSync('frontend/startum.config.js', 'utf8');

for (const id of ['learningHub', 'applicationTracker', 'reviews', 'courseFinderForm', 'studyPlanPanel']) {
  assert.ok(!html.includes(`id="${id}"`), `${id} must be removed from the public homepage`);
}
assert.ok(html.includes('id="fit"'), 'The distinct 5-step STARTUM Navigator remains available');
assert.ok(!html.includes('id="telegramExperience"'), 'public Telegram section must be removed');
assert.ok(!html.includes('href="#telegramExperience"'), 'public Telegram navigation must be removed');
const footer = html.split('<footer class="footer">')[1].split('</footer>')[0];
const socialBlock = footer.split('<div class="footer-social">')[1].split('</div>')[0];
assert.ok(socialBlock.includes('https://t.me/StartumEducation'), 'official Telegram channel must appear in footer socials');
assert.ok(!html.split('<header')[1]?.split('</header>')[0]?.includes('t.me/'), 'Telegram must not appear in top navigation');
assert.ok(!footer.includes('telegramExperience'), 'no standalone Telegram promo section');
assert.ok(!html.includes('id="botQuickApply"'), 'contact Telegram shortcut must be removed');
assert.ok(!js.includes('function startumBotUrl(course = "")'), 'public course enrollment must not redirect to Telegram');
assert.ok(html.includes('href="#contact" class="btn btn-mint" data-course-modal-enroll'), 'course modal action links to the application form');
assert.ok(!js.includes('function setupTelegramSection()'));
assert.ok(!js.includes('function setupLearningWorld()'), 'overlapping interactive 3D hero layer is removed');
assert.ok(js.includes('assets/images/nemis-tili-ustoz.png'));
assert.ok(!html.includes('assets/images/startum-dark-classroom.webp'), 'duplicate dark hero photo overlay is removed');
assert.ok(js.includes('assets/images/startum-dark-hero.webp'), 'Dark Mode uses the dedicated generated hero asset');
assert.ok(!html.includes('id="telegramExperience"')); 
assert.ok(!config.includes('botUsername:'), 'frontend has no Telegram channel/bot redirect config');
assert.ok(bot.includes('if payload == "explore":'));
assert.ok(bot.includes('if payload == "apply":'));
assert.ok(bot.includes('await state.set_state(RegistrationState.full_name)'));
assert.ok(!css.includes('.learning-world'), 'unused 3D hero styles are cleaned up');
assert.ok(css.includes('.hero-facts'));
assert.ok(css.includes('@media (max-width: 359px)'));
assert.ok(css.includes('grid-template-columns: repeat(2, minmax(0, 1fr))'));
assert.ok(!css.includes('.telegram-workflow-card'));
console.log('STARTUM public product refinement: PASS');
