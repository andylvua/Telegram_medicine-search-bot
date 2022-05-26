"""
Author: Andrew Yaroshevych
Version: 2.6.5 Development
"""
from datetime import datetime

from telegram import ReplyKeyboardMarkup, Update, KeyboardButton, ForceReply, ChatAction, InlineKeyboardButton, \
    InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, ConversationHandler, CallbackContext

from PIL import Image
from pyzbar.pyzbar import decode
from email.message import EmailMessage

import os
import io
import json
import logging
import smtplib
import configparser
from functools import wraps

from pymongo import MongoClient

import validators
import statistics
import face_recognition as faces

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
admins_collection = db.Administrators
blacklist = db.Blacklist

# Conversation states
NAME, INGREDIENT, ABOUT, PHOTO, CHECK, INSERT, CHANGE_INFO, REWRITE = range(8)
CONTACT, ADMIN_PHOTO = range(2)
REPORT = 1
REVIEW = 1
STATISTICS, SEND_FILES = range(2)
REASON, BAN = range(2)


MAIN_REPLY_KEYBOARD = [['Перевірити наявність', 'Додати новий медикамент', 'Інструкції', 'Надіслати відгук']]

UNDER_MAINTENANCE = True


def under_maintenance(func):
    """
    The under_maintenance function is a decorator that checks if the bot is under maintenance.
    If it is, then it will not allow access to any commands of the bot.

    :param func: Pass the wrapped function to the decorator
    :return: The function that was passed to it
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


def superuser(func):
    """
    The superuser function is a decorator that checks if the user is in the
    superuser list. If they are, it allows them to use the decorated functions.

    :param func: Pass the wrapped function to the decorator
    :return: The function that was passed to it
    """
    @wraps(func)
    def wrapped(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        superusers = config.items("Superusers")

        if user_id not in list(int(value) for key, value in superusers):
            logger.info("Unauthorized superuser access denied ID: {}".format(user_id))

            update.message.reply_text(
                "❌ *Ви не можете використовувати цю команду, оскільки не "
                "належите до користувачів із спеціальним доступом*",
                parse_mode="MarkdownV2"
            )
            return
        else:
            logger.info("Superuser access granted")

        return func(update, context, *args, **kwargs)
    return wrapped


def restricted(func):
    """
    The restricted function is a decorator which restricts usage of the function to only admins.
    It is used by passing the function name as an argument to it.

    :param func: Pass the function that will be decorated
    :return: The wrapped function
    """
    @wraps(func)
    def wrapped(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        if blacklist.count_documents({"user_id": user_id}) != 0:
            logger.info("User banned by ID: {}".format(user_id))
            blocked_user = blacklist.find_one({"user_id": user_id}, {"_id": 0})

            update.message.reply_text(
                "❌ *Вас заблоковано\.* ID: *{}*".format(user_id) +
                f"\n\n*Причина*: {blocked_user['reason']} "
                "\n\nЯкщо Ви вважаєте, що це помилка \- зверніться до адміністратора бота",
                parse_mode='MarkdownV2',
            )
            return
        if admins_collection.count_documents({"user_id": user_id}) != 0:
            logger.info("Admin is already registered. Access granted")
        else:
            user = update.message.from_user
            user_name = user.first_name

            update.message.reply_text(
                f"❌ <b>{user_name}</b>, Ви не можете проводити операцій з базою даних."
                f"\n\nВаш ID <b>{user_id}</b> не зареєстровано як адміністратора"
                "\n\nАби зареєструватись, виконайте команду <b>/authorize</b>",
                parse_mode='HTML',
            )
            logger.info("Unauthorized access denied for {}. Asking to authorize".format(user_id))
            return
        return func(update, context, *args, **kwargs)

    return wrapped


@under_maintenance
def start_handler(update: Update, context: CallbackContext) -> None:
    """
    The start_handler function is called when the user sends a message to the bot
    that contains the command /start. It is used to initialize and reset all variables
    in context.user_data, as well as send a welcome message back to the user.

    :param update: Update: Update the user interface
    :param context: CallbackContext: Store data during the conversation
    :return: None
    """
    user = update.message.from_user
    logger.info("%s: %s", user.first_name, update.message.text)

    context.user_data["DRUG_INFO"] = {
        "name": "",
        "active_ingredient": "",
        "description": "",
        "code": "",
        "photo": b'',
        "user_id": 0,
        "added_on": ''
    }

    reply_keyboard = MAIN_REPLY_KEYBOARD

    update.message.reply_text(
        '🇺🇦 '
        '*Привіт\! Я бот для адміністування бази даних Telegram MSB\.*'
        '\n\nОберіть опцію, будь ласка\. Якщо ви користуєтесь ботом вперше \- рекомендую подивитись розділ "Інструкції"'
        '\n\nЦе можна зробити будь\-коли за допомогою команди */help*',
        parse_mode='MarkdownV2',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію')
    )


@under_maintenance
def scan_handler(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    logger.info("%s: %s", user.first_name, update.message.text)

    reply_keyboard = [['Відмінити сканування']]

    update.message.reply_text(
        'Будь ласка, надсилайте мені фото пакувань, де я можу *чітко* побачити штрихкод '
        'для перевірки наявності\.',
        parse_mode='MarkdownV2',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder='Надішліть фото')
    )


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


@under_maintenance
def retrieve_scan_results(update: Update, context: CallbackContext) -> None:
    """
    The retrieve_scan_results function is called when the user scans a barcode.
    It checks if the barcode is present in our database and, if so, sends it to the user.
    If not, it asks them whether they want to add information about this drug.

    :param update: Update: Access the message (if any) sent when the command /start was issued
    :param context: CallbackContext: Send data back to the conversation handler
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

    try:
        barcode = scan_barcode(image_bytes)
    except AssertionError:
        logger.info("Failed to scan")

        reply_keyboard = [['Ще раз', 'Інструкції']]

        update.message.reply_text(
            text="*На жаль, сталася помилка\. Мені не вдалося відсканувати штрих\-код ❌ *"
                 "\nСпробуйте ще раз, або подивіться інструкції до сканування та "
                 "переконайтесь, що робите все правильно\.",
            quote=True,
            parse_mode='MarkdownV2',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                             one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder='Оберіть опцію')
        )
    else:
        logger.info("Decoded successfully")

        context.user_data.setdefault("DRUG_INFO", {})["code"] = barcode

        reply_keyboard = [['Завершити сканування', 'Повідомити про проблему']]
        reply_keyboard2 = [['Так', 'Ні']]

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
                caption='✅ Штрих-код ' + '<b>' + barcode + '</b>' +
                        ' наявний у моїй базі даних:\n\n' +
                        format_query(query_result),
                quote=True
            )

        elif query_result:
            logger.info("The barcode is present in the database but photo is missing")

            update.message.reply_text(
                parse_mode='HTML',
                reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                                 resize_keyboard=True,
                                                 input_field_placeholder='Продовжуйте'),
                text='✅ Штрих-код ' + '<b>' + barcode + '</b>' +
                     ' наявний у моїй базі даних:\n\n' +
                     format_query(query_result) +
                     '\n\n⚠️ Фото відсутнє',
                quote=True
            )
        else:
            logger.info("The barcode is missing from the database. Asking to add info")
            link = 'https://www.google.com/search?q=' + barcode

            update.message.reply_text(
                parse_mode='HTML',
                reply_markup=ReplyKeyboardMarkup(reply_keyboard2, one_time_keyboard=True,
                                                 resize_keyboard=True,
                                                 input_field_placeholder='Продовжуйте'),
                text='❌ Штрих-код ' + '<b>' + barcode + '</b>' +
                     ' відсутній у моїй базі даних.\n\n' +
                     'Чи бажаєте Ви додати інформацію про цей медикамент?'
                     f'\n\nДля зручності, ви можете знайти інформацію про цей медикамент у '
                     f'<a href="{link}"><b>Google</b></a>',
                quote=True,
                disable_web_page_preview=True
            )


