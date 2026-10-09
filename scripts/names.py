"""Список полных ФИО для реестра нотариата: фамилия + имя × отчества по словарю имён отцов.

Запуск:
  python3 names.py --surname Смирнова --name Мария [--female|--male] [--extra-fathers Юхо,Матти]
  python3 names.py --surname Корхонен --name Анна --female --patronymics-file свои.txt
Пол угадывается по окончанию фамилии (-ова/-ева/-ёва/-ина/-ына/-ая/-яя — женский,
-ов/-ев/-ёв/-ин/-ын/-ий/-ой/-ый — мужской); у несклоняемых фамилий (Шевченко,
Корхонен, Дурново) пол обязателен. --patronymics-file — свои отчества построчно,
без автоматического образования. Варианты е/ё строятся по каждой части отдельно.
Счётчик базовых имён и итоговых строк печатается в stderr.
"""
import argparse
import itertools
import json
import sys

FATHERS = """Александр Алексей Анатолий Андрей Антип Антон Аркадий Арсений Афанасий Борис Вавила
Валентин Валерий Василий Виктор Виталий Владимир Всеволод Гавриил Геннадий Георгий Герасим Григорий
Даниил Данил Демьян Денис Дмитрий Евгений Евдоким Евсей Егор Емельян Ермолай Ефим Захар Иван
Игнат Игнатий Илларион Илья Иона Иосиф Кирилл Климент Константин Кузьма Лаврентий Лев Леонид
Леонтий Логин Лука Макар Максим Матвей Мина Митрофан Михаил Назар Никанор Никифор Никита Николай
Олег Осип Павел Пантелей Пётр Платон Прокопий Прохор Роман Савва Савелий Семён Сергей Сидор
Спиридон Степан Тимофей Тихон Трофим Устин Фёдор Феодор Филипп Фока Фома Фрол Харитон Юрий Яков""".split()

IRREGULAR = {
    "Илья": (["Ильич"], ["Ильинична"]),
    "Лука": (["Лукич"], ["Лукинична", "Лукична"]),
    "Кузьма": (["Кузьмич"], ["Кузьминична"]),
    "Фома": (["Фомич"], ["Фоминична"]),
    "Фока": (["Фокич"], ["Фокична"]),
    "Никита": (["Никитич"], ["Никитична"]),
    "Савва": (["Саввич"], ["Саввична"]),
    "Мина": (["Минич"], ["Минична"]),
    "Иона": (["Ионович"], ["Ионовна"]),
    "Вавила": (["Вавилович"], ["Вавиловна"]),
    "Яков": (["Яковлевич"], ["Яковлевна"]),
    "Пётр": (["Петрович"], ["Петровна"]),
    "Павел": (["Павлович"], ["Павловна"]),
    "Лев": (["Львович"], ["Львовна"]),
    "Гавриил": (["Гаврилович"], ["Гавриловна"]),
    "Даниил": (["Даниилович", "Данилович"], ["Данииловна", "Даниловна"]),
}

VOWELS = set("аеёиоуыэюя")
FEMALE_ENDINGS = ("ова", "ева", "ёва", "ина", "ына", "ая", "яя")
MALE_ENDINGS = ("ов", "ев", "ёв", "ин", "ын", "ий", "ой", "ый")


def patronymics(name, female):
    if name in IRREGULAR:
        return IRREGULAR[name][female]
    if name.endswith(("а", "я")):
        raise ValueError(f"нет правила для имени на -а/-я: {name} — добавь его в IRREGULAR или --patronymics-file")
    if name.endswith("ий"):
        stem = name[:-2]
        cluster = len(stem) >= 2 and stem[-1] not in VOWELS and stem[-2] not in VOWELS
        endings = ["иевна"] if cluster else ["ьевна", "иевна"]
        if not female:
            endings = [e[:-2] + "ич" for e in endings]
        return [stem + e for e in endings]
    if name.endswith(("ей", "ай")):
        return [name[:-1] + ("евна" if female else "евич")]
    return [name + ("овна" if female else "ович")]


def yo_variants(part):
    return list(dict.fromkeys([part, part.replace("ё", "е").replace("Ё", "Е")]))


def guess_female(surname):
    s = surname.casefold()
    if s.endswith(FEMALE_ENDINGS):
        return True
    if s.endswith(MALE_ENDINGS):
        return False
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--surname", required=True)
    ap.add_argument("--name", required=True)
    sex = ap.add_mutually_exclusive_group()
    sex.add_argument("--female", action="store_true")
    sex.add_argument("--male", action="store_true")
    ap.add_argument("--extra-fathers", default="", help="имена отцов через запятую, сверх словаря")
    ap.add_argument("--patronymics-file", help="готовые отчества построчно, вместо словаря")
    args = ap.parse_args()

    female = True if args.female else False if args.male else guess_female(args.surname)
    if female is None:
        ap.error(f"по фамилии «{args.surname}» пол не определить — укажи --female или --male")

    if args.patronymics_file:
        with open(args.patronymics_file, encoding="utf-8") as fh:
            pats = [line.strip() for line in fh if line.strip()]
        base = len(pats)
    else:
        fathers = list(dict.fromkeys(FATHERS + [f.strip() for f in args.extra_fathers.split(",") if f.strip()]))
        base = len(fathers)
        pats = []
        for father in fathers:
            try:
                pats += patronymics(father, female)
            except ValueError as exc:
                print("пропуск:", exc, file=sys.stderr)

    out = []
    for pat in dict.fromkeys(pats):
        for s, n, p in itertools.product(yo_variants(args.surname), yo_variants(args.name), yo_variants(pat)):
            out.append(f"{s} {n} {p}")
    out = list(dict.fromkeys(out))
    print(f"{base} имён отцов → {len(out)} ФИО", file=sys.stderr)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
