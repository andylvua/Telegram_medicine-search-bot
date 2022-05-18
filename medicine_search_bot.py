"""
Author: Andrew Yaroshevych
Version: 2.4.0
"""
from functools import wraps

from telegram import Update, ReplyKeyboardRemove, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, Filters, CallbackContext, CommandHandler, MessageHandler, CallbackQueryHandler, \
    ConversationHandler

from PIL import Image
from pyzbar.pyzbar import decode
from email.message import EmailMessage

import os
import io
import logging
import smtplib
import configparser

import requests
import bs4
import re

from pymongo import MongoClient

logging.basicConfig(
    format='Time: %(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

config = configparser.ConfigParser()
config.read("config.ini")

cluster = MongoClient(config['Database']['cluster'])

db = cluster.TestBotDatabase
collection = db.TestBotCollection

# Conversation states
REVIEW = 1
REPORT = 1
SEARCH = 1

MAIN_REPLY_KEYBOARD = [['Сканувати', 'Пошук'], ['Інструкції', 'Налаштування', 'Надіслати відгук']]

UNDER_MAINTENANCE = False


def under_maintenance(func):
    @wraps(func)
    def wrapped(update, context, *args, **kwargs):
        user_id = int(update.effective_user.id)

        if user_id != 483571608 and UNDER_MAINTENANCE is True:
            logger.info("Unauthorized maintenance access denied ID: {}".format(user_id))

            update.message.reply_text(
                "❌ *The bot is under maintenance*",
                parse_mode="MarkdownV2"
            )
            return
        else:
            logger.info("Maintenance access granted")

        return func(update, context, *args, **kwargs)
    return wrapped


@under_maintenance
def start_handler(update: Update, context: CallbackContext) -> None:

    print(context.user_data)

    user = update.message.from_user
    logger.info("%s: %s", user.first_name, update.message.text)

    reply_keyboard = [['Сканувати', 'Інструкції', 'Пошук'], ['Налаштування', 'Про мене', 'Надіслати відгук']]

    update.message.reply_text(
        '🇺🇦 '
        '*Привіт\! Я бот для пошуку медикаментів\.*'
        '\nЯ допоможу Вам знайти коротку інформацію про ліки\.'
        '\n\nОберіть опцію, будь ласка\. Якщо ви користуєтесь ботом вперше \- рекомендую подивитись розділ "Інструкції"'
        '\n\nЦе можна зробити будь\-коли за допомогою команди */help*',
        parse_mode='MarkdownV2',
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, resize_keyboard=True, input_field_placeholder='Оберіть опцію'
        ),
    )


@under_maintenance
def scan_handler(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    logger.info("%s: %s", user.first_name, update.message.text)

    reply_keyboard = [['Відмінити сканування']]

    update.message.reply_text(
        'Будь ласка, надішліть мені фото пакування, де я можу *чітко* побачити штрихкод\.',
        parse_mode='MarkdownV2',
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, resize_keyboard=True, input_field_placeholder='Надішліть фото'
        ),
    )