@under_maintenance
@restricted
def start_adding(update: Update, context: CallbackContext) -> int:
    """
    The start_adding function is called when the user sends the /add command to the bot.
    If the user has sent a photo, it will ask for a name of the medicine. If not, it will ask to send one.

    :param update: Update: Access the telegram api
    :param context: CallbackContext: Pass data from the handler to the callback function
    :return: The name state
    """
    user = update.message.from_user
    logger.info("User %s started adding process", user.first_name)

    reply_keyboard = [['Скасувати додавання']]

    if update.message.text != "Так" and not update.message.photo:
        logger.info("Photo is missing, asking to scan one")

        update.message.reply_text(
            'Добре.\nСпершу, надішліть фото штрих-коду',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                             resize_keyboard=True,
                                             input_field_placeholder='Надішліть фото')
        )

        return NAME
    elif not update.message.photo:
        logger.info("Photo already scanned, asking for a name")
        update.message.reply_text(
            'Добре.\nСпершу, надішліть назву медикаменту',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                             resize_keyboard=True,
                                             input_field_placeholder='Введіть назву')
        )
        return INGREDIENT


@under_maintenance
def get_name(update: Update, context: CallbackContext) -> int or None:
    """
    The get_name function is called in the name state when the user sends a message to the bot.
    The function first checks if there is an image with barcode on it, and then tries to decode it using zbar library.
    If decoding was successful, we get a code of drug from decoded data and check if such code exists in our database.
    If yes - it cancels adding process. If Exeption is occured during decoding it sends an error message and return
    to start_adding function (which asks for another photo).
    Otherwise - ask for name of medicine.

    :param update: Update: Access the telegram api
    :param context: CallbackContext: Store data in between calls
    :return: Ingredient state of conversation or None
    """
    user = update.message.from_user
    reply_keyboard = [['Скасувати додавання']]

    if update.message.photo:
        id_img = update.message.photo[-1].file_id
    else:
        return

    photo = context.bot.getFile(id_img)
    image_bytes = io.BytesIO()
    photo.download(out=image_bytes)

    logger.info("Storing photo")

    try:
        logger.info("Trying to decode")

        result = decode(Image.open(image_bytes))
        barcode = result[0].data.decode("utf-8")

        logger.info("Decoded successfully")

        if get_db_query_result(barcode):
            logger.info("This barcode already exists. Cancelling adding process")

            update.message.reply_text(
                text="⚠️ Медикамент з таким штрих-кодом вже присутній у базі даних.",
                quote=True
            )

            return cancel(update=update, context=context)
        else:
            context.user_data.setdefault("DRUG_INFO", {})["code"] = barcode
            logger.info("Storing barcode info")

            update.message.reply_text(
                text="Штрих-код відскановано успішно ✅",
                quote=True
            )

    except IndexError as e:
        logger.info("Failed to scan. Asking to retry")

        update.message.reply_text(
            text="*На жаль, сталася помилка\. Мені не вдалось відсканувати штрих\-код ❌ *"
                 "\nПереконайтесь, що робите все правильно та надішліть фото ще раз, "
                 "або подивіться інструкції до сканування за допомогою команди */help*",
            quote=True,
            parse_mode='MarkdownV2',
        ),

        return start_adding(update=update, context=context)

    logger.info("Asking for a name")
    update.message.reply_text(
        text='Надішліть назву медикаменту',
        reply_markup=ForceReply(input_field_placeholder="Назва")
    )

    return INGREDIENT


@under_maintenance
def get_active_ingredient(update: Update, context: CallbackContext) -> int:
    """
    The get_active_ingredient function is called when the user enters a name of the drug.
    It checks if the entered name is correct, stores it, and then asks for an active ingredient.

    :param update: Update: Access the message object
    :param context: CallbackContext: Store data that will be passed between the handlers
    :return: About state of conversation
    """
    logger.info("Entered name of the drug: %s", update.message.text)

    user = update.message.from_user
    reply_keyboard = [['Скасувати додавання']]

    name = update.message.text
    if validators.check_name(name) is None:
        logger.info("Name is not correct, asking to retry")

        update.message.reply_text(
            text='*Вкажіть, будь ласка, корректну назву*'
                 f'\n\nПоточна назва "{name}" містить тільки цифри',
            parse_mode="MarkdownV2",
            reply_markup=ForceReply(input_field_placeholder="Повторіть")
        )
        return INGREDIENT

    context.user_data.setdefault("DRUG_INFO", {})["name"] = name
    logger.info("Storing name")

    logger.info("Asking for an active ingredient")

    update.message.reply_text(
        text='Вкажіть, будь ласка, діючу речовину медикаменту',
        reply_markup=ForceReply(input_field_placeholder="Діюча речовина")
    )

    return ABOUT


@under_maintenance
def get_about(update: Update, context: CallbackContext) -> int:
    """
    The get_about function is called when the user sends an active ingredient to the bot.
    It is used to get information about a drug.
    The function first checks if the active ingredient of the drug is correct, stores it,
    and then asks for its description.

    :param update: Update: Store the incoming message
    :param context: CallbackContext: Store data on the conversation between functions
    :return: Photo state of conversation
    """
    logger.info("Entered active ingredient of the drug: %s", update.message.text)

    user = update.message.from_user
    reply_keyboard = [['Скасувати додавання']]

    active_ingredient = update.message.text
    if validators.check_active_ingredient(active_ingredient) is None:
        logger.info("Active ingredient is not correct, asking to retry")

        update.message.reply_text(
            text='*Вкажіть, будь ласка, корректну назву діючої речовини*'
                 f'\n\nПоточна назва діючої речовини "{active_ingredient}" містить тільки цифри',
            parse_mode="MarkdownV2",
            reply_markup=ForceReply(input_field_placeholder="Повторіть")

        )
        return ABOUT

    context.user_data["DRUG_INFO"]["active_ingredient"] = active_ingredient
    logger.info("Storing active ingredient")

    logger.info("Asking for a description")

    update.message.reply_text(
        text='Тепер надішліть короткий опис даного препарату',
        reply_markup=ForceReply(input_field_placeholder="Опис")
    )

    return PHOTO


