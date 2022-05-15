"""
Author: Andrew Yaroshevych
Version: 2.5.0
"""
import re

from telegram import ReplyKeyboardMarkup, Update, KeyboardButton
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, ConversationHandler, CallbackContext

from PIL import Image
from pyzbar.pyzbar import decode
from email.message import EmailMessage

import os
import io
import logging
import smtplib
import configparser
from functools import wraps

from pymongo import MongoClient

import validators

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
CONTACT = 1
REPORT = 1
REVIEW = 1

DRUG_INFO = {
    "name": "",
    "active_ingredient": "",
    "description": "",
    "code": "",
    "photo": b'',
    "user_id": 0
}

MAIN_REPLY_KEYBOARD = [['Перевірити наявність', 'Додати новий медикамент', 'Інструкції', 'Надіслати відгук']]


def restricted(func):
    @wraps(func)
    def wrapped(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        if blacklist.count_documents({"user_id": user_id}) != 0:
            logger.info("User banned")
            blocked_user = blacklist.find_one({"user_id": user_id}, {"_id": 0})

            update.message.reply_text(
                "❌ *Вас заблоковано\.* ID: *{}*".format(user_id) +
                f"\n\n*Причина*: {blocked_user['reason']} "
                "\n\nЯкщо Ви вважаєте, що це помилка \- зверніться до адміністратора бота",
                parse_mode='MarkdownV2',
            )
            return
        if admins_collection.count_documents({"user_id": user_id}) != 0:
            logger.info("Admin is already registered")
        else:
            update.message.reply_text(
                "❌ Ви не можете проводити операцій з базою даних\. \n\nВаш ID *{}* не зареєстровано "
                "як адміністратора"
                "\n\nАби зареєструватись, виконайте команду */authorize*".format(user_id),
                parse_mode='MarkdownV2',
            )
            logger.info("Unauthorized access denied for {}".format(user_id))
            return
        return func(update, context, *args, **kwargs)

    return wrapped


def start_handler(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    logger.info("%s: %s", user.first_name, update.message.text)

    reply_keyboard = MAIN_REPLY_KEYBOARD

    update.message.reply_text(
        '*Привіт\! Я бот для адміністування бази даних Telegram MSB\.*'
        '\n\nОберіть опцію, будь ласка\.',
        parse_mode='MarkdownV2',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію')
    )


def scan_handler(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    logger.info("%s: %s. Scan started", user.first_name, update.message.text)

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
        logger.info("Database quired. Retrieving results")
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


def retrieve_scan_results(update: Update, context: CallbackContext) -> None:
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
        logger.info("Trying to decode")

        result = decode(Image.open('code.png'))
        code_str = result[0].data.decode("utf-8")
        DRUG_INFO["code"] = code_str

        reply_keyboard = [['Завершити сканування', 'Повідомити про проблему']]
        reply_keyboard2 = [['Так', 'Ні']]

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
                caption='✅ Штрих-код ' + '<b>' + code_str + '</b>' +
                        ' наявний у моїй базі даних:\n\n' +
                        retrieve_db_query(code_str),
                quote=True
            )

            os.remove("retrieved_image.jpg")
        elif db_check_availability(code_str):
            logger.info("The barcode is present in the database but photo is missing")

            update.message.reply_text(
                parse_mode='HTML',
                reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                                 resize_keyboard=True,
                                                 input_field_placeholder='Продовжуйте'),
                text='✅ Штрих-код ' + '<b>' + code_str + '</b>' +
                     ' наявний у моїй базі даних:\n\n' +
                     retrieve_db_query(code_str) +
                     '\n\n⚠️ Фото відсутнє',
                quote=True
            )
        else:
            logger.info("The barcode is missing from the database. Asking to add info")

            update.message.reply_text(
                parse_mode='HTML',
                reply_markup=ReplyKeyboardMarkup(reply_keyboard2, one_time_keyboard=True,
                                                 resize_keyboard=True,
                                                 input_field_placeholder='Продовжуйте'),
                text='❌ Штрих-код ' + '<b>' + code_str + '</b>' +
                     ' відсутній у моїй базі даних.\n\n' +
                     'Чи бажаєте Ви додати інформацію про цей медикамент?',
                quote=True
            )

    except IndexError as e:
        logger.info("Failed to scan")

        reply_keyboard = [['Ще раз', 'Інструкції']]

        update.message.reply_text(
            text="*На жаль, сталася помилка ❌ *"
                 "\nСпробуйте ще раз, або подивіться інструкції до сканування та "
                 "переконайтесь, що робите все правильно\.",
            quote=True,
            parse_mode='MarkdownV2',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                             one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder='Оберіть опцію')
        )
    finally:
        logger.info("Operation ended. Deleting barcode image")
        os.remove("code.png")


