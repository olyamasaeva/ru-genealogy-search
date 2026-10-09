const {chromium} = require('playwright');
const queries = JSON.parse(process.argv[2]);
const filter = new RegExp(process.argv[3] || '.', 'i');
const PROXY = process.env.PW_PROXY;
(async () => {
  const browser = await chromium.launch(PROXY ? {proxy: {server: PROXY}} : {});
  const page = await (await browser.newContext({locale: 'ru-RU'})).newPage();
  for (const [f, n, s] of queries) {
    const url = 'https://obd-memorial.ru/html/search.htm?f=' + encodeURIComponent(f) + '&n=' + encodeURIComponent(n || '') + '&s=' + encodeURIComponent(s || '');
    await page.goto(url, {waitUntil: 'domcontentloaded', timeout: 90000});
    await page.waitForTimeout(12000);
    const rows = await page.evaluate(() => [...document.querySelectorAll('.search-result')].map(r => r.innerText.replace(/\s+/g, ' ').trim()));
    const loaded = await page.evaluate(() => /Найдено|результат|ничего не найдено/i.test(document.body.innerText));
    const status = !loaded && !rows.length ? 'parse_error: страница выдачи не распознана' : rows.length >= 20 ? 'truncated: только первая страница, сузь запрос именем и отчеством' : 'complete';
    console.log('==', f, n || '', s || '', rows.length, 'rows,', status);
    rows.filter(r => filter.test(r)).forEach(r => console.log(r));
    await page.waitForTimeout(3000);
  }
  await browser.close();
})();