@under_maintenance
def get_photo(update: Update, context: CallbackContext) -> int:
    """
    The get_photo function checks if entered drug description is correct, stores it,
    and then asks the user to send a photo of the front side of
    the medicine package.


    :param update: Update: Access the message object
    :param context: CallbackContext: Pass the user id to the function
    :return: Check state of conversation
    """
    logger.info("Entered description: %s", update.message.text)

    user = update.message.from_user
    reply_keyboard = [['Скасувати додавання', 'Пропустити']]

    description = update.message.text
    try:
        if validators.check_description(description) != description:
            logger.info("Description is not correct, asking to retry")

            reply_keyboard = [['Скасувати додавання']]

            update.message.reply_text(
                text=f'Вкажіть, будь ласка, опис українською мовою'
                     f'\n\nПоточна мова: {validators.check_description(description)}',
                reply_markup=ForceReply(input_field_placeholder="Повторіть")
            )
            return PHOTO
    except Exception as e:
        logger.info("Description is not correct, asking to retry")
        logger.info(e)

        reply_keyboard = [['Скасувати додавання']]

        update.message.reply_text(
            text=f'Мені не вдалося розпізнати мову введеного тексту. Введіть, будь ласка, коректний опис!',
            reply_markup=ForceReply(input_field_placeholder="Повторіть")
        )
        return PHOTO

    context.user_data["DRUG_INFO"]["description"] = description
    logger.info("Storing description")

    logger.info("Asking for a photo of the front side")

    update.message.reply_text(
        text='Також, надішліть фото передньої сторони упаковки медикаменту.'
             '\n\n(Не рекомендується) Натисніть "Пропустити", якщо не хочете додавати фото',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         resize_keyboard=True,
                                         input_field_placeholder="Надішліть фото")
    )
    return CHECK


@under_maintenance
def skip_photo(update: Update, context: CallbackContext) -> int:
    """
    The skip_photo function skips adding photo of the front side of
    the medicine package.


    :param update: Update: Update the user's profile
    :param context: CallbackContext: Pass information to the callback function
    :return: Check state of the conversation
    """
    return CHECK


@under_maintenance
def check_info(update: Update, context: CallbackContext) -> int:
    """
    The check_info function is used to check the entered information about the drug.
    It formats output string of the name, active ingredient and the description.
    Then it checks if there is a photo, and if everything is correct it asks for confirmation of adding to database.

    :param update: Update: Access the message object
    :param context: CallbackContext: Pass the user data to the function
    :return: Insert state of the conversation
    """
    logger.info("All info collected successfully. Now checking...")

    user = update.message.from_user

    drug_info = context.user_data["DRUG_INFO"]

    output = f"<b>Назва</b>: {drug_info['name']} " \
             f"\n<b>Діюча речовина</b>: {drug_info['active_ingredient']} " \
             f"\n<b>Опис</b>: {drug_info['description']} "

    reply_keyboard = [['Так, додати до бази даних', 'Змінити інформацію', 'Ні, скасувати']]

    if update.message.photo:
        id_img = update.message.photo[-1].file_id
        photo = context.bot.getFile(id_img)
        image_bytes = io.BytesIO()

        photo.download(out=image_bytes)
        context.user_data["DRUG_INFO"]["photo"] = image_bytes.getvalue()
        logger.info("Storing photo")

        update.message.reply_photo(
            image_bytes.getvalue(),
            caption='<b>Введена інформація:</b>\n\n' + output +
                    '\n\n❓Ви точно бажаєте додати її до бази даних?',
            parse_mode='HTML',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                             resize_keyboard=True,
                                             input_field_placeholder="Оберіть опцію")
        )

    elif update.message.text and drug_info.setdefault("photo", b'') == b'':
        logger.info("Photo skipped")

        update.message.reply_text(
            text='<b>Введена інформація:</b>\n\n' +
                 '⚠️ Фото відсутнє\n' + output +
                 '\n\n❓Ви точно бажаєте додати її до бази даних?',
            parse_mode='HTML',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                             resize_keyboard=True,
                                             input_field_placeholder="Оберіть опцію")
        )
    else:
        img = drug_info['photo']

        update.message.reply_photo(
            img,
            caption='<b>Введена інформація:</b>\n\n' + output +
                    '\n\n❓Ви точно бажаєте додати її до бази даних?',
            parse_mode='HTML',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                             resize_keyboard=True,
                                             input_field_placeholder="Оберіть опцію")
        )
    return INSERT


@under_maintenance
def insert_to_db(update: Update, context: CallbackContext) -> int or ConversationHandler.END:
    """
    The insert_to_db function adds a drug to the database.
    It takes in an update and context as arguments, checks the user confirnation message,
    and if it's 'Так, додати до бази даних' then adds it to the database.
    It also sends a message confirming that it was added successfully.
    If message text is 'Змінити інформацію' it returns change_info of the conversation.
    If none of that checks are passed it cancels the adding process

    :param update: Update: Access the message object
    :param context: CallbackContext: Keep track of the state of a conversation
    :return: Next state or ConversationHandler.END
    """
    user = update.message.from_user

    reply_keyboard = MAIN_REPLY_KEYBOARD

    if update.message.text == 'Так, додати до бази даних':
        user_id = update.effective_user.id

        context.user_data["DRUG_INFO"]["user_id"] = user_id
        context.user_data["DRUG_INFO"]["added_on"] = datetime.now().strftime("%d/%m/%Y, %H:%M:%S")

        collection.insert_one(context.user_data["DRUG_INFO"])
        logger.info("Checked info. Added to DB successfully")

        update.message.reply_text(
            text='✅ Препарат успішно додано до бази даних',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder="Оберіть опцію")
        )

        logger.info("Clearing info: %s", context.user_data["DRUG_INFO"])
        context.user_data["DRUG_INFO"].clear()
        logger.info("Cleared")

    elif update.message.text == 'Змінити інформацію':
        logger.info("User asked to change info")

        reply_keyboard_change = [['Назва', 'Діюча речовина', 'Опис']]
        update.message.reply_text(
            text='Гаразд, яке поле ви хочете змінити?',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard_change, one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder="Оберіть опцію")
        )
        return CHANGE_INFO

    else:
        logger.info("User %s canceled adding process", user.first_name)

        update.message.reply_text(
            text='☑️ Гаразд, додавання скасовано',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder="Оберіть опцію")
        )

    return ConversationHandler.END