@restricted
def start_adding(update: Update, context: CallbackContext) -> int:
    user = update.message.from_user
    logger.info("User %s started adding process", user.first_name)

    reply_keyboard = [['Скасувати додавання']]

    if update.message.text != "Так" and not update.message.photo:
        logger.info("Photo is missing, asking to scan one")

        update.message.reply_text(
            'Добре.\nСпершу, надішліть фото штрих-коду',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                             one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder='Надішліть фото')
        )

        return NAME
    elif not update.message.photo:
        logger.info("Photo already scanned, asking for a name")
        update.message.reply_text(
            'Добре.\nСпершу, надішліть назву медикаменту',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                             one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder='Введіть назву')
        )
        return INGREDIENT


def get_name(update: Update, context: CallbackContext) -> int or None:
    logger.info("Storing photo")

    user = update.message.from_user
    reply_keyboard = [['Скасувати додавання']]

    if update.message.photo:
        id_img = update.message.photo[-1].file_id
    else:
        return

    foto = context.bot.getFile(id_img)
    foto.download('code.png')

    try:
        result = decode(Image.open('code.png'))
        code_str = result[0].data.decode("utf-8")
        if db_check_availability(code_str):
            logger.info("This barcode already exists. Cancelling adding process")

            update.message.reply_text(
                text="⚠️ Медикамент з таким штрих-кодом вже присутній у базі даних.",
                quote=True,
                reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                                 one_time_keyboard=True,
                                                 resize_keyboard=True)
            )

            return cancel(update=update, context=context)
        else:
            logger.info("Barcode scanned successfully")
            DRUG_INFO["code"] = code_str
            logger.info("Storing barcode info")
            update.message.reply_text(
                text="Штрих-код відскановано успішно ✅",
                quote=True,
                reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                                 one_time_keyboard=True,
                                                 resize_keyboard=True)
            )

    except IndexError as e:
        logger.info("Failed to scan")

        update.message.reply_text(
            text="*На жаль, сталася помилка\. Мені не вдалось відсканувати штрих\-код ❌ *"
                 "\nПереконайтесь, що робите все правильно та надішліть фото ще раз, "
                 "або подивіться інструкції до сканування за допомогою команди */help*",
            quote=True,
            parse_mode='MarkdownV2',
        ),

        return start_adding(update=update, context=context)
    finally:
        os.remove("code.png")

    logger.info("Asking for a name")
    update.message.reply_text(
        text='Надішліть назву медикаменту',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder="Введіть назву")
    )

    return INGREDIENT


def get_active_ingredient(update: Update, context: CallbackContext) -> int:
    logger.info("Entered name of the drug: %s", update.message.text)

    user = update.message.from_user
    reply_keyboard = [['Скасувати додавання']]

    name = update.message.text
    if validators.check_name(name) is None:
        logger.info("Name is not correct, asking to retry", update.message.text)

        update.message.reply_text(
            text='*Вкажіть, будь ласка, корректну назву*'
                 f'\n\nПоточна назва "{name}" містить тільки цифри',
            parse_mode="MarkdownV2",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder="Повторіть ввід"),
        )
        return INGREDIENT

    DRUG_INFO["name"] = name

    logger.info("Asking for an active ingredient")

    update.message.reply_text(
        text='Вкажіть, будь ласка, діючу речовину медикаменту',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder="Введіть діючу речовину"),
    )

    return ABOUT


