import json

import bs4
import regex
import requests
import cloudscraper

from googletrans import Translator


def is_cyrillic(query_string: str) -> bool:
    """
    The is_cyrillic function checks if the query string contains any Cyrillic characters.
    If it does, True is returned. Otherwise, False is returned.

    :param query_string: Check if the query string contains any cyrillic characters
    :return: True if the query_string contains any cyrillic characters, and false otherwise
    """
    if regex.search(r'\p{IsCyrillic}', query_string):
        return True
    else:
        return False


def translate(query_string: str) -> str:
    """
    Takes a string as input and returns the translated string in ukrainian.

    :param query_string: Pass the string to be translated as a parameter
    :return: A translation of the query string
    """
    translator = Translator()
    return translator.translate(query_string, dest='uk').text


def find_info(query_string: str) -> dict or None:
    """
    Takes a string as an argument parses website and returns a dictionary with the following keys:
        name - medicine name
        active_ingredient - active ingredient of the medicine
        pharmgroup - pharmacological group of the medicine (e.g., analgesics, antiseptics)
        indication - medical indication

    :param query_string: Pass the name of the medicine to find
    :return: A dictionary with the following keys: name, active_ingredient, pharmgroup, indication and contraindication
    """
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


def print_progress_bar(iteration, total, prefix='', suffix='', decimals=1, length=100, fill='█', print_end="") -> None:
    """
    The print_progress_bar function prints a progress bar to the console.

    Args:
        iteration (int): The current iteration.
        total (int): The total number of iterations before completion.

        prefix (str, optional): A string that will be prepended to the progress bar and any
        associated text during printing.

    :param iteration: Keep track of the current iteration
    :param total: Determine the total number of iterations necessary to fill the bar
    :param prefix: Print a string before the progress bar
    :param suffix: Print a message after the progress bar
    :param decimals: Specify the number of decimal places to display in the output
    :param length: Determine the length of the progress bar
    :param fill: Determine the character used to fill the bar
    :param print_end: Prevent the print function from printing a new line after each iteration
    :return: None
    """
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