@under_maintenance
def change_info(update: Update, context: CallbackContext) -> int:
    """
    The change_info function is called when the user chooses to change entered info
    and change info state is returned.
    It checks what field of information is being changed and then asks for new data.


    :param update: Update: Access the message that is received by the bot
    :param context: CallbackContext: Store data on the user's side throughout the conversation
    :return: Rewrite state and information that the user wants to change
    """
    reply_keyboard = [['Скасувати додавання']]

    if update.message.text == 'Назва':
        logger.info("Asking for a new name")

        context.user_data["change"] = "name"
        update.message.reply_text(
            text='Добре, надішліть нову назву',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder="Оберіть опцію")
        )
    if update.message.text == 'Діюча речовина':
        logger.info("Asking for a new active ingredient")

        context.user_data["change"] = "active_ingredient"
        update.message.reply_text(
            text='Добре, надішліть нову назву діючої речовини',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder="Оберіть опцію")
        )
    if update.message.text == 'Опис':
        logger.info("Asking for a new description")

        context.user_data["change"] = "description"
        update.message.reply_text(
            text='Добре, надішліть новий опис',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder="Оберіть опцію")
        )

    return REWRITE


@under_maintenance
def rewrite(update: Update, context: CallbackContext) -> check_info:
    """
    The rewrite function is used to change the information of a drug.
    It is called when the user wants to change a specific field of their drug.
    The function first checks if the user is changing their name, active ingredient, or description.
    If they are changing their name, it changes that field in DRUG_INFO and then calls check_info().
    If they are changing an active ingredient or description, it changes that field in DRUG_INFO
    and then calls check_info().

    :param update: Update: Access the message that is being sent by the user
    :param context: CallbackContext: Store the user data
    :return: The check_info function
    """
    if context.user_data["change"] == "name":
        context.user_data["DRUG_INFO"]["name"] = update.message.text

        logger.info("Changed name succsessfully")

        return check_info(update=update, context=context)
    if context.user_data["change"] == "active_ingredient":
        context.user_data["DRUG_INFO"]["active_ingredient"] = update.message.text

        logger.info("Changed active ingredient succsessfully")

        return check_info(update=update, context=context)
    if context.user_data["change"] == "description":
        context.user_data["DRUG_INFO"]["description"] = update.message.text

        logger.info("Changed description succsessfully")

        return check_info(update=update, context=context)


@under_maintenance
def cancel(update: Update, context: CallbackContext) -> ConversationHandler.END:
    """
    The cancel function is called when the user sends /cancel to the bot.
    It is used to stop a conversation used to add medicine.

    :param update: Update: Access all the information of the new message sent by the user
    :param context: CallbackContext: Pass information to the callback function
    :return: Conversationhandler.END
    """
    user = update.message.from_user
    reply_keyboard = MAIN_REPLY_KEYBOARD

    logger.info("User %s canceled the adding process", user.first_name)
    update.message.reply_text(
        text='ℹ️ Операцію додавання скасовано',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         one_time_keyboard=True, resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію')
    )

    return ConversationHandler.END


@under_maintenance
def file_warning(update: Update, context: CallbackContext) -> None:
    """
    The file_warning function is called when a user sends a file instead of an image.
    It will reply with the following message:
    'Будь ласка, використовуйте фотографію, а не файл.'

    :param update: Update: Access the message that was sent by the user
    :param context: CallbackContext: Pass information between different parts of the program
    :return: None
    """
    user = update.message.from_user
    logger.info("%s: File warning", user.first_name)

    update.message.reply_text(
        'Будь ласка, використовуйте *фотографію*, а не файл\.',
        parse_mode='MarkdownV2',
    )


@under_maintenance
def main_keyboard_handler(update: Update, context: CallbackContext) -> None:
    """
    The main_keyboard_handler function is a callback function that is called
    in order to show MAIN_REPLY_KEYBOARD to the user.

    :param update: Update: Pass the current update to the function
    :param context: CallbackContext: Pass information between different parts of the program
    :return: None
    """
    user = update.message.from_user
    logger.info("%s: %s. Returning to the main menu", user.first_name, update.message.text)

    reply_keyboard = MAIN_REPLY_KEYBOARD

    if update.message.text not in ["Зрозуміло!", "Ні"]:
        update.message.reply_text(
            '☑️ Сканування завершено',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder='Оберіть опцію')
        )
    else:
        update.message.reply_text(
            'Гаразд',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder='Оберіть опцію')
        )


@under_maintenance
def instructions_handler(update: Update, context: CallbackContext) -> ConversationHandler.END:
    """
    The instructions_handler function is called whenever the user sends a message that matches
    the regular expression '^(Інструкції|/help)$'.
    It is used to send instructions to users. It also returns ConversationHandler.END


    :param update: Update: Access the message object
    :param context: CallbackContext: Send data back to the bot
    :return: ConversationHandler.END
    """
    user = update.message.from_user
    logger.info("%s: %s", user.first_name, update.message.text)

    reply_keyboard = [['Зрозуміло!']]

    pic = 'resources/How_to_scan.png'
    update.message.reply_photo(
        open(pic, 'rb'),
        caption='🔍 Щоб перевірити наявність штрих\-коду у базі даних \- надішліть мені фото '
                'пакування, де я можу *чітко* побачити штрихкод\.'
                '\n\n❗️ Аби додати новий медикамент до бази даних, оберіть опцію '
                '"Додати новий медикамент", або скористайтесь командою */add*'
                '\n\nТакож, при перевірці наявності *бот сам запропонує* Вам додати відсутній штрих\-код\.'
                '\n\n☑️ При додаванні вкажіть назву медикаменту\. *Не використовуйте спеціальних символів* у назві\.'
                '\n☑️ Далі вкажіть діючу речовину даного препарату\.'
                '\n☑️ Також додайте короткий опис *українською мовою*\.'
                '\n☑️ В кінці додайте фото упаковки медикаменту\. Якщо ви не хочете додавати фото, скористайтесь опцією'
                ' "Пропустити"\.️'
                '\n\n*Опис має містити:*'
                '\n*1\.* Основне застосування препарату \(показання до застосування\)'
                '\n*2\.* Протипоказання, якщо такі існують'
                '\n\n📩 Надіслати нам відгук можна обравши опцію "Надіслати відгук" із головного меню, '
                'або скориставшись командою */review*'
                '\n\n ↩️ Відмінити будь\-яку дію можна командою */cancel*'
                '\n\n 💬 Ви можете викликати це повідомлення у будь\-який момент, '
                'надіславши команду */help*',
        parse_mode='MarkdownV2',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію')
    )
    return ConversationHandler.END


