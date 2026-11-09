const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('frontend/script.js', 'utf8');
const dataStart = source.indexOf('const schedule = {');
const dataEnd = source.indexOf('\nconst systemData = {', dataStart);
const renderStart = source.indexOf('function renderSchedule() {');
const renderEnd = source.indexOf('\nfunction renderFaq()', renderStart);
assert.ok(dataStart >= 0 && dataEnd > dataStart, 'schedule data block must exist');
assert.ok(renderStart >= 0 && renderEnd > renderStart, 'renderSchedule function must exist');

const sourceBlock = source.slice(dataStart, dataEnd);
const renderBlock = source.slice(renderStart, renderEnd);
const factorySource = `(() => {
  ${sourceBlock}
  let lang = 'uz';
  let dayKey = null;
  const elements = { '#dayTabs': { innerHTML: '' }, '#scheduleList': { innerHTML: '' } };
  const callbacks = {};
  const $ = (selector) => elements[selector];
  const $$ = (selector) => selector === '.day-tab'
    ? Object.keys(schedule[lang]).map((day) => ({
        dataset: { day },
        addEventListener: (_event, callback) => { callbacks[day] = callback; },
      }))
    : [];
  const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[ch]));
  ${renderBlock}
  return {
    render(locale, day) {
      lang = locale;
      dayKey = day;
      renderSchedule();
      return { html: elements['#scheduleList'].innerHTML, dayTabs: elements['#dayTabs'].innerHTML };
    },
    days(locale) { return Object.keys(schedule[locale]); },
  };
})()`;

const harness = vm.runInNewContext(factorySource, {});
const expected = {
  uz: { korean: 'Koreys tili', russian: 'Rus tili', english: 'Ingliz tili', german: 'Nemis tili', days: ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba'] },
  ru: { korean: 'Корейский язык', russian: 'Русский язык', english: 'Английский язык', german: 'Немецкий язык', days: ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье'] },
  en: { korean: 'Korean', russian: 'Russian', english: 'English', german: 'German', days: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'] },
};

for (const [locale, labels] of Object.entries(expected)) {
  assert.deepEqual(Array.from(harness.days(locale)), labels.days);
  labels.days.forEach((day, index) => {
    const result = harness.render(locale, day).html;
    assert.ok(result.includes('14:00–16:00'), `${locale}/${day}: Korean time must be shown`);
    assert.ok(result.includes(labels.korean), `${locale}/${day}: Korean must be shown`);
    assert.ok(result.includes(locale === 'ru' ? 'Ежедневно' : locale === 'en' ? 'Every day' : 'Har kuni'), `${locale}/${day}: daily language frequency must be shown without inventing a slot`);
    assert.ok(result.includes(labels.russian), `${locale}/${day}: Russian must be shown`);
    assert.ok(result.includes(labels.english), `${locale}/${day}: English must be shown`);
    if (index === 0) assert.ok(result.includes('15:00–16:20'), `${locale}/${day}: preserve the existing Monday English slot`);
    else assert.ok(result.includes(locale === 'ru' ? 'Ежедневно' : locale === 'en' ? 'Every day' : 'Har kuni'), `${locale}/${day}: preserve daily English frequency without inventing a time`);
    const shouldHaveGerman = [0, 2, 4].includes(index);
    assert.equal(result.includes(labels.german), shouldHaveGerman, `${locale}/${day}: German must only appear Monday/Wednesday/Friday`);
    assert.equal((result.match(new RegExp(`schedule-course\">${labels.english.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}<\\/div>`, 'g')) || []).length, 1, `${locale}/${day}: no duplicate English row`);
  });
}

for (const localeText of [
  'schedule.languageNote',
  'schedule.sample',
  'Guruh vaqti tasdiqlanmagan',
  'Group slot not confirmed',
  'Время группы не подтверждено',
]) {
  assert.ok(!source.includes(localeText), `internal timetable note must be removed: ${localeText}`);
}

console.log('STARTUM timetable rendering: PASS (3 languages × 7 days)');