@under_maintenance
def end_scan_handler(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    logger.info("%s: %s", user.first_name, update.message.text)

    reply_keyboard = MAIN_REPLY_KEYBOARD

    update.message.reply_text(
        '☑️ Сканування завершено',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію'),
    )


@under_maintenance
def instructions_handler(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    logger.info("%s: %s", user.first_name, update.message.text)

    reply_keyboard = [['Зрозуміло!']]

    pic = 'resources/How_to_scan.png'
    update.message.reply_photo(open(pic, 'rb'),
                               caption='🔍 Щоб відсканувати штрихкод та отримати опис ліків \- надішліть мені фото '
                                       'пакування, де я можу *чітко* побачити штрихкод\.'
                                       '\n\n▶️ Почати сканування у будь\-який момент можна за допомогою команди */scan*'
                                       '\n\n✏️ Зверніть увагу, ви можете надсилати одразу декілька фотографій\.'
                                       '\n\n❗️ Переконайтесь, що фотографія *не розмита*, а штрихкод розташований '
                                       '*вертикально* або *горизонтально*\. '
                                       'Не фотографуйте надто далеко, та намагайтесь тримати камеру *паралельно* '
                                       'до упаковки\! '
                                       '\nЦе мінімізує кількість помилок та дозволить боту працювати коректно\.'
                                       '\n\n✅ Після сканування ви можете надсилати фото далі\. '
                                       '\nАби завершити сканування \- натисніть відповідну кнопку\.'
                                       '\n\n ↩️ Відмінити будь\-яку дію можна командою */cancel*'
                                       '\n\n ⚙️ За допомогою команди */settings* можна налаштувати функцію пошуку '
                                       'медикаменту у *Google*'
                                       '\n\n 💬 Ви можете викликати це повідомлення у будь\-який момент, '
                                       'надіславши команду */help*',
                               parse_mode='MarkdownV2',
                               reply_markup=ReplyKeyboardMarkup(
                                   reply_keyboard, one_time_keyboard=True, resize_keyboard=True,
                                   input_field_placeholder='Оберіть опцію'),
                               )


@under_maintenance
def goto_scan(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    logger.info("%s: %s", user.first_name, update.message.text)

    if update.message.text != 'Ще раз':
        update.message.reply_text(
            'Це добре😊 Можемо перейти до сканування.',
            reply_markup=ReplyKeyboardRemove(),
        )
    return scan_handler(update=update, context=context)


def db_check_availability(code_str) -> bool or None:
    try:
        logger.info("Database quired. Checking availability")
        if collection.count_documents({"code": code_str}) != 0:
            return True
        else:
            return False
    except Exception as e:
        logger.error(e)
        return


def retrieve_db_query(code_str) -> str or None:
    try:
        logger.info("Database quired. Retrieving info")
        query_result = collection.find_one({"code": code_str}, {"_id": 0})
        str_output = f"<b>Назва</b>: {query_result['name']} " \
                     f"\n<b>Діюча речовина</b>: {query_result['active_ingredient']} " \
                     f"\n<b>Опис</b>: {query_result['description']} "
        return str_output
    except Exception as e:
        logger.info(e)
        return


def retrieve_db_photo(code_str) -> Image or None:
    try:
        query_result = collection.find_one({"code": code_str}, {"_id": 0})
        logger.info("Database quired")

        if query_result['photo'] == b'':
            logger.info("Field 'photo' is empty")
            return

        logger.info("Retrieving photo")
        img = Image.open(io.BytesIO(query_result['photo']))
        return img
    except Exception as e:
        logger.info(e)
        return


# noinspection DuplicatedCode
@under_maintenance
def retrieve_results(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    logger.info("%s: Photo received", user.first_name)

    if update.message.photo:
        id_img = update.message.photo[-1].file_id
    else:
        return

    foto = context.bot.getFile(id_img)

    new_file = context.bot.get_file(foto.file_id)
    new_file.download('code.png')

    try:
        result = decode(Image.open('code.png'))
        code_str = result[0].data.decode("utf-8")
        link = 'https://www.google.com/search?q=' + code_str

        reply_keyboard = [['Завершити сканування', 'Повідомити про проблему']]

        if db_check_availability(code_str) and retrieve_db_photo(code_str) is not None:
            logger.info("The barcode is present in the database")
            img = retrieve_db_photo(code_str)
            img.save("retrieved_image.jpg")

            update.message.reply_photo(
                open("retrieved_image.jpg", 'rb'),
                parse_mode='HTML',
                reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                                 resize_keyboard=True,
                                                 input_field_placeholder='Продовжуйте'),
                caption='Ось відсканований штрихкод ✅:\n' + '<b>' + code_str + '</b>' + "\n\n" +
                        retrieve_db_query(code_str),
            )

            os.remove("retrieved_image.jpg")
        elif db_check_availability(code_str):
            update.message.reply_text(
                parse_mode='HTML',
                reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                                 resize_keyboard=True,
                                                 input_field_placeholder='Продовжуйте'),
                text='Ось відсканований штрихкод ✅:\n' + '<b>' + code_str + '</b>' + "\n\n" +
                     retrieve_db_query(code_str) + "\n\n⚠️ Фото відсутнє",
                quote=True
            )
        else:
            reply_keyboard = [['Завершити сканування']]

            update.message.reply_text(parse_mode='HTML',
                                      reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                                                       resize_keyboard=True,
                                                                       input_field_placeholder='Продовжуйте'),
                                      text='Штрих-код ' + '<b>' + code_str + '</b>' +
                                           ' на жаль відсутній у моїй базі даних ❌'
                                           '\n\nЯкщо ви хочете долучитись до наповнення бази даних - '
                                           'скористайтесь нашим другим ботом <b>@msb_database_bot</b>',
                                      quote=True)

        if context.user_data.setdefault("GOOGLE_SEARCH", "True") == "True":
            update.message.reply_text(parse_mode='HTML',
                                      reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                                                       resize_keyboard=True,
                                                                       input_field_placeholder='Продовжуйте'),
                                      text='<b>' + '\n\nЙмовірно це: ' + '</b>' + get_query_heading(code_str) +
                                           ' - (За результатами пошуку ' + f'<a href="{link}"><b>Google</b></a>' + ')',
                                      disable_web_page_preview=True)

        context.user_data["DRUG_CODE"] = code_str
    except IndexError as e:
        logger.info(e)

        reply_keyboard = [['Ще раз', 'Інструкції']]

        update.message.reply_text(text="*На жаль, сталася помилка ❌ *"
                                       "\nСпробуйте ще раз, або подивіться інструкції до сканування та "
                                       "переконайтесь, що робите все правильно\.",
                                  quote=True,
                                  parse_mode='MarkdownV2',
                                  reply_markup=ReplyKeyboardMarkup(
                                      reply_keyboard, one_time_keyboard=True, resize_keyboard=True,
                                      input_field_placeholder='Оберіть опцію'
                                  )),
    finally:
        os.remove("code.png")