def get_about(update: Update, context: CallbackContext) -> int:
    logger.info("Entered active ingredient of the drug: %s", update.message.text)

    user = update.message.from_user
    reply_keyboard = [['Скасувати додавання']]

    active_ingredient = update.message.text
    if validators.check_active_ingredient(active_ingredient) is None:
        logger.info("Active ingredient is not correct, asking to retry", update.message.text)

        update.message.reply_text(
            text='*Вкажіть, будь ласка, корректну назву діючої речовини*'
                 f'\n\nПоточна назва діючої речовини "{active_ingredient}" містить тільки цифри',
            parse_mode="MarkdownV2",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder="Повторіть ввід"),
        )
        return ABOUT

    DRUG_INFO["active_ingredient"] = active_ingredient

    logger.info("Asking for a description")

    update.message.reply_text(
        text='Тепер надішліть короткий опис даного препарату',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder="Введіть опис")
    )

    return PHOTO


def get_photo(update: Update, context: CallbackContext) -> int:
    logger.info("Entered description: %s. Asking for a photo", update.message.text)

    user = update.message.from_user
    reply_keyboard = [['Скасувати додавання', 'Пропустити']]

    description = update.message.text
    if validators.check_description(description) != description:
        logger.info("Description is not correct, asking to retry", update.message.text)

        update.message.reply_text(
            text=f'Вкажіть, будь ласка, опис українською мовою'
                 f'\n\nПоточна мова: {validators.check_description(description)}',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder="Повторіть ввід"),
        )
        return PHOTO

    DRUG_INFO["description"] = description

    update.message.reply_text(
        text='Також, надішліть фото передньої сторони упаковки медикаменту.'
             '\n\n(Не рекомендується) Натисніть "Пропустити", якщо не хочете додавати фото',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder="Надішліть фото")
    )
    return CHECK


def skip_photo(update: Update, context: CallbackContext) -> int:
    return CHECK


def check_info(update: Update, context: CallbackContext) -> int:
    logger.info("Now checking info")

    user = update.message.from_user

    output = f"<b>Назва</b>: {DRUG_INFO['name']} " \
             f"\n<b>Діюча речовина</b>: {DRUG_INFO['active_ingredient']} " \
             f"\n<b>Опис</b>: {DRUG_INFO['description']} "

    reply_keyboard = [['Так, додати до бази даних', 'Змінити інформацію', 'Ні, скасувати']]

    if update.message.photo:
        id_img = update.message.photo[-1].file_id
        photo = context.bot.getFile(id_img)
        photo.download('photo.jpg')

        img = Image.open("photo.jpg")
        image_bytes = io.BytesIO()
        img.save(image_bytes, format='JPEG')

        DRUG_INFO["photo"] = image_bytes.getvalue()

        update.message.reply_photo(
            open("photo.jpg", 'rb'),
            caption='<b>Введена інформація:</b>\n\n' + output +
                    '\n\n❓Ви точно бажаєте додати її до бази даних?',
            parse_mode='HTML',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder="Оберіть опцію")
        )
        os.remove("photo.jpg")
    elif update.message.text and DRUG_INFO["photo"] == b'':
        update.message.reply_text(
            text='<b>Введена інформація:</b>\n\n' +
                 '⚠️ Фото відсутнє\n' + output +
                 '\n\n❓Ви точно бажаєте додати її до бази даних?',
            parse_mode='HTML',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder="Оберіть опцію")
        )
    else:
        img = Image.open(io.BytesIO(DRUG_INFO['photo']))
        img.save("photo.jpg")

        update.message.reply_photo(
            open("photo.jpg", 'rb'),
            caption='<b>Введена інформація:</b>\n\n' + output +
                    '\n\n❓Ви точно бажаєте додати її до бази даних?',
            parse_mode='HTML',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder="Оберіть опцію")
        )
        os.remove("photo.jpg")
    return INSERT


