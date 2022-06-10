import io

import bs4
import regex
import requests
import cloudscraper

from PIL import Image

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
        print("Nothing's found")
        return

    search_result = search.find("div", {"id": "sku_0"}).find("a")

    medicine_name = search_result["title"]
    medicine_page_link = 'https://tabletki.ua' + search_result["href"]
    medicine_photo_link = search_result.find("img")["src"]

    medicine_photo = requests.get(medicine_photo_link).content

    image = Image.open(io.BytesIO(medicine_photo))
    image.show()

    medicine_page = scraper.get(medicine_page_link)

    medicine = bs4.BeautifulSoup(medicine_page.text, "html.parser")

    medicine_active_ingredient = medicine.find("div", {"id": "instr_cont_0"}).find("p").text \
        .split(":")[-1].strip().strip(";").capitalize()

    medicine_pharmgroup = medicine.find("div", {"id": "instr_cont_2"}).find("p").text

    print("Name:", medicine_name)
    print("Active ingredient:", medicine_active_ingredient)
    print("Pharmacotherapeutic group:", medicine_pharmgroup)


find_info('ibuprofene')