def get_query_heading(barcode) -> str:
    url = 'https://google.com/search?q=' + barcode

    request_result = requests.get(url)
    soup = bs4.BeautifulSoup(request_result.text, "html.parser")

    heading_objects = soup.find_all('h3')
    first_heading = heading_objects[0]

    first_heading_formatted = re.sub(r"\([^()]*\)", "", first_heading.getText().split(' - ')[0]
                                     .replace(str(barcode), '')).lstrip().rstrip('.').rstrip()
    return first_heading_formatted


@under_maintenance
def file_warning(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    logger.info("%s: File warning", user.first_name)

    reply_keyboard = [['Ще раз']]

    update.message.reply_text(
        'Будь ласка, використовуйте *фотографію*, а не файл\.',
        parse_mode='MarkdownV2',
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, resize_keyboard=True, input_field_placeholder='Надішліть фото'
        ),
    )


@under_maintenance
def undefined_input(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    logger.info("%s: %s", user.first_name, update.message.text)

    reply_keyboard = MAIN_REPLY_KEYBOARD

    update.message.reply_text(
        'Я вас не розумію 🧐.\nОберіть, будь ласка, одну з доступних опцій',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію'),
    )


@under_maintenance
def cancel_operation(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    logger.info("%s: %s", user.first_name, update.message.text)

    reply_keyboard = MAIN_REPLY_KEYBOARD

    update.message.reply_text(
        '☑️ Гаразд, операцію скасовано',
        parse_mode='MarkdownV2',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію'),
    )


@under_maintenance
def tell_about(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    logger.info("%s: %s", user.first_name, update.message.text)

    reply_keyboard = [['Зрозуміло!']]

    pic = 'resources/MSB_Logo.png'
    update.message.reply_photo(open(pic, 'rb'),
                               'Слава Україні! 🇺🇦\n\n'
                               '🤖 Я - бот, створений командою студентів зі Львова.\n\n✅ Моє завдання - допомогти '
                               'волонтерам, що праwюють на '
                               'пункnах сортування гуманітарної допомоги. Я допоможу Вам знайти інформацію та короткий '
                               'опис про медичні '
                               'препарати за допомогою штрих-коду.'
                               '\n\n🥇 Це дозволить пришвидшити роботу, а також якість сортування медикаментів '
                               'для допомоги Збройним Силам України 💛💙',
                               reply_markup=ReplyKeyboardMarkup(
                                   reply_keyboard, one_time_keyboard=True, resize_keyboard=True),
                               )


@under_maintenance
def settings(update: Update, context: CallbackContext) -> None:
    """Sends a message with three inline buttons attached."""
    if context.user_data["GOOGLE_SEARCH"] == "True":
        keyboard = [
            [
                InlineKeyboardButton("Ввімкнено ✅", callback_data="True"),
                InlineKeyboardButton("Вимкнено", callback_data="False"),
            ]
        ]
    else:
        keyboard = [
            [
                InlineKeyboardButton("Ввімкнено", callback_data="True"),
                InlineKeyboardButton("Вимкнено ✅", callback_data="False"),
            ]
        ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text('*⚙️ Налаштування *'
                              '\n\nВивід результатів пошуку Google при скануванні:  ',
                              reply_markup=reply_markup,
                              parse_mode="MarkdownV2")


@under_maintenance
def google_search_set(update: Update, context: CallbackContext) -> None:
    """Parses the CallbackQuery and updates the message text."""
    query = update.callback_query

    query.answer()

    context.user_data["GOOGLE_SEARCH"] = query.data

    if context.user_data["GOOGLE_SEARCH"] == "True":
        keyboard = [
            [
                InlineKeyboardButton("Ввімкнено ✅", callback_data="True"),
                InlineKeyboardButton("Вимкнено", callback_data="False"),
            ]
        ]
    else:
        keyboard = [
            [
                InlineKeyboardButton("Ввімкнено", callback_data="True"),
                InlineKeyboardButton("Вимкнено ✅", callback_data="False"),
            ]
        ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    query.edit_message_text('*⚙️ Налаштування *'
                            '\n\nВивід результатів пошуку Google при скануванні:  ',
                            reply_markup=reply_markup,
                            parse_mode="MarkdownV2")


@under_maintenance
def start_review(update: Update, context: CallbackContext) -> int:
    reply_keyboard = [['Скасувати']]

    update.message.reply_text(
        text=f"💌 *Ваш відгук буде надіслано команді розробників*"
             "\n\nНапишіть, будь ласка, свій відгук",
        parse_mode="MarkdownV2",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder='Відгук')
    )
    return REVIEW


@under_maintenance
def send_review(update: Update, context: CallbackContext) -> ConversationHandler.END:
    review_msg = update.message.text
    user = update.message.from_user

    logger.info("User reviewed: %s", review_msg)

    reply_keyboard = MAIN_REPLY_KEYBOARD

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()

            address = config['Mail']['address']
            password = config['Mail']['password']

            smtp.login(address, password)

            msg = EmailMessage()

            msg['Subject'] = "User response for Telegram MSB"
            msg['From'] = address
            msg['To'] = address

            user_data = f"<br><br><br><b>User ID:</b> {update.effective_user.id}<br><b>User name:</b> {user.first_name}"
            message = review_msg + user_data

            content = \
                f"""<!DOCTYPE html>
                <html lang="en">
                <head>
                    <meta charset="UTF-8">
                    <title>User Response</title>
                </head>

                <link rel="preconnect" href="https://fonts.googleapis.com">
                <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
                <link href="https://fonts.googleapis.com/css2?family=Nunito:wght@300&display=swap" rel="stylesheet">
                <link href="https://fonts.googleapis.com/css2?family=Nunito:wght@200&display=swap" rel="stylesheet">

                <body style="background-image: linear-gradient(160deg, #0d1d1b, #041421);">
                <h1 style="color: #ffffff; font-family: 'Nunito', sans-serif; text-align: center; padding-top: 20px;">
                    User Response
                </h1>

                <p style="color: #ffffff; font-family: 'Nunito', sans-serif; font-size:120%; padding: 10px 50px;">
                    {message}
                </p>

                <div style="position:fixed;
                            left:0;
                            bottom:0;
                            height:70px;
                            width:100%;
                            border-top: 1px solid #ffffff;
                            ">
                <p align="center"><a style="text-decoration: none;
                                            margin-bottom: 0px;
                                            color: #ffffff;
                                            font-family: 'Nunito', sans-serif;" 
                                            href="https://t.me/medicine_search_bot">
                                            <img style="max-width: 40px;" 
                                                        src="https://www.linkpicture.com/q/MSB_Logo_transparent.png" 
                                                        alt="Logo"></a></p>
                </div>
                </body>
                </html>"""

            msg.set_content(content, subtype='html')
            smtp.send_message(msg)

        update.message.reply_text(
            text="*Щиро дякуємо* ❤️ "
                 "\n\nВаш відгук надіслано\. Ми обовʼязково розглянем його найближчим часом",
            parse_mode="MarkdownV2",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                             resize_keyboard=True,
                                             input_field_placeholder='Оберіть опцію')
        )
    except Exception as e:
        logger.warning(e)
        update.message.reply_text(
            text="*Упс\.\.\. Щось пішло не так* 😞️"
                 "\n\nСпробуйте ще раз, або звʼяжіться з адміністратором бота\.",
            parse_mode="MarkdownV2",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                             resize_keyboard=True,
                                             input_field_placeholder='Оберіть опцію')
        )

    return ConversationHandler.END


@under_maintenance
def cancel_report(update: Update, context: CallbackContext) -> ConversationHandler.END:
    reply_keyboard = MAIN_REPLY_KEYBOARD

    update.message.reply_text(
        text="☑️ Відгук скасовано",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію')
    )

    context.user_data["DRUG_CODE"] = ''
    return ConversationHandler.END


@under_maintenance
def start_report(update: Update, context: CallbackContext) -> int:
    reply_keyboard = [['Скасувати']]

    drug_code = context.user_data.get("DRUG_CODE", '')

    if drug_code == "":
        update.message.reply_text(
            text="⚠️️️ Немає про що повідомляти, спершу відскануйте штрих-код"
        )
        scan_handler(update=update, context=context)
        return ConversationHandler.END
    if db_check_availability(drug_code) is False:
        update.message.reply_text(
            text="⚠️️️ Ви не можете повідомити про штрих-код, що відсутній у базі баних"
        )
        return cancel_report(update=update, context=context)

    update.message.reply_text(
        text=f"❗️️ *Ви повідомляєте про проблему з інформацією про медикамент зі штрих\-кодом __{drug_code}__*"
             "\n\nНадішліть, будь ласка, короткий опис проблеми",
        parse_mode="MarkdownV2",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder='Опис проблеми')
    )
    return REPORT


@under_maintenance
def add_report_description(update: Update, context: CallbackContext) -> ConversationHandler.END:
    report_description = update.message.text
    logger.info("User reported: %s", report_description)

    reply_keyboard = MAIN_REPLY_KEYBOARD

    drug_code = context.user_data["DRUG_CODE"]

    document = collection.find_one({"code": drug_code})
    if "report" in document:
        number = int(re.findall('\[.*?]', document["report"])[-1].strip("[]"))
        collection.update_one({"code": drug_code},
                              {"$set": {"report": document["report"] + f",\n[{number + 1}]: " + report_description}})
    else:
        collection.update_one({"code": drug_code}, {"$set": {"report": "[1]: " + report_description}})

    update.message.reply_text(
        text="✅️ Дякуємо. Ви успішно повідомили про проблему",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію')
    )

    context.user_data["DRUG_CODE"] = ''
    return ConversationHandler.END


@under_maintenance
def start_search(update: Update, context: CallbackContext) -> int:
    reply_keyboard = [['Скасувати']]

    update.message.reply_text(
        text="Введіть *назву*, *активну речовину*, або *штрих\-код* для пошуку по базі даних",
        parse_mode="MarkdownV2",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder='Опис проблеми')
    )
    return SEARCH