@under_maintenance
def register(update: Update, context: CallbackContext) -> int:
    """
    The register_experimental function is a callback function for the /authorize command.
    It is used to register an admin user.
    The function first checks if the user is already registered as an admin, and if so,
    it cancels the registration process.
    If not, it sends a message asking for contact information (phone number and username)
    to be sent in order to move on to the next step of registration.

    :param update: Update: Store all the data related to the bot
    :param context: CallbackContext: Send data back to the conversation handler
    :return: The next state of conversation
    """
    user = update.message.from_user
    user_id = update.effective_user.id

    logger.info("%s: Started authorization", user.first_name)

    if admins_collection.count_documents({"user_id": user_id}) != 0:
        logger.info("Admin is already registered, cancelling adding process")

        reply_keyboard = MAIN_REPLY_KEYBOARD

        update.message.reply_text(
            text="☑️ Ви вже пройшли авторизацію. Вас зареєстровано як адміністратора",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                             resize_keyboard=True,)
        )
        return ConversationHandler.END

    contact_button = KeyboardButton(text="Надіслати контакт", request_contact=True)
    cancel_button = KeyboardButton(text="Скасувати реєстрацію")
    custom_keyboard = [[contact_button, cancel_button]]
    reply_markup = ReplyKeyboardMarkup(custom_keyboard,
                                       one_time_keyboard=True,
                                       resize_keyboard=True,
                                       input_field_placeholder='Реєстрація')

    update.message.reply_text(
        text='🔐 Реєстрація потрібна для забеспечення безпеки та зменшення кількості спаму'
             '\n\n✅ *Аби зареєструватись, оберіть опцію "Надіслати контакт"*'
             '\n\n↩️ Якщо ви не бажаєте реєструватись, оберіть опцію "Скасувати реєстрацію"'
             '\n\n❕ Зверніть увагу \- не пройшовши авторизацію ви *не зможете* вносити зміни до бази даних',
        parse_mode="MarkdownV2",
        reply_markup=reply_markup)

    return CONTACT


@under_maintenance
def get_admin_photo(update: Update, context: CallbackContext) -> int:
    """
    The get_admin_photo_experimental function is called when the user sends a contact.
    It stores the phone number in context.user_data, and then asks for a selfie photo to be sent.

    :param update: Update: Access the telegram api
    :param context: CallbackContext: Send data between functions
    :return: The next state of the concersation
    """
    logger.info("User send contact")

    reply_keyboard = [['Скасувати реєстрацію']]

    user_id = update.effective_user.id
    user = update.message.from_user

    context.user_data["phone_number"] = update.message.contact.phone_number
    logger.info("Storing admin phone number")

    context.user_data["ADMIN_INFO"] = update.message.contact.to_dict()
    logger.info("Storing admin contact info")

    update.message.reply_text(
        text='👤 *Тепер, надішліть, будь ласка, фото свого обличчя*'
             '\n\n😃 Не лякайтесь\! Ця процедура потрібна для підвищення безпеки під час війни\.'
             '\n\n🔒 Ми подбаємо про *конфіденційність та безпеку* ваших даних\.'
             ' Уся інформація зберігається на *захищених серверах*\. Ми *не будемо поширювати* її\.'
             '\n\n❕ Будь ласка, використовуйте реальну фотографію вашого обличчя\.'
             ' Фотографуйте при хорошому освітленні та старайтесь, щоб ваше обличчя було добре видно на фото\.'
             '\n\n❗️ Вам буде заблоковано доступ за використання несправжніх фотографій обличчя\.',
        parse_mode="MarkdownV2",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder='Надішліть фото'))

    return ADMIN_PHOTO


@under_maintenance
def add_admin(update: Update, context: CallbackContext) -> ConversationHandler.END:
    """
    The add_admin function checks whether user sent correct photo. If there are no faces or too many faces on photo
    it asks user to send it agait and returns the previous state of the conversation.
    If everything is fine it adds a new admin to the database.
    It takes in an update and context objects as arguments, and returns ConversationHandler.END
    to end the conversation after it is completed.

    :param update: Update: Pass the incoming update
    :param context: CallbackContext: Store data on the user's conversation flow
    :return: Conversationhandler.END
    """
    user_id = update.effective_user.id
    user = update.message.from_user

    reply_keyboard = MAIN_REPLY_KEYBOARD

    if update.message.photo:
        logger.info("User sent photo")

        id_img = update.message.photo[-1].file_id
        photo = context.bot.getFile(id_img)
        image_bytes = io.BytesIO()
        photo.download(out=image_bytes)
    else:
        return

    face = faces.find_faces(image_bytes.getvalue())

    if face == 'Too many faces':
        logger.info("Too many faces")

        update.message.reply_text(
            text='*На цій фотографії більше одного обличчя\.* '
                 '\n\nНадішліть, будь ласка, коректну фотографію',
            parse_mode="MarkdownV2"
        )

        return ADMIN_PHOTO
    elif face == 'Face not found':
        logger.info("Face not found")

        update.message.reply_text(
            text='*Мені не вдалося знайти обличчя на цій фотографії\.* '
                 '\n\nНадішліть, будь ласка, фотографію, де чітко видко ваше обличчя',
            parse_mode="MarkdownV2"
        )
        return ADMIN_PHOTO

    context.user_data["ADMIN_INFO"]["photo"] = image_bytes.getvalue()
    logger.info("Storing admin photo")

    context.user_data["ADMIN_INFO"]["registred_on"] = datetime.now().strftime("%d/%m/%Y, %H:%M:%S")

    post_id = admins_collection.insert_one(context.user_data["ADMIN_INFO"]).inserted_id
    logger.info("Added new admin successfully. Admin ID: {}".format(user_id))

    update.message.reply_photo(
        face,
        caption=f"✅ <b>{user.first_name}</b>, Вас успішно зареєстровано як адміністратора"
                f"\n\nВаш ID: <b>{user_id}</b>"
                f"\nВаш номер телефону: <b>{context.user_data['phone_number']}</b>",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію')
    )

    return ConversationHandler.END


@under_maintenance
def cancel_register(update: Update, context: CallbackContext) -> ConversationHandler.END:
    """
    The cancel_register function is called when the user sends a message with text 'Скасувати реєстрацію'
    It cancels the registration process and returns to main menu

    :param update: Update: Access the telegram api
    :param context: CallbackContext: Pass information from the handler to the callback function
    :return: ConversationHandler.END
    """
    reply_keyboard = MAIN_REPLY_KEYBOARD

    user = update.message.from_user
    logger.info("%s: Cancelled authorization", user.first_name)

    update.message.reply_text(
        text="☑️ Реєстрацію скасовано",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію')
    )
    return ConversationHandler.END