def insert_to_db(update: Update, context: CallbackContext) -> int or ConversationHandler.END:
    user = update.message.from_user

    reply_keyboard = MAIN_REPLY_KEYBOARD

    if update.message.text == 'Так, додати до бази даних':
        user_id = update.effective_user.id
        DRUG_INFO["user_id"] = user_id

        post_id = collection.insert_one(DRUG_INFO).inserted_id
        logger.info("Checked info. Added successfully")
        update.message.reply_text(
            text='✅ Препарат успішно додано до бази даних',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder="Оберіть опцію")
        )

        logger.info("Clearing info: %s", DRUG_INFO)
        DRUG_INFO["name"] = ""
        DRUG_INFO["active_ingredient"] = ""
        DRUG_INFO["description"] = ""
        DRUG_INFO["code"] = ""
        DRUG_INFO["photo"] = b''
        DRUG_INFO["user_id"] = 0
        logger.info("Cleared")

    elif update.message.text == 'Змінити інформацію':
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


def change_info(update: Update, context: CallbackContext) -> int:
    reply_keyboard = [['Скасувати додавання']]

    if update.message.text == 'Назва':
        context.user_data["change"] = "name"
        update.message.reply_text(
            text='Добре, надішліть нову назву',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder="Оберіть опцію")
        )
    if update.message.text == 'Діюча речовина':
        context.user_data["change"] = "active_ingredient"
        update.message.reply_text(
            text='Добре, надішліть нову назву діючої речовини',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder="Оберіть опцію")
        )
    if update.message.text == 'Опис':
        context.user_data["change"] = "description"
        update.message.reply_text(
            text='Добре, надішліть новий опис',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder="Оберіть опцію")
        )

    return REWRITE


def rewrite(update: Update, context: CallbackContext) -> check_info:
    if context.user_data["change"] == "name":
        DRUG_INFO["name"] = update.message.text
        return check_info(update=update, context=context)
    if context.user_data["change"] == "active_ingredient":
        DRUG_INFO["active_ingredient"] = update.message.text
        return check_info(update=update, context=context)
    if context.user_data["change"] == "description":
        DRUG_INFO["description"] = update.message.text
        return check_info(update=update, context=context)


def cancel(update: Update, context: CallbackContext) -> ConversationHandler.END:
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


def file_warning(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    logger.info("%s: File warning", user.first_name)

    reply_keyboard = [['Ще раз']]

    update.message.reply_text(
        'Будь ласка, використовуйте *фотографію*, а не файл\.',
        parse_mode='MarkdownV2',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder='Надішліть фото')
    )


