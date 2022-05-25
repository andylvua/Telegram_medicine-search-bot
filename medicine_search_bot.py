"""
Author: Andrew Yaroshevych
Version: 2.5.5 Development
"""
from functools import wraps

from telegram import Update, ReplyKeyboardRemove, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, \
    ChatAction
from telegram.ext import Updater, Filters, CallbackContext, CommandHandler, MessageHandler, CallbackQueryHandler, \
    ConversationHandler

from PIL import Image, ImageDraw
from pyzbar.pyzbar import decode
from email.message import EmailMessage

import io
import logging
import smtplib
import configparser

import requests
import bs4
import re

from pymongo import MongoClient

logging.basicConfig(
    format='%(asctime)s.%(msecs)03d - %(name)s - %(funcName)s() - %(levelname)s - %(message)s',
    datefmt='%d/%m/%Y %H:%M:%S', level=logging.INFO
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

UNDER_MAINTENANCE = True


def under_maintenance(func):
    """
    The under_maintenance function is a decorator that checks if the bot is under maintenance.
    If it is, then it will not allow access to any commands of the bot.

    :param func: Keep the original function name
    :return: The wrapped function
    """
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
    """
    The start_handler function is called when the user sends a message to the bot
    that contains the command /start. It is used to introduce users to our bot and
    to help them interact with it.

    :param update:Update: Access the message object
    :param context:CallbackContext: Store data that will be passed between the callback functions
    :return: None
    """

    user = update.message.from_user
    logger.info("%s: %s", user.first_name, update.message.text)

    reply_keyboard = [['Сканувати', 'Інструкції', 'Пошук'], ['Налаштування', 'Про мене', 'Надіслати відгук']]

    update.message.reply_text(
        '🇺🇦 '
        '*Привіт\! Я бот для пошуку медикаментів\.*'
        '\nЯ допоможу Вам швидко знайти інформацію про ліки\.'
        '\n\nОберіть опцію, будь ласка\. Якщо ви користуєтесь ботом вперше \- рекомендую подивитись розділ "Інструкції"'
        '\n\nЦе можна зробити будь\-коли за допомогою команди */help*',
        parse_mode='MarkdownV2',
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, resize_keyboard=True, input_field_placeholder='Оберіть опцію'
        ),
    )


@under_maintenance
def scan_handler(update: Update, context: CallbackContext) -> None:
    """
    The scan_handler function is used to tell user to scan the barcode on a package.

    :param update:Update: Access the message that was sent by the user
    :param context:CallbackContext: Pass data between the callback functions
    :return: None
    """
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
    """
    The end_scan_handler function is called when the user sends a message to the bot
    that contains /cancel command. It is used to notify the user that scanning has ended and
    to return them to the main menu.

    :param update:Update: Access the message object
    :param context:CallbackContext: Access user data
    :return: None
    """
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
    """
    The instructions_handler function is called whenever the user sends a message that matches
    the regular expression '^(Інструкції|/help)$'.
    It is used to send instructions to users.


    :param update:Update: Access the message object
    :param context:CallbackContext: Send data back to the bot
    :return: None
    """
    user = update.message.from_user
    logger.info("%s: %s", user.first_name, update.message.text)

    reply_keyboard = [['Зрозуміло!']]

    pic = 'resources/How_to_scan.png'
    update.message.reply_photo(open(pic, 'rb'),
                               caption='📷 *Щоб відсканувати штрихкод* та отримати опис ліків \- надішліть мені фото '
                                       'пакування, де я можу *чітко* побачити штрихкод\.'
                                       '\n\n▶️ *Почати сканування* у будь\-який момент можна '
                                       'за допомогою команди */scan*'
                                       '\n\n✏️ Зверніть увагу, ви можете надсилати одразу декілька фотографій\.'
                                       '\n\n❗️ Переконайтесь, що фотографія *не розмита*, а штрихкод розташований '
                                       '*вертикально* або *горизонтально*\. '
                                       '\nЦе мінімізує кількість помилок та дозволить боту працювати коректно\.'
                                       '\n\n🔍 *Скористатися розширеним пошуком* можна за допомогою команди */search* '
                                       '\nЦя функція дозволяє здійснювати пошук за *назвою* та '
                                       '*діючою речовиною* медикаменту\.'
                                       '\n\n ↩️ Відмінити будь\-яку дію можна командою */cancel*'
                                       '\n\n ⚙️ За допомогою команди */settings* можна налаштувати функцію *пошуку '
                                       'медикаменту у Google*'
                                       '\n\n📩 Надіслати нам відгук можна обравши опцію "Надіслати відгук" із головного '
                                       'меню, або скориставшись командою */review*'
                                       '\n\n 💬 Ви можете викликати це повідомлення у *будь\-який момент*, '
                                       'надіславши команду */help*',
                               parse_mode='MarkdownV2',
                               reply_markup=ReplyKeyboardMarkup(
                                   reply_keyboard, one_time_keyboard=True, resize_keyboard=True,
                                   input_field_placeholder='Оберіть опцію'),
                               )