@under_maintenance
def start_report(update: Update, context: CallbackContext) -> int:
    """
    The start_report function is called when the user sends a message "Повідомити про проблему" to the bot.
    It is used to start report conversation with user.
    It checks if there is a drug code in context and if it's not 0, and it's present in the database, then it asks for
    a description of problem with drug from user.

    :param update: Update: Access the message object
    :param context: CallbackContext: Store data between calls
    :return: The next state of the conversation
    """
    reply_keyboard = [['Скасувати']]

    user = update.message.from_user
    logger.info("%s: Started report", user.first_name)

    drug_info = context.user_data.setdefault("DRUG_INFO", {})

    if drug_info.setdefault("code", '') == '':
        logger.info("Barcode is not scanned. Cancelling report")

        update.message.reply_text(
            text="⚠️️️ Немає про що повідомляти, спершу відскануйте штрих-код"
        )
        scan_handler(update=update, context=context)
        return ConversationHandler.END
    if get_db_query_result(drug_info["code"]) is None:
        logger.info("Barcode is missing from the DB. Cancelling report")

        update.message.reply_text(
            text="⚠️️️ Ви не можете повідомити про штрих-код, що відсутній у базі баних"
        )
        return cancel_report(update=update, context=context)

    logger.info("Asking for report description")

    update.message.reply_text(
        text=f"❗️️ *Ви повідомляєте про проблему з інформацією про медикамент зі штрих\-кодом "
             f"__{drug_info['code']}__*"
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

    :param update: Update: Pass on any information that has been passed to the handler
    :param context: CallbackContext: Store data in the context
    :return: Conversationhandler.END
    """
    report_description = update.message.text
    user_id = update.effective_user.id

    logger.info("User reported: %s", report_description)

    reply_keyboard = MAIN_REPLY_KEYBOARD

    drug_info = context.user_data["DRUG_INFO"]

    document = collection.find_one({"code": drug_info["code"]})
    if "report" in document:
        logger.info("Report for this document already exists. Concatenating")

        # number = int(re.findall('\[.*?]', document["report"])[-1].strip("[]"))
        collection.update_one({"code": drug_info["code"]},
                              {"$set": {"report": document["report"] + f", [{user_id}]: " + report_description}})
    else:
        collection.update_one({"code": drug_info["code"]}, {"$set": {"report": f"[{user_id}]: " + report_description}})

    logger.info("Reported successfully")

    update.message.reply_text(
        text="✅️ Дякуємо. Ви успішно повідомили про проблему",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію')
    )
    return ConversationHandler.END


@under_maintenance
def cancel_report(update: Update, context: CallbackContext) -> ConversationHandler.END:
    """
    The cancel_report function is called when the user cancels their report.
    It removes the drug code from context and returns to main menu.

    :param update: Update: Access the telegram api
    :param context: CallbackContext: Pass data between states
    :return: Conversationhandler.END
    """
    reply_keyboard = MAIN_REPLY_KEYBOARD

    logger.info("Report cancelled")

    update.message.reply_text(
        text="☑️ Відгук скасовано",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію')
    )

    context.user_data["DRUG_INFO"]["code"] = ''
    return ConversationHandler.END


@under_maintenance
def cancel_default(update: Update, context: CallbackContext) -> None:
    """
    The cancel_default function is called when the user presses the cancel button.
    It returns user to the main menu.

    :param update: Update: Access the message object
    :param context: CallbackContext: Access the context data of a callback query
    :return: None
    """
    reply_keyboard = MAIN_REPLY_KEYBOARD

    user = update.message.from_user
    logger.info("%s: /cancel. All operations cancelled", user.first_name)

    update.message.reply_text(
        text="ℹ️️ Усі операції скасовано",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію')
    )


@under_maintenance
def start_review(update: Update, context: CallbackContext) -> int:
    """
    The start_review function is called when the user sends a message to the bot
    with /review command. It will ask for review text.


    :param update: Update: Access the telegram api
    :param context: CallbackContext: Pass data between different parts of the program
    :return: The next state of the conversation
    """
    reply_keyboard = [['Скасувати']]

    user = update.message.from_user
    logger.info("User %s started review. Asking for a description", user.first_name)

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

    :param update: Update: Access the telegram api
    :param context: CallbackContext: Access data,
    :return: Conversationhandler.END
    """
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

            msg['Subject'] = "User response for MSB DB Management Bot"
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

        logger.info("User %s reviewed successfully", user.first_name)

        update.message.reply_text(
            text="*Щиро дякуємо* ❤️ "
                 "\n\nВаш відгук надіслано\. Ми обовʼязково розглянем його найближчим часом",
            parse_mode="MarkdownV2",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                             one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder='Оберіть опцію')
        )
    except Exception as e:
        logger.warning("Something went wrong during review")
        logger.warning(e)

        update.message.reply_text(
            text="*Упс\.\.\. Щось пішло не так* 😞️"
                 "\n\nСпробуйте ще раз, або звʼяжіться з адміністратором бота\.",
            parse_mode="MarkdownV2",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                             one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder='Оберіть опцію')
        )

    return ConversationHandler.END


@under_maintenance
@superuser
def statistics_for_user(update: Update, context: CallbackContext) -> int:
    """
    The statistics_for_user function is used to get statistics for a specific user.
    It takes the update and context objects as parameters, then asks the user to input an ID of a user.

    :param update: Update: Access the context of the conversation
    :param context: CallbackContext: Pass data between the callback functions
    :return: The user's id
    """
    reply_keyboard = [['Скасувати']]

    logger.info("/statistics. Asking for the ID")

    update.message.reply_text(
        text="Введіть ID користувача для отримання статистики",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію')
    )
    return STATISTICS


def get_admin_info(user_id):
    """
    The get_admin_info function returns the formatted admin information for a given user_id.

    :param user_id: Find the user in the admins collection
    :return: A dictionary with the admin's information
    """
    logger.info("Getting admin info")

    admin_info = admins_collection.find_one({"user_id": user_id}, {"_id": 0, "photo": 0})
    return "\nІнформація: " + json.dumps(admin_info, sort_keys=False, ensure_ascii=False, indent=4)


def retrieve_admin_photo(user_id):
    """
    EXPERIMENTAL FUNCTION
    """
    logger.info("Getting admin photo")

    admin_info = admins_collection.find_one({"user_id": user_id}, {"_id": 0, "photo": 1})
    return admin_info["photo"]


def get_banned_info(user_id):
    """
    The get_banned_info function returns a dictionary of information about the user_id that is passed to it.

    :param user_id: Find the user in the blacklist database
    :return: The information about the user who has been banned
    """
    logger.info("Getting banned info")

    banned_info = blacklist.find_one({"user_id": user_id}, {"_id": 0})
    return "\nІнформація: " + json.dumps(banned_info, sort_keys=False, ensure_ascii=False, indent=4)


def get_reports_by_user_quantity(user_id):
    """
    EXPERIMENTAL FUNCTION
    """
    logger.info("Getting admin info")

    reported_medicine = collection.find({"report": {'$exists': 'true'}})

    reports_quantity = 0

    for medicine in reported_medicine:
        if f"[{user_id}]" in medicine["report"]:
            reports_quantity += 1
        else:
            continue

    return reports_quantity


