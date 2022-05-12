"""
Author: Andrew Yaroshevych
Version: 2.1.0
"""
from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, ConversationHandler, CallbackContext

from PIL import Image
from pyzbar.pyzbar import decode

import os
import io
import logging
import configparser

from pymongo import MongoClient
from functools import wraps

LIST_OF_ADMINS = []

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%d/%m/%Y %H:%M:%S', level=logging.INFO
)
logger = logging.getLogger(__name__)

config = configparser.ConfigParser()
config.read("config.ini")

cluster = MongoClient(config['Database']['cluster'])
db = cluster.TestBotDatabase
collection = db.TestBotCollection

# Conversation states
NAME, INGREDIENT, ABOUT, PHOTO, CHECK, INSERT = range(6)

DRUG_INFO = {
    "name": "",
    "active_ingredient": "",
    "description": "",
    "code": "",
    "photo": b''
}


def restricted(func):
    @wraps(func)
    def wrapped(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in LIST_OF_ADMINS:
            update.message.reply_text(
                "Unauthorized access denied for *{}*".format(user_id),
                parse_mode='MarkdownV2',
            )
            logger.info("Unauthorized access denied for {}.".format(user_id))
            return
        return func(update, context, *args, **kwargs)
    return wrapped


def start_handler(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    logger.info("%s: %s", user.first_name, update.message.text)

    reply_keyboard = [['Перевірити наявність', 'Додати новий медикамент', 'Інструкції']]

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
        logger.info("Database quired. Retrieving photo")
        query_result = collection.find_one({"code": code_str}, {"_id": 0})
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

        reply_keyboard = [['Завершити сканування']]
        reply_keyboard2 = [['Так', 'Ні']]

        if db_check_availability(code_str):
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
        logger.info("Operation ended. Deleting photo")
        os.remove("code.png")


@restricted
def start_adding(update: Update, context: CallbackContext) -> int:
    user = update.message.from_user
    logger.info("User %s started adding process", user.first_name)
    logger.info("Clearing info: %s", DRUG_INFO)
    DRUG_INFO["name"] = ""
    DRUG_INFO["active_ingredient"] = ""
    DRUG_INFO["description"] = ""
    DRUG_INFO["code"] = ""
    DRUG_INFO["photo"] = b''
    logger.info("Cleared")

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
    reply_keyboard = [['Скасувати додавання']]

    description = update.message.text
    DRUG_INFO["description"] = description

    update.message.reply_text(
        text='Також, надішліть фото передньої сторони упаковки медикаменту',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder="Надішліть фото")
    )
    return CHECK


def check_info(update: Update, context: CallbackContext) -> int:
    logger.info("Now checking info")

    user = update.message.from_user

    id_img = update.message.photo[-1].file_id
    photo = context.bot.getFile(id_img)
    photo.download('photo.jpg')

    img = Image.open("photo.jpg")
    image_bytes = io.BytesIO()
    img.save(image_bytes, format='JPEG')

    DRUG_INFO["photo"] = image_bytes.getvalue()

    output = f"<b>Назва</b>: {DRUG_INFO['name']} " \
             f"\n<b>Діюча речовина</b>: {DRUG_INFO['active_ingredient']} " \
             f"\n<b>Опис</b>: {DRUG_INFO['description']} "

    reply_keyboard = [['Так, додати до бази даних', 'Ні, скасувати']]

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


def insert_to_db(update: Update, context: CallbackContext) -> int:
    user = update.message.from_user

    reply_keyboard = [['Перевірити наявність', 'Додати новий медикамент', 'Інструкції']]

    if update.message.text == 'Так, додати до бази даних':
        post_id = collection.insert_one(DRUG_INFO).inserted_id
        logger.info("Checked info. Added successfully")
        update.message.reply_text(
            text='✅ Препарат успішно додано до бази даних',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder="Оберіть опцію")
        )
    else:
        logger.info("User %s canceled adding process", user.first_name)
        update.message.reply_text(
            text='☑️ Гаразд, додавання скасовано',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder="Оберіть опцію")
        )

    return ConversationHandler.END


def cancel(update: Update, context: CallbackContext) -> int:
    user = update.message.from_user
    reply_keyboard = [['Перевірити наявність', 'Додати новий медикамент', 'Інструкції']]

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

    reply_keyboard = [['Перевірити наявність', 'Додати новий медикамент', 'Інструкції']]

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


def instructions_handler(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    logger.info("%s: %s", user.first_name, update.message.text)

    reply_keyboard = [['Зрозуміло!']]

    pic = 'resources/How_to_scan.png'
    update.message.reply_photo(
        open(pic, 'rb'),
        caption='🔍 Щоб перевірити наявність штрих\-коду у базі даних \- надішліть мені фото '
                'пакування, де я можу *чітко* побачити штрихкод\.'
                '\n\n✏️ Зверніть увагу, ви можете надсилати одразу декілька фотографій\.'
                '\n\n✅ Після сканування ви можете надсилати фото далі\. '
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


def main() -> None:
    updater = Updater(config['Database']['token'])
    dispatcher = updater.dispatcher

    scan = MessageHandler(Filters.regex('^(Перевірити наявність|/scan|Ще раз)$'), scan_handler)
    start = CommandHandler('start', start_handler)
    decoder = MessageHandler(Filters.photo, retrieve_scan_results)
    not_file = MessageHandler(Filters.attachment, file_warning)
    end_scan = MessageHandler(Filters.regex('^(Завершити сканування|Відмінити сканування|Зрозуміло!|Ні)$'),
                              main_keyboard_handler)
    instructions = MessageHandler(Filters.regex('^(Інструкції|/help)$'), instructions_handler)

    conv_handler = ConversationHandler(
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
            ],
            CHECK: [
                MessageHandler(Filters.photo & ~Filters.command & ~Filters.text("Скасувати додавання"), check_info)
            ],
            INSERT: [
                MessageHandler(Filters.text & ~Filters.text("Скасувати додавання"), insert_to_db)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel),
                   MessageHandler(Filters.text("Скасувати додавання"), cancel),
                   CommandHandler("help", instructions_handler)]
    )

    dispatcher.add_handler(conv_handler)
    dispatcher.add_handler(start)
    dispatcher.add_handler(scan)
    dispatcher.add_handler(decoder)
    dispatcher.add_handler(not_file)
    dispatcher.add_handler(end_scan)
    dispatcher.add_handler(instructions)

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