@under_maintenance
def goto_scan(update: Update, context: CallbackContext) -> None:
    """
    The goto_scan function is called in order to call scan_handler.
    It will remove any reply_keyboard that is present and
    tells the user that they can scan their documents.

    :param update:Update: Access the message that was sent by the user
    :param context:CallbackContext: Keep the user's data
    :return: None
    """
    user = update.message.from_user
    logger.info("%s: %s", user.first_name, update.message.text)

    if update.message.text != 'Ще раз':
        update.message.reply_text(
            'Це добре😊 Можемо перейти до сканування.',
            reply_markup=ReplyKeyboardRemove(),
        )
    return scan_handler(update=update, context=context)


def get_db_query_result(barcode) -> bool or None:
    """
    The get_db_query_result function takes a barcode as an argument and returns the result of a MongoDB query.
    If no results are found, it returns None.

    :param barcode: Check if the barcode exists in the database
    :return: A dictionary with the product information if the barcode exists in the database
    """
    try:
        logger.info("Database quired. Checking availability")
        query_result = collection.find_one({"code": barcode}, {"_id": 0})
        if query_result is None:
            return

        return query_result
    except Exception as e:
        logger.error(e)
        return


def format_query(query_result) -> str or None:
    """
    The format_query function takes a query result and returns a string
    representation of the query result. This is used for displaying
    query results in human-readable format.

    :param query_result: Retrieve the information from the database
    :return: A string containing the name, active ingredient and description of the drug
    """
    try:
        logger.info("Retrieving info")
        str_output = f"<b>Назва</b>: {query_result['name']} " \
                     f"\n<b>Діюча речовина</b>: {query_result['active_ingredient']} " \
                     f"\n<b>Опис</b>: {query_result['description']} "
        return str_output
    except Exception as e:
        logger.info(e)
        return


def retrieve_query_photo(query_result) -> bytes or None:
    """
    The retrieve_query_photo function retrieves the photo from a query result.

    :param query_result: Retrieve the photo from the database
    :return: The binary data of the photo
    """
    try:
        assert query_result is not None

        if query_result['photo'] == b'':
            logger.info("Field 'photo' is empty")
            return

        logger.info("Retrieving photo")
        img = query_result['photo']
        return img
    except AssertionError:
        return


def send_scanned_barcode_image(update: Update, bytes_image: io.BytesIO) -> None:
    """
    The send_scanned_barcode_image function takes an image and draws a rectangle around the detected barcode.
    It then saves the image to a BytesIO object, which is then sent as an update with the message.

    :param update: Update: Pass the update that caused the handler to be called
    :param bytes_image:bytes: Image to detect the barcode
    :return: None
    """
    image = Image.open(bytes_image)
    draw = ImageDraw.Draw(image)

    for barcode in decode(image):
        rect = barcode.rect
        draw.rectangle(
            (
                (rect.left, rect.top),
                (rect.left + rect.width, rect.top + rect.height)
            ),
            outline='#c4102e',
            width=5
        )

    output = io.BytesIO()
    image.save(output, "PNG")

    update.message.reply_photo(output.getvalue())