@under_maintenance
def search_by_name(update: Update, context: CallbackContext) -> ConversationHandler.END:
    query = update.message.text

    logger.info("Entered query: %s", query)

    medicine_by_name = collection.find({'$text': {'$search': query}},
                                       {'score': {'$meta': "textScore"}}).limit(3)

    medicine_by_name.sort([('score', {'$meta': 'textScore'})])

    reply_keyboard = MAIN_REPLY_KEYBOARD

    if not list(medicine_by_name):
        logger.info("Nothing is found")

        update.message.reply_text(
            text="*❌ Нічого не знайдено*",
            parse_mode="MarkdownV2",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                             one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder='Оберіть опцію')
        )
        return ConversationHandler.END

    logger.info("Found something")

    update.message.reply_text(
        text="*Результати пошуку:*",
        parse_mode="MarkdownV2"
    )

    medicine_by_name.rewind()
    for item in medicine_by_name:
        str_output = f"<b>Назва</b>: {item['name']} " \
                     f"\n<b>Діюча речовина</b>: {item['active_ingredient']} " \
                     f"\n<b>Опис</b>: {item['description']}"

        if item["photo"] == b'':
            update.message.reply_text(
                text='⚠️ Фото відсутнє\n\n' + str_output,
                parse_mode="HTML",
                reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                                 one_time_keyboard=True,
                                                 resize_keyboard=True,
                                                 input_field_placeholder='Оберіть опцію')
            )
        else:
            img = Image.open(io.BytesIO(item['photo']))
            img.save("retrieved_image.jpg")

            update.message.reply_photo(
                open("retrieved_image.jpg", 'rb'),
                caption=str_output,
                parse_mode="HTML",
                reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                                 one_time_keyboard=True,
                                                 resize_keyboard=True,
                                                 input_field_placeholder='Оберіть опцію')
            )
            os.remove("retrieved_image.jpg")

    medicine_by_name.close()
    return ConversationHandler.END


