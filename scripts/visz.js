const {chromium} = require('playwright');
const [mode, ...queries] = process.argv.slice(2);
const field = mode === 'memo' ? '#memo' : '#lname';
const PROXY = process.env.PW_PROXY;
(async () => {
  const browser = await chromium.launch(PROXY ? {proxy: {server: PROXY}} : {});
  const page = await (await browser.newContext({locale: 'ru-RU'})).newPage();
  for (const q of queries) {
    await page.goto('https://visz.nlr.ru/person/', {waitUntil: 'domcontentloaded', timeout: 60000});
    await page.waitForTimeout(3000);
    await page.evaluate(([sel, value]) => { document.querySelector(sel).value = value; form_search.submit(); }, [field, q]);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(5000);
    const text = await page.evaluate(() => document.body.innerText);
    const start = text.indexOf('Количество найденных записей');
    console.log('==', mode, q);
    if (start < 0) { console.log('parse_error: страница выдачи не распознана'); continue; }
    console.log(text.slice(start, text.indexOf('наверх', start)).replace(/\nПодробнее\.\.\./g, '').trim());
    await page.waitForTimeout(2000);
  }
  await browser.close();
})();