def scan_barcode(image_bytes: io.BytesIO) -> str:
    """
    The scan_barcode function takes in an image file and returns the barcode contained within it.

    :param image_bytes:io.BytesIO: Pass the image from the camera to the decode function
    :return: The string representation of the barcode that it decodes
    """
    logger.info("Trying to decode")
    result = decode(Image.open(image_bytes))

    assert result

    barcode = result[0].data.decode("utf-8")
    return barcode


# noinspection DuplicatedCode
@under_maintenance
def retrieve_results(update: Update, context: CallbackContext) -> None:
    """
    The retrieve_results function retrieves the results of a barcode scan.
    It first checks if the barcode is present in our database, and if it is, it sends back an image of that product.
    If not, then it will send back a message saying that the product was not found in our database.

    :param update: Update: Access the message object
    :param context: CallbackContext: Send data back to the main handler function
    :return: None
    """
    user = update.message.from_user
    logger.info("%s: Photo received", user.first_name)

    if update.message.photo:
        id_img = update.message.photo[-1].file_id
    else:
        return

    photo = context.bot.getFile(id_img)
    image_bytes = io.BytesIO()
    photo.download(out=image_bytes)

    # send_scanned_barcode_image(update, image_bytes)

    try:
        barcode = scan_barcode(image_bytes)
    except AssertionError:
        logger.info("Failed to scan. Asking to retry")

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
    else:
        link = 'https://www.google.com/search?q=' + barcode

        reply_keyboard = [['Завершити сканування', 'Повідомити про проблему']]

        query_result = get_db_query_result(barcode)
        photo = retrieve_query_photo(query_result)

        if query_result and photo is not None:
            logger.info("The barcode is present in the database")

            update.message.reply_photo(
                photo,
                parse_mode='HTML',
                reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                                 resize_keyboard=True,
                                                 input_field_placeholder='Продовжуйте'),
                caption='Ось відсканований штрихкод ✅:\n' + '<b>' + barcode + '</b>' + "\n\n" +
                        format_query(query_result),
            )

        elif query_result:
            update.message.reply_text(
                parse_mode='HTML',
                reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                                 resize_keyboard=True,
                                                 input_field_placeholder='Продовжуйте'),
                text='Ось відсканований штрихкод ✅:\n' + '<b>' + barcode + '</b>' + "\n\n" +
                     format_query(query_result) + "\n\n⚠️ Фото відсутнє",
                quote=True
            )
        else:
            reply_keyboard = [['Завершити сканування']]

            update.message.reply_text(parse_mode='HTML',
                                      reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                                                       resize_keyboard=True,
                                                                       input_field_placeholder='Продовжуйте'),
                                      text='Штрих-код ' + '<b>' + barcode + '</b>' +
                                           ' на жаль відсутній у моїй базі даних ❌'
                                           '\n\nЯкщо ви хочете долучитись до наповнення бази даних - '
                                           'скористайтесь нашим другим ботом <b>@msb_database_bot</b>',
                                      quote=True)

        if context.user_data.setdefault("GOOGLE_SEARCH", "True") == "True":
            update.message.reply_text(parse_mode='HTML',
                                      reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                                                       resize_keyboard=True,
                                                                       input_field_placeholder='Продовжуйте'),
                                      text='<b>' + '\n\nЙмовірно це: ' + '</b>' + get_query_heading(barcode) +
                                           ' - (За результатами пошуку ' + f'<a href="{link}"><b>Google</b></a>' + ')',
                                      disable_web_page_preview=True)

        context.user_data["DRUG_CODE"] = barcode


def get_query_heading(barcode) -> str:
    """
    The get_query_heading function takes a string of the form '0123456789' and returns
    the heading of the first Google search result for that string.

    :param barcode: Barcode for the Google search
    :return: A string containing the first heading of a search query
    """
    url = 'https://google.com/search?q=' + barcode

    request_result = requests.get(url)
    soup = bs4.BeautifulSoup(request_result.text, "html.parser")

    heading_objects = soup.find_all('h3')
    first_heading = heading_objects[0]

    first_heading_formatted = re.sub(r"\([^()]*\)", "", first_heading.getText().split(' - ')[0]
                                     .replace(barcode, '')).lstrip().rstrip('.').rstrip()
    return first_heading_formatted