@under_maintenance
def search_by_barcode(update: Update, context: CallbackContext) -> ConversationHandler.END:
    code_str = update.message.text

    logger.info("Entered barcode: %s", code_str)

    medicine_by_barcode = collection.find_one({"code": code_str}, {"_id": 0, "report": 0})

    reply_keyboard = MAIN_REPLY_KEYBOARD

    if not list(medicine_by_barcode):
        logger.info("Nothing is found")

        update.message.reply_text(
            text="*❌ Нічого не знайдено*",
            parse_mode="MarkdownV2"
        )
        return ConversationHandler.END

    logger.info("Found something")

    update.message.reply_text(
        text="*Результати пошуку:*",
        parse_mode="MarkdownV2"
    )

    str_output = f"<b>Назва</b>: {medicine_by_barcode['name']} " \
                 f"\n<b>Діюча речовина</b>: {medicine_by_barcode['active_ingredient']} " \
                 f"\n<b>Опис</b>: {medicine_by_barcode['description']}"

    if medicine_by_barcode["photo"] == b'':
        update.message.reply_text(
            text='⚠️ Фото відсутнє\n\n' + str_output,
            parse_mode="HTML",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                             one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder='Оберіть опцію')
        )
    else:
        img = Image.open(io.BytesIO(medicine_by_barcode['photo']))
        img.save("retrieved_image.jpg")

        update.message.reply_photo(
            open("retrieved_image.jpg", 'rb'),
            caption=str_output,
            parse_mode="HTML",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                             one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder='Оберіть опцію')
        )
        os.remove("retrieved_image.jpg")

    return ConversationHandler.END


