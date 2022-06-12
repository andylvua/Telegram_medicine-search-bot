import json

import bs4
import regex
import requests
import cloudscraper

from googletrans import Translator


def is_cyrillic(query_string):
    if regex.search(r'\p{IsCyrillic}', query_string):
        return True
    else:
        return False


def translate(query_string):
    translator = Translator()
    return translator.translate(query_string, dest='uk').text


def find_info(query_string):
    if not is_cyrillic(query_string):
        query_string = translate(query_string)

    url = f'https://tabletki.ua/uk/search/{query_string}/'

    scraper = cloudscraper.create_scraper()
    request_result = scraper.get(url)

    search = bs4.BeautifulSoup(request_result.text, "html.parser")

    availability_check = search.find("div", {"class": "page-not-found__message"})

    if availability_check:
        return

    search_result = search.find("div", {"id": "sku_0"}).find("a")

    medicine_name = search_result["title"]
    medicine_page_link = 'https://tabletki.ua' + search_result["href"]
    medicine_photo_link = search_result.find("img")["src"]

    medicine_photo = requests.get(medicine_photo_link).content

    # image = Image.open(io.BytesIO(medicine_photo))
    # image.show()

    medicine_page = scraper.get(medicine_page_link)

    medicine = bs4.BeautifulSoup(medicine_page.text, "html.parser")

    try:
        medicine_active_ingredient = medicine.find("div", {"id": "instr_cont_0"}).find("p").text \
            .split(":")[-1].strip().strip(";").capitalize()
    except AttributeError:
        medicine_active_ingredient = None

    try:
        medicine_pharmgroup = medicine.find("div", {"id": "instr_cont_2"}).find("p").text.strip()
    except AttributeError:
        medicine_pharmgroup = None

    try:
        medicine_indication = medicine.find("div", {"id": "instr_cont_4"}).text.split(".")[0].strip()
    except AttributeError:
        medicine_indication = None

    try:
        medicine_contraindication = medicine.find("div", {"id": "instr_cont_5"}).text.split(".")[0].strip()
    except AttributeError:
        medicine_contraindication = None

    info = {
        "name": medicine_name,
        "active_ingredient": medicine_active_ingredient,
        "pharmgroup": medicine_pharmgroup,
        "indication": medicine_indication,
        "contrandication": medicine_contraindication
    }
    return info


def print_progress_bar(iteration, total, prefix='', suffix='', decimals=1, length=100, fill='█', print_end=""):
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filled_length = int(length * iteration // total)
    bar = fill * filled_length + '-' * (length - filled_length)
    print(f'\r{prefix} |{bar}| {percent}% {suffix}', end=print_end)

    if iteration == total:
        print()


with open('names.txt') as file:
    names_lines = file.readlines()

info_list = list()

print_progress_bar(0, len(names_lines), prefix='Progress:', suffix='Complete', length=50)

found = 0
for i, name in enumerate(names_lines):
    data = find_info(name)

    if data and data["active_ingredient"]:
        medicine_info = {
            "Назва": data["name"],
            "Діюча речовина": data["active_ingredient"],
            "Фармгрупа": data["pharmgroup"],
            "Показання": data["indication"],
            "Протипоказання": data["contrandication"]
        }
        found += 1
        info_list.append(medicine_info)

    print_progress_bar(i + 1, len(names_lines), prefix='Progress:', suffix='Complete', length=50)

with open("medicine_info.json", "w", encoding='utf-8') as final:
    json.dump(info_list, final, sort_keys=False, ensure_ascii=False, indent=4)

print(f"Done. Found {found} out of {len(names_lines)} medicines")