def main_keyboard_handler(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    logger.info("%s: %s", user.first_name, update.message.text)

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


def instructions_handler(update: Update, context: CallbackContext) -> ConversationHandler.END:
    user = update.message.from_user
    logger.info("%s: %s", user.first_name, update.message.text)

    reply_keyboard = [['Зрозуміло!']]

    pic = 'resources/How_to_scan.png'
    update.message.reply_photo(
        open(pic, 'rb'),
        caption='🔍 Щоб перевірити наявність штрих\-коду у базі даних \- надішліть мені фото '
                'пакування, де я можу *чітко* побачити штрихкод\.'
                '\n\n✏️ Ви можете надсилати одразу декілька фотографій\.'
                '\n\n❗️ Аби додати новий медикамент до бази даних, оберіть опцію '
                '"Додати новий медикамент", або скористайтесь командою */add*'
                '\n\nТакож, операція додавання може бути виконана'
                ' при перевірці наявності \- *бот сам запропонує* Вам додати відсутній штрих\-код\.'
                '\n\n☑️ При додаванні вкажіть назву медикаменту\. *Не використовуйте спеціальних символів* у назві\.'
                '\n☑️ Далі вкажіть діючу речовину даного препарату *українською мовою*\.'
                '\n☑️ Також додайте короткий опис *українською мовою*\. '
                '\n\n*Опис має містити:*'
                '\n*1\.* Основне застосування препарату \(показання до застосування\)'
                '\n*2\.* Протипоказання, якщо такі існують'
                '\n\n📩 Надіслати нам відгук можна обравши опцію "Надіслати відгук" із головного меню,'
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


def register(update: Update, context: CallbackContext) -> int:
    user = update.message.from_user
    user_id = update.effective_user.id

    logger.info("%s: Started authorization", user.first_name)

    if admins_collection.count_documents({"user_id": user_id}) != 0:
        logger.info("Admin is already registered, cancelling adding process")

        reply_keyboard = MAIN_REPLY_KEYBOARD

        update.message.reply_text(
            text="☑️ Ви вже пройшли авторизацію",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard)
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
             '\n❕ Зверніть увагу \- не пройшовши авторизацію ви *не зможете* вносити зміни до бази даних',
        parse_mode="MarkdownV2",
        reply_markup=reply_markup)

    return CONTACT


def add_admin(update: Update, context: CallbackContext) -> ConversationHandler.END:
    logger.info("User send contact")

    reply_keyboard = MAIN_REPLY_KEYBOARD

    post_id = admins_collection.insert_one(update.message.contact.to_dict()).inserted_id
    user_id = update.effective_user.id
    user = update.message.from_user

    phone_number_markdown = update.message.contact.phone_number.replace('+', '\+')
    update.message.reply_text(
        text=f"✅ *{user.first_name}*, Вас успішно зареєстровано як адміністратора"
             f"\n\nВаш ID: *{user_id}*"
             f"\nВаш номер телефону: *{phone_number_markdown}*",
        parse_mode="MarkdownV2",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію')
    )

    logger.info("Added new admin successfully. Admin ID: {}".format(user_id))
    return ConversationHandler.END


def cancel_register(update: Update, context: CallbackContext):
    reply_keyboard = MAIN_REPLY_KEYBOARD

    update.message.reply_text(
        text="☑️ Реєстрацію скасовано",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію')
    )
    return ConversationHandler.END


def start_report(update: Update, context: CallbackContext) -> int:
    reply_keyboard = [['Скасувати']]
    if DRUG_INFO["code"] == "":
        update.message.reply_text(
            text="⚠️️️ Немає про що повідомляти, спершу відскануйте штрих-код"
        )
        scan_handler(update=update, context=context)
        return ConversationHandler.END
    if db_check_availability(DRUG_INFO["code"]) is False:
        update.message.reply_text(
            text="⚠️️️ Ви не можете повідомити про штрих-код, що відсутній у базі баних"
        )
        return cancel_report(update=update, context=context)

    update.message.reply_text(
        text=f"❗️️ *Ви повідомляєте про проблему з інформацією про медикамент зі штрих\-кодом __{DRUG_INFO['code']}__*"
             "\n\nНадішліть, будь ласка, короткий опис проблеми",
        parse_mode="MarkdownV2",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder='Опис проблеми')
    )
    return REPORT


def add_report_description(update: Update, context: CallbackContext) -> ConversationHandler.END:
    report_description = update.message.text
    logger.info("User reported: %s", report_description)

    reply_keyboard = MAIN_REPLY_KEYBOARD

    document = collection.find_one({"code": DRUG_INFO["code"]})
    if "report" in document:
        number = int(re.findall('\[.*?]', document["report"])[-1].strip("[]"))
        collection.update_one({"code": DRUG_INFO["code"]},
                              {"$set": {"report": document["report"] + f",\n[{number + 1}]: " + report_description}})
    else:
        collection.update_one({"code": DRUG_INFO["code"]}, {"$set": {"report": "[1]: " + report_description}})

    update.message.reply_text(
        text="✅️ Дякуємо. Ви успішно повідомили про проблему",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію')
    )
    return ConversationHandler.END


def cancel_report(update: Update, context: CallbackContext) -> ConversationHandler.END:
    reply_keyboard = MAIN_REPLY_KEYBOARD

    update.message.reply_text(
        text="☑️ Відгук скасовано",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію')
    )
    return ConversationHandler.END


def cancel_default(update: Update, context: CallbackContext) -> None:
    reply_keyboard = MAIN_REPLY_KEYBOARD
    update.message.reply_text(
        text="ℹ️️ Усі операції скасовано",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                         one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію')
    )


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


def main() -> None:
    updater = Updater(config['Database']['token'])
    dispatcher = updater.dispatcher

    scan = MessageHandler(Filters.regex('^(Перевірити наявність|/scan|Ще раз)$'), scan_handler)
    start = CommandHandler('start', start_handler)
    cancel_echo = CommandHandler('cancel', cancel_default)
    decoder = MessageHandler(Filters.photo, retrieve_scan_results)
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
                MessageHandler(Filters.contact & ~Filters.command, add_admin)
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

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