@under_maintenance
def cancel_search(update: Update, context: CallbackContext) -> ConversationHandler.END:
    reply_keyboard = MAIN_REPLY_KEYBOARD

    update.message.reply_text(
        text="☑️ Пошук скасовано",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію')
    )
    return ConversationHandler.END


def main() -> None:
    # noinspection SpellCheckingInspection
    updater = Updater(config['Telegram']['token'])
    dispatcher = updater.dispatcher

    start = CommandHandler('start', start_handler)
    scan = MessageHandler(Filters.regex('^(Сканувати|/scan)$'), scan_handler)
    end_scan = MessageHandler(Filters.regex('^(Завершити сканування|Відмінити сканування)$'), end_scan_handler)
    instructions = MessageHandler(Filters.regex('^(Інструкції|/help)$'), instructions_handler)
    continue_scan = MessageHandler(Filters.regex('^(Зрозуміло!|Ще раз)$'), goto_scan)
    decoder = MessageHandler(Filters.photo, retrieve_results)
    not_file = MessageHandler(Filters.attachment, file_warning)
    # do_not_understand = MessageHandler(~ Filters.regex('^(Сканувати|/scan)$') &
    #                                    ~ Filters.regex('^(Інструкції|/help)$') &
    #                                    ~ Filters.regex('^(Зрозуміло!|Ще раз)$') &
    #                                    ~ Filters.regex('Завершити сканування') &
    #                                    ~ Filters.regex('Про мене') &
    #                                    ~ Filters.regex('^(Надіслати відгук|/review)$') &
    #                                    ~ Filters.photo &
    #                                    ~ Filters.attachment, undefined_input)
    cancel = CommandHandler('cancel', cancel_operation)
    about = MessageHandler(Filters.regex('Про мене'), tell_about)

    review_handler = ConversationHandler(
        entry_points=[MessageHandler(Filters.regex('^(Надіслати відгук|/review)$'), start_review)],
        states={
            REVIEW: [
                MessageHandler(Filters.text & ~Filters.command & ~Filters.text("Скасувати"), send_review)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel_report),
                   MessageHandler(Filters.text("Скасувати"), cancel_report)]
    )

    report_handler = ConversationHandler(
        entry_points=[MessageHandler(Filters.text("Повідомити про проблему"), start_report)],
        states={
            REPORT: [
                MessageHandler(Filters.text & ~Filters.command & ~Filters.text("Скасувати"), add_report_description)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel_report),
                   MessageHandler(Filters.text("Скасувати"), cancel_report)]
    )

    search = ConversationHandler(
        entry_points=[MessageHandler(Filters.regex('^(Пошук|/search)$'), start_search)],
        states={
            SEARCH: [
                MessageHandler(Filters.text & ~Filters.regex('^(\d{13})$') & ~Filters.command &
                               ~Filters.text("Скасувати"), search_by_name),
                MessageHandler(Filters.regex('^(\d{13})$') & ~Filters.command & ~Filters.text("Скасувати"),
                               search_by_barcode)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel_search),
                   MessageHandler(Filters.text("Скасувати"), cancel_search)]
    )

    dispatcher.add_handler(CallbackQueryHandler(google_search_set))
    dispatcher.add_handler(MessageHandler(Filters.regex('^(Налаштування|/settings)$'), settings))

    dispatcher.add_handler(start)
    dispatcher.add_handler(search)
    dispatcher.add_handler(scan)
    dispatcher.add_handler(end_scan)
    dispatcher.add_handler(cancel)
    dispatcher.add_handler(instructions)
    dispatcher.add_handler(continue_scan)
    dispatcher.add_handler(decoder)
    dispatcher.add_handler(not_file)
    # dispatcher.add_handler(do_not_understand)
    dispatcher.add_handler(about)
    dispatcher.add_handler(review_handler)
    dispatcher.add_handler(report_handler)

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