@under_maintenance
def file_warning(update: Update, context: CallbackContext) -> None:
    """
    The file_warning function is called when a user sends a file instead of an image.
    It will reply with the following message:
    'Будь ласка, використовуйте фотографію, а не файл.'

    :param update:Update: Access the message that was sent by the user
    :param context:CallbackContext: Pass information between different parts of the program
    :return: None
    """
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
    """
    The undefined_input function is called when the user sends a message that
    is not recognized by any of the other handlers.
    It simply replies with a message explaining how to use it.

    :param update:Update: Pass the incoming update to the handler
    :param context:CallbackContext: Pass data between handlers
    :return: None
    """
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
    """
    The cancel_operation function is called when the user sends /cancel to the bot.
    It is used to cancel an ongoing operation.

    :param update:Update: Access the message object
    :param context:CallbackContext: Pass data between handlers
    :return: None
    """
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
    """
    The tell_about function is a callback function that is called when the user sends command "Про мене".
    It will send a photo of bot logo and some information about our bot to the user.

    :param update:Update: Access the message that was sent by the user
    :param context:CallbackContext: Pass data between callbacks
    :return: None
    """
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
    """
    The settings function is used to change the settings of the bot.
    It is called when a user clicks on /settings in the Telegram app.
    The function sends a message with two inline buttons attached,
    each one for enabling or disabling Google search results output.

    :param update: Update: Access the context of the conversation
    :param context: CallbackContext: Store data on the bot object’s state
    :return: A message with three inline buttons attached
    """
    """Sends a message with three inline buttons attached."""
    if context.user_data.setdefault("GOOGLE_SEARCH", "True") == "True":
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
    """
    The google_search_set function parses the CallbackQuery and updates the message text.
    It also creates a keyboard with two options: True or False, which are then passed to
    the reply_markup argument of edit_message_text.

    :param update:Update: Access the context of the callback query
    :param context:CallbackContext: Store data that is shared between the callback handlers of a single query
    :return: None
    """
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
    """
    The start_review function is called when the user sends a message to the bot
    with /review command. It will ask for review text.


    :param update:Update: Access the telegram api
    :param context:CallbackContext: Pass data between different parts of the program
    :return: The next state of the conversation
    """
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
    """
    The send_review function sends a review to the MSB admins.
    It takes in an update and context objects as parameters, and returns ConversationHandler.END.

    :param update:Update: Access the telegram api
    :param context:CallbackContext: Access data,
    :return: Conversationhandler.END
    """
    review_msg = update.message.text
    user = update.message.from_user

    logger.info("User reviewed: %s", review_msg)

    context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

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
    """
    The cancel_report function is called when the user cancels their report.
    It removes the drug code from context and returns to main menu.

    :param update:Update: Access the telegram api
    :param context:CallbackContext: Pass data between states
    :return: Conversationhandler.END
    """
    reply_keyboard = MAIN_REPLY_KEYBOARD

    update.message.reply_text(
        text="☑️ Відгук скасовано",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію')
    )

    context.user_data["DRUG_CODE"] = 0
    return ConversationHandler.END