@under_maintenance
def show_statistics(update: Update, context: CallbackContext) -> int or None:
    """
    The show_statistics function is used to show the statistics of a user.
    It returns send files state of the conversation.

    :param update: Update: Pass the incoming update
    :param context: CallbackContext: Pass data between callbacks
    :return: The next state of conversation
    """
    reply_keyboard = [['Завершити']]

    entered_id = int(update.message.text)
    context.user_data["entered_id"] = entered_id

    try:
        logger.info("Collecting user info by ID")

        documents_quantity = collection.count_documents({"user_id": entered_id})
        reports_on_user = collection.count_documents({"user_id": entered_id, "report": {'$exists': 'true'}})
        is_admin = admins_collection.count_documents({"user_id": entered_id}) > 0
        is_banned = blacklist.count_documents({"user_id": entered_id}) > 0

    except Exception as e:
        logger.warning("Something went wrong during statistics collection")
        logger.warning(e)

        update.message.reply_text(
            text=f"Щось пішло не так: \n\n{e}",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                             one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder='Оберіть опцію')
        )
    else:
        if documents_quantity == 0 and not is_admin and not is_banned:
            logger.info("There's no statistics for {}".format(entered_id))

            update.message.reply_text(
                text="ℹ️ Статистика для користувача *{}* відсутня".format(entered_id),
                parse_mode="MarkdownV2",
                reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                                 one_time_keyboard=True,
                                                 resize_keyboard=True,
                                                 input_field_placeholder='Оберіть опцію')
            )
            return

        reports_by_user = get_reports_by_user_quantity(entered_id)

        if is_banned:
            banned_info = get_banned_info(entered_id)
        else:
            banned_info = ''

        if reports_on_user > 0:
            reply_keyboard[0].insert(0, 'Отримати список скарг')

        if documents_quantity > 0:
            reply_keyboard[0].insert(0, 'Отримати додані медикаменти')

        logger.info("Retrieving statistics")

        if is_admin:
            admin_info = get_admin_info(entered_id)

            update.message.reply_photo(
                retrieve_admin_photo(entered_id),
                caption="Статистика для користувача <b>{}</b>\n\n️".format(entered_id) +
                f"<b>Додано медикаментів</b>: {documents_quantity}"
                f"\n<b>Скарг, поданих на цього користувача</b>: {reports_on_user}"
                f"\n<b>Скарг, поданих цим користувачем</b>: {reports_by_user}"
                f"\n<b>Чи є адміністратором</b>: {is_admin}{admin_info}"
                f"\n<b>Заблоковано</b>: {is_banned}{banned_info}",
                parse_mode="HTML",
                reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                                 one_time_keyboard=True,
                                                 resize_keyboard=True,
                                                 input_field_placeholder='Оберіть опцію')
            )
        else:
            update.message.reply_text(
                text="Статистика для користувача <b>{}</b>\n\n️".format(entered_id) +
                     f"<b>Додано медикаментів</b>: {documents_quantity}"
                     f"\n<b>Скарг, поданих на цього користувача</b>: {reports_on_user}"
                     f"\n<b>Скарг, поданих цим користувачем</b>: {reports_by_user}"
                     f"\n<b>Чи є адміністратором</b>: {is_admin}"
                     f"\n<b>Заблоковано</b>: {is_banned}{banned_info}",
                parse_mode="HTML",
                reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                                 one_time_keyboard=True,
                                                 resize_keyboard=True,
                                                 input_field_placeholder='Оберіть опцію')
            )

    context.user_data["reply_keyboard"] = reply_keyboard
    return SEND_FILES


@under_maintenance
def send_files(update: Update, context: CallbackContext) -> ConversationHandler.END:
    """
    The send_files function is called when the user sends a message with text 'Отримати додані медикаменти' or
    'Отримати список скарг'. It takes in an update and a context as parameters.
    The function first checks if the entered_id is valid, and then it creates two files: one for medicine data,
    another for report data. Then it sends these files to the user.

    :param update: Update: Pass on the update to the function
    :param context: CallbackContext: Store data on the conversation between functions
    :return: Conversationhandler.END
    """
    entered_id = context.user_data["entered_id"]

    reply_keyboard = context.user_data["reply_keyboard"]

    if update.message.text == 'Отримати додані медикаменти':
        medicine_by_user_id = list(
            collection.find({"user_id": entered_id}, {"_id": 0, "photo": 0, "report": 0, "user_id": 0}))

        with open('data.json', 'w', encoding='utf-8') as f:
            json.dump(medicine_by_user_id, f, sort_keys=False, ensure_ascii=False, indent=4)

        logger.info("Sending medicine file")

        update.message.reply_document(
            document=open('data.json', 'rb'),
            filename=f"Statistics_for_{entered_id}.json",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                             one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder='Оберіть опцію')
        )
        os.remove('data.json')

    if update.message.text == 'Отримати список скарг':
        medicine_by_user_id = list(collection.find({"user_id": entered_id, "report": {'$exists': 'true'}},
                                                   {"_id": 0, "photo": 0, "user_id": 0, "active_ingredient": 0,
                                                    "description": 0}))

        with open('data.json', 'w', encoding='utf-8') as f:
            json.dump(medicine_by_user_id, f, sort_keys=False, ensure_ascii=False, indent=4)

        logger.info("Sending reports file")

        update.message.reply_document(
            document=open('data.json', 'rb'),
            filename=f"Reports_for_{entered_id}.json",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                             one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder='Оберіть опцію')
        )
        os.remove('data.json')

    return SEND_FILES


@under_maintenance
def cancel_statistics(update: Update, context: CallbackContext) -> ConversationHandler.END:
    """
    The cancel_ban function is called when the user presses the cancel button.
    It sends a message saying that getting statistics process has been canceled
    and returns user to the main menu.

    :param update: Update: Access the telegram api
    :param context: CallbackContext: Pass data between the callback functions
    :return: Conversationhandler.END
    """
    reply_keyboard = MAIN_REPLY_KEYBOARD

    logger.info("Ended collecting statistics")

    update.message.reply_text(
        text="☑️ Отримання статистики завершено",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію')
    )
    return ConversationHandler.END


@under_maintenance
@superuser
def start_ban(update: Update, context: CallbackContext) -> int:
    """
    The start_ban function is called when the user sends a message to the bot
    that contains /ban command. The usage if this function is restricted to only for superusers.
    The function will ask user to send ID of the user he wants to ban

    :param update: Update: Access the data received by the bot
    :param context: CallbackContext: Pass the context of a callback query
    :return: The id of the user to be banned
    """
    logger.info("/ban. Asking for the ID")

    reply_keyboard = [['Скасувати']]

    update.message.reply_text(
        text="Введіть ID користувача для блокування",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію')
    )
    return REASON


@under_maintenance
def get_reason(update: Update, context: CallbackContext) -> int:
    """
    The get_reason function is used to get the reason for which a user is blocked.
    It takes in an update and a context as parameters, and stores user ID in the context.user_data.
    Finalli it returns the ban state of the conversation

    :param update: Update: Access the message that was sent by the user
    :param context: CallbackContext: Store data in the context
    :return: The reason for blocking the user
    """
    reply_keyboard = [['Скасувати']]

    context.user_data["user_id"] = int(update.message.text)

    logger.info("Asking for a ban reason")

    update.message.reply_text(
        text="Введіть причину блокування блокування",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію')
    )
    return BAN


