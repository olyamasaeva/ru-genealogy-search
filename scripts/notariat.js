const {chromium} = require('playwright');

const names = JSON.parse(process.argv[2]);
const filter = new RegExp(process.argv[3] || '.', 'i');
const PAUSE_MS = 3500;
const MAX_RETRIES = 3;
const PROXY = process.env.PW_PROXY;

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function query(page, name) {
  return page.evaluate(async n => {
    const token = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';
    const r = await fetch('/api/probate-cases', {method: 'POST',
      headers: {'Content-Type': 'application/json', 'x-csrftoken': token, 'x-requested-with': 'XMLHttpRequest'},
      body: JSON.stringify({name: n, birth_date: 'NULL', death_date: 'NULL'})});
    return {status: r.status, retryAfter: r.headers.get('retry-after'), text: await r.text()};
  }, name);
}

(async () => {
  const browser = await chromium.launch(PROXY ? {proxy: {server: PROXY}} : {});
  const page = await (await browser.newContext({locale: 'ru-RU'})).newPage();
  await page.goto('https://notariat.ru/ru-ru/help/probate-cases/', {waitUntil: 'domcontentloaded', timeout: 90000});
  await sleep(5000);
  let scanned = 0;
  let excluded = 0;
  let done = 0;
  try {
    for (const name of names) {
      let res;
      for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
        res = await query(page, name);
        if (res.status !== 429) break;
        const wait = (parseInt(res.retryAfter, 10) || 60) * 1000;
        console.log('429, жду', wait / 1000, 'с');
        await sleep(wait);
      }
      if (res.status === 403 || /captcha|капч/i.test(res.text.slice(0, 2000))) {
        console.log('STOP: сайт ответил', res.status, '— похоже на блокировку или капчу, прогон остановлен');
        break;
      }
      if (res.status !== 200) {
        console.log('ERR', name, res.status);
      } else {
        const records = JSON.parse(res.text).records || [];
        scanned += records.length;
        for (const x of records) {
          const place = [x.Address, x.DistrictName, x.ChamberName].join(' ');
          const line = [x.Fio, x.BirthDate, x.DeathDate, x.Address, x.DistrictName, x.ChamberName, x.CaseNumber].join(' | ');
          if (filter.test(place)) console.log('HIT', line); else excluded += 1;
        }
      }
      done += 1;
      await sleep(PAUSE_MS);
    }
  } finally {
    console.log('done', done, 'of', names.length, 'queries,', scanned, 'records scanned,', excluded, 'excluded by place filter');
    await browser.close();
  }
})();