@under_maintenance
def start_report(update: Update, context: CallbackContext) -> int:
    """
    The start_report function is called when the user sends a message "Повідомити про проблему" to the bot.
    It is used to start report conversation with user.
    It checks if there is a drug code in context and if it's not 0, and it's present in the database, then it asks for
    a description of problem with drug from user.

    :param update:Update: Access the message object
    :param context:CallbackContext: Store data between calls
    :return: The next state of the conversation
    """
    reply_keyboard = [['Скасувати']]

    drug_code = context.user_data.get("DRUG_CODE", 0)

    if drug_code == 0:
        update.message.reply_text(
            text="⚠️️️ Немає про що повідомляти, спершу відскануйте штрих-код"
        )
        scan_handler(update=update, context=context)
        return ConversationHandler.END
    if get_db_query_result(drug_code) is None:
        update.message.reply_text(
            text="⚠️️️ Ви не можете повідомити про штрих-код, що відсутній у базі баних"
        )
        return cancel_report(update=update, context=context)

    update.message.reply_text(
        text=f"❗️️ *Ви повідомляєте про проблему з інформацією про медикамент зі штрих\-кодом __{str(drug_code)}__*"
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
    """
    The add_report_description function takes in an update and context object as arguments.
    It then saves the report description to MongoDB, and replies with a confirmation message.

    :param update:Update: Pass on any information that has been passed to the handler
    :param context:CallbackContext: Store data in the context
    :return: Conversationhandler.END
    """
    report_description = update.message.text
    user_id = update.effective_user.id

    logger.info("User reported: %s", report_description)

    reply_keyboard = MAIN_REPLY_KEYBOARD

    drug_code = context.user_data["DRUG_CODE"]

    document = collection.find_one({"code": drug_code})
    if "report" in document:
        number = int(re.findall('\[.*?]', document["report"])[-1].strip("[]"))
        collection.update_one({"code": drug_code},
                              {"$set": {"report": document["report"] + f", [{user_id}]: " + report_description}})
    else:
        collection.update_one({"code": drug_code}, {"$set": {"report": f"[{user_id}]: " + report_description}})

    update.message.reply_text(
        text="✅️ Дякуємо. Ви успішно повідомили про проблему",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію')
    )

    context.user_data["DRUG_CODE"] = 0
    return ConversationHandler.END


@under_maintenance
def start_search(update: Update, context: CallbackContext) -> int:
    """
    The start_search function is called when the user sends a message to the bot
    with /search command. It will prompt them for input and then search for that input in
    the database. If it finds something, it will return a list of possible matches.

    :param update:Update: Access the context of the conversation
    :param context:CallbackContext: Keep track of the user’s conversation state
    :return: The next state of conversation
    """
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
    """
    The search_by_name function is called if user entered name or active ingredint as search query.
    It takes the update and context objects as arguments, and returns ConversationHandler.END to stop the conversation.

    :param update:Update: Pass the incoming update to the handler function
    :param context:CallbackContext: Pass data between callbacks
    :return: Conversationhandler.END
    """
    query = update.message.text

    logger.info("Entered query: %s", query)

    medicine_by_name = collection.find({'$text': {'$search': f"/^{query}/"}},
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
            img = item['photo']

            update.message.reply_photo(
                img,
                caption=str_output,
                parse_mode="HTML",
                reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                                 one_time_keyboard=True,
                                                 resize_keyboard=True,
                                                 input_field_placeholder='Оберіть опцію')
            )

    medicine_by_name.close()
    return ConversationHandler.END


@under_maintenance
def search_by_barcode(update: Update, context: CallbackContext) -> ConversationHandler.END:
    """
    The search_by_barcode function is called if user entered barcode as search query.
    It takes as input an Update object and a Context object,
    and returns the ConversationHandler.END to stop the conversation.

    :param update:Update: Pass the incoming update to the handler
    :param context:CallbackContext: Keep track of the user's conversation flow
    :return: ConversationHandler.END
    """
    barcode = update.message.text

    logger.info("Entered barcode: %s", barcode)

    medicine_by_barcode = collection.find_one({"code": barcode}, {"_id": 0, "report": 0})

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
        img = medicine_by_barcode['photo']

        update.message.reply_photo(
            img,
            caption=str_output,
            parse_mode="HTML",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                             one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder='Оберіть опцію')
        )

    return ConversationHandler.END


@under_maintenance
def cancel_search(update: Update, context: CallbackContext) -> ConversationHandler.END:
    """
    The cancel_search function is called when the user sends a message to cancel their search.
    It will return the user back to the main menu.

    :param update:Update: Access the telegram api
    :param context:CallbackContext: Access the update_queue, dispatcher and bot attributes
    :return: Conversationhandler.END
    """
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
    dispatcher.add_handler(about)
    dispatcher.add_handler(review_handler)
    dispatcher.add_handler(report_handler)

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