@under_maintenance
def ban_user(update: Update, context: CallbackContext) -> ConversationHandler.END:
    """
    The ban_user function takes in an update and a context as parameters, and returns ConversationHandler.END.
    It inserts banned user info to the blacklist collection of the database and sends a confirmation message.

    :param update: Update: Access the message object, which contains information about the user and
    :param context: CallbackContext: Pass data between callbacks
    :return: Conversationhandler.END
    """
    reply_keyboard = MAIN_REPLY_KEYBOARD

    reason = update.message.text

    post = {
        "user_id": context.user_data["user_id"],
        "reason": reason,
        "banned_on": datetime.now().strftime("%d/%m/%Y, %H:%M:%S")
    }

    post_id = blacklist.insert_one(post).inserted_id

    logger.info("Banned successfully. ID: {}".format(context.user_data["user_id"]))

    update.message.reply_text(
        text="✅ Користувача успішно заблоковано",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію')
    )
    return ConversationHandler.END


@under_maintenance
def cancel_ban(update: Update, context: CallbackContext) -> ConversationHandler.END:
    """
    The cancel_ban function is called when the user presses the cancel button.
    It removes a user ID from the context.user_data and sends them a message
    saying that ban process has been canceled. Then returns user to the main menu.

    :param update: Update: Access the telegram api
    :param context: CallbackContext: Pass data between the callback functions
    :return: Conversationhandler.END
    """
    logger.info("Ban cancelled")

    reply_keyboard = MAIN_REPLY_KEYBOARD

    context.user_data["user_id"] = 0

    update.message.reply_text(
        text="☑️ Блокування користувача скасовано",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію')
    )
    return ConversationHandler.END


@superuser
@under_maintenance
def send_plot(update: Update, context: CallbackContext) -> None:
    """
    The send_plot function sends a plot of the number of drugs per country to the user.


    :param update: Update: Access the message object
    :param context: CallbackContext: Send messages to the user
    :return: None
    """
    logger.info("Sending countries statistics plot")

    keyboard = [[InlineKeyboardButton(text="Інтеракивна карта",
                                      web_app=WebAppInfo(url='https://countries-map.herokuapp.com/'))]]

    context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_PHOTO)

    quantities = statistics.get_quantities('resources/country_codes.json')
    not_empty_countries = statistics.get_not_empty_countries(quantities)

    plot = statistics.get_bar_chart(not_empty_countries)

    img_buf = io.BytesIO()
    plot.savefig(img_buf, format='png')

    update.message.reply_photo(
        img_buf.getvalue(),
        caption="*Статистика по країнах на основі колекції медикаментів*",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup(keyboard,
                                          resize_keyboard=True,)
    )


def main() -> None:
    updater = Updater(config['Database']['token'])
    dispatcher = updater.dispatcher

    scan = MessageHandler(Filters.regex('^(Перевірити наявність|/scan|Ще раз)$'), scan_handler)
    start = CommandHandler('start', start_handler)
    cancel_echo = CommandHandler('cancel', cancel_default)
    decoder = MessageHandler(Filters.photo, retrieve_scan_results)
    decoder_str = MessageHandler(Filters.regex('^\d{13}$'), retrieve_scan_results)
    not_file = MessageHandler(Filters.attachment, file_warning)
    end_scan = MessageHandler(Filters.regex('^(Завершити сканування|Відмінити сканування|Зрозуміло!|Ні)$'),
                              main_keyboard_handler)
    instructions = MessageHandler(Filters.regex('^(Інструкції|/help)$'), instructions_handler)

    add_handler = ConversationHandler(
        entry_points=[MessageHandler(Filters.regex('^(Так|Додати новий медикамент|/add)$'), start_adding)],
        states={
            NAME: [
                MessageHandler(Filters.photo & ~Filters.command & ~Filters.text("Скасувати додавання"), get_name)
            ],
            INGREDIENT: [
                MessageHandler(Filters.text & ~Filters.command & ~Filters.text("Скасувати додавання"),
                               get_active_ingredient)
            ],
            ABOUT: [
                MessageHandler(Filters.text & ~Filters.command & ~Filters.text("Скасувати додавання"), get_about),
            ],
            PHOTO: [
                MessageHandler(Filters.text & ~Filters.command & ~Filters.text("Скасувати додавання"), get_photo),
                MessageHandler(Filters.regex('^(Пропустити)$')
                               & ~Filters.command & ~Filters.text("Скасувати додавання"), skip_photo)
            ],
            CHECK: [
                MessageHandler(Filters.photo & ~Filters.command & ~Filters.text("Скасувати додавання"), check_info),
                MessageHandler(Filters.regex('^(Пропустити)$')
                               & ~Filters.command & ~Filters.text("Скасувати додавання"), check_info)
            ],
            INSERT: [
                MessageHandler(Filters.text & ~Filters.text("Скасувати додавання"), insert_to_db)
            ],
            CHANGE_INFO: [
                MessageHandler(Filters.regex('^(Назва|Діюча речовина|Опис)$') & ~Filters.text("Скасувати додавання"),
                               change_info)
            ],
            REWRITE: [
                MessageHandler(Filters.text & ~Filters.text("Скасувати додавання"),
                               rewrite)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel),
                   MessageHandler(Filters.text("Скасувати додавання"), cancel),
                   CommandHandler("help", instructions_handler)]
    )

    register_handler = ConversationHandler(
        entry_points=[CommandHandler('authorize', register)],
        states={
            CONTACT: [
                MessageHandler(Filters.contact & ~Filters.command, get_admin_photo)
            ],
            ADMIN_PHOTO: [
                MessageHandler(Filters.photo & ~Filters.command, add_admin)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel_register),
                   MessageHandler(Filters.text("Скасувати реєстрацію"), cancel_register)]
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

    user_statistics = ConversationHandler(
        entry_points=[CommandHandler('statistics', statistics_for_user)],
        states={
            STATISTICS: [
                MessageHandler(Filters.text & ~Filters.command & ~Filters.text("Скасувати"), show_statistics)
            ],
            SEND_FILES: [
                MessageHandler(Filters.text & ~Filters.command & ~Filters.regex('^(Скасувати|Завершити)$'), send_files)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel_statistics),
                   MessageHandler(Filters.regex('^(Скасувати|Завершити)$'), cancel_statistics)]
    )

    ban = ConversationHandler(
        entry_points=[CommandHandler('ban', start_ban)],
        states={
            REASON: [
                MessageHandler(Filters.text & ~Filters.command & ~Filters.text("Скасувати"), get_reason)
            ],
            BAN: [
                MessageHandler(Filters.text & ~Filters.command & ~Filters.text("Скасувати"), ban_user)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel_ban),
                   MessageHandler(Filters.text("Скасувати"), cancel_ban)]
    )

    countries_statistics = CommandHandler('countries', send_plot)

    dispatcher.add_handler(user_statistics)
    dispatcher.add_handler(countries_statistics)
    dispatcher.add_handler(register_handler)
    dispatcher.add_handler(report_handler)
    dispatcher.add_handler(review_handler)
    dispatcher.add_handler(add_handler)
    dispatcher.add_handler(start)
    dispatcher.add_handler(scan)
    dispatcher.add_handler(decoder)
    dispatcher.add_handler(not_file)
    dispatcher.add_handler(end_scan)
    dispatcher.add_handler(instructions)
    dispatcher.add_handler(cancel_echo)
    dispatcher.add_handler(ban)

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
