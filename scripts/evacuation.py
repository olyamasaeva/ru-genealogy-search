"""База эвакуированных из Ленинграда (ЦГА СПб): поиск по ФИО, вывод строк таблицы.

Запуск: python3 evacuation.py [--direct] [--max-pages N] "Фамилия Имя" [ещё ФИО ...]
--direct — без прокси из окружения: сайт часто не отвечает через VPN.
Ищет по подстроке: годится и «Имя Отчество» без фамилии. По умолчанию не больше 20 страниц по 25 строк.
"""
import html
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://evacuation.spbarchives.ru/"
OPENER = urllib.request.build_opener()


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return OPENER.open(req, timeout=60).read().decode("utf-8", "replace")


def cells(row):
    return [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip()
            for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]


def search(fio, max_pages):
    page = 1
    while page <= max_pages:
        query = urllib.parse.urlencode({"fio": fio, "pageNumber": page, "recordsPerPage": 25})
        text = fetch(BASE + "table?" + query)
        rows = re.findall(r'<tr class="clickable-row" data-href="\./card\?cardRecordId=(\d+)[^"]*"[^>]*>(.*?)</tr>', text, re.S)
        for link, row in rows:
            print(" | ".join(cells(row)), "|", BASE + "card?cardRecordId=" + link)
        if len(rows) < 25:
            if page == 1 and not rows and "clickable-row" not in text and "table" not in text:
                print("parse_error: страница выдачи не распознана")
            return
        page += 1
        time.sleep(2)
    print(f"truncated: показано {max_pages} стр. по 25, дальше не смотрел; увеличь --max-pages или уточни ФИО")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--direct" in args:
        args.remove("--direct")
        OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    limit = 20
    if args[:1] == ["--max-pages"]:
        limit, args = int(args[1]), args[2:]
    for name in args:
        print("==", name)
        try:
            search(name, limit)
        except urllib.error.URLError as exc:
            sys.exit(f"сайт не ответил ({exc.reason}); если включён VPN или прокси, повтори с --direct")
