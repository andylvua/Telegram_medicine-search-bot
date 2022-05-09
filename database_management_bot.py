"""
Author: Andrew Yaroshevych
Version: 2.0.0
"""

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, ConversationHandler, CallbackContext

from PIL import Image
from pyzbar.pyzbar import decode

import os
import logging
import configparser

from pymongo import MongoClient

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

config = configparser.ConfigParser()
config.read("config.ini")

cluster = MongoClient(config['Database']['cluster'])
db = cluster.TestBotDatabase
collection = db.TestBotCollection

# Conversation states
NAME, INGREDIENT, ABOUT, CHECK, INSERT = range(5)

drug_info = {
    "name": None,
    "active_ingredient": None,
    "description": None,
    "code": None
}


def start_handler(update: Update, _: CallbackContext):
    user = update.message.from_user
    logger.info("%s: %s", user.first_name, update.message.text)

    reply_keyboard = [['Перевірити наявність', 'Додати новий медикамент', 'Інструкції']]

    update.message.reply_text(
        '*Привіт\! Я бот для адміністування бази даних Telegram MSB\.*'
        '\n\nОберіть опцію, будь ласка\.',
        parse_mode='MarkdownV2',
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, resize_keyboard=True, input_field_placeholder='Оберіть опцію'
        ),
    )


def scan_handler(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    logger.info("%s: %s. Scan started", user.first_name, update.message.text)

    reply_keyboard = [['Відмінити сканування']]

    update.message.reply_text(
        'Будь ласка, надсилайте мені фото пакувань, де я можу *чітко* побачити штрихкод '
        'для перевірки наявності\.',
        parse_mode='MarkdownV2',
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, resize_keyboard=True, input_field_placeholder='Надішліть фото'
        ),
    )


def db_query(code):
    logger.info("Database quired")

    try:
        if collection.count_documents({"code": code}) != 0:
            query_result = collection.find_one({"code": code}, {"_id": 0})
            output = f"<b>Назва</b>: {query_result['name']} " \
                     f"\n<b>Діюча речовина</b>: {query_result['active_ingredient']} " \
                     f"\n<b>Опис</b>: {query_result['description']} "
            return output
        else:
            return
    except Exception as e:
        logger.info(e)
        return


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
        drug_info["code"] = code_str
        link = 'https://www.google.com/search?q=' + code_str

        reply_keyboard = [['Завершити сканування']]
        reply_keyboard2 = [['Так', 'Ні']]

        if db_query(code_str) is not None:
            update.message.reply_text(parse_mode='HTML',
                                      reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                                                       resize_keyboard=True,
                                                                       input_field_placeholder='Продовжуйте'),
                                      text='✅ Штрих-код ' + '<b>' + code_str + '</b>' +
                                           ' наявний у моїй базі даних:\n\n' +
                                           db_query(code_str),
                                      quote=True)
        else:
            update.message.reply_text(parse_mode='HTML',
                                      reply_markup=ReplyKeyboardMarkup(reply_keyboard2, one_time_keyboard=True,
                                                                       resize_keyboard=True,
                                                                       input_field_placeholder='Продовжуйте'),
                                      text='❌ Штрих-код ' + '<b>' + code_str + '</b>' +
                                           ' відсутній у моїй базі даних.\n\n' +
                                           'Чи бажаєте Ви додати інформацію про цей медикамент?',
                                      quote=True)

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


def start_adding(update: Update, _: CallbackContext) -> int:
    user = update.message.from_user
    reply_keyboard = [['Скасувати додавання']]

    if update.message.text != "Так" and not update.message.photo:
        update.message.reply_text(
            'Добре.\nСпершу, надішліть фото штрих-коду',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder='Надішліть фото'
                                             ),
        )

        return NAME
    elif not update.message.photo:
        logger.info("Started collecting info")
        update.message.reply_text(
            'Добре.\nСпершу, надішліть назву медикаменту',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder='Введіть назву'
                                             ),
        )
        return INGREDIENT


def get_name(update: Update, context: CallbackContext):
    logger.info("Storing photo")

    user = update.message.from_user
    reply_keyboard = [['Скасувати додавання']]

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
        drug_info["code"] = code_str
        if collection.count_documents({"code": code_str}) != 0:
            update.message.reply_text(text="⚠️ Медикамент з таким штрих-кодом вже присутній у базі даних.",
                                      quote=True,
                                      reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                                                       resize_keyboard=True),
                                      )
            logger.info("Cancelling, barcode already exists")
            return cancel(update=update, _=context)
        else:
            logger.info("Added barcode info")
            update.message.reply_text(text="Штрих-код відскановано успішно ✅",
                                      quote=True,
                                      reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                                                       resize_keyboard=True),
                                      )

    except IndexError as e:
        logger.info(e)

        update.message.reply_text(text="*На жаль, сталася помилка\. Мені не вдалось відсканувати штрих\-код ❌ *"
                                       "\nПереконайтесь, що робите все правильно та надішліть фото ще раз, "
                                       "або подивіться інструкції до сканування за допомогою команди */help*",
                                  quote=True,
                                  parse_mode='MarkdownV2',
                                  ),
        return start_adding(update=update, _=context)
    finally:
        os.remove("code.png")

    update.message.reply_text(
        text='Надішліть назву медикаменту',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder="Введіть назву")
    )

    return INGREDIENT


def get_active_ingredient(update: Update, _: CallbackContext) -> int:
    logger.info("Entered name of the drug: %s", update.message.text)

    user = update.message.from_user
    reply_keyboard = [['Скасувати додавання']]

    name = update.message.text
    drug_info["name"] = name

    update.message.reply_text(text='Вкажіть, будь ласка, діючу речовину медикаменту',
                              reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                                               resize_keyboard=True,
                                                               input_field_placeholder="Введіть діючу речовину"
                                                               ),
                              )

    return ABOUT


def get_about(update: Update, _: CallbackContext) -> int:
    logger.info("Entered active ingredient of the drug: %s", update.message.text)

    user = update.message.from_user
    reply_keyboard = [['Скасувати додавання']]

    active_ingredient = update.message.text
    drug_info["active_ingredient"] = active_ingredient

    update.message.reply_text(
        text='Тепер надішліть короткий опис даного препарату',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                         resize_keyboard=True,
                                         input_field_placeholder="Введіть опис"
                                         ),
    )

    return CHECK


def check_info(update: Update, _: CallbackContext) -> int:
    logger.info("Entered description: %s. Now checking info", update.message.text)

    user = update.message.from_user
    description = update.message.text
    drug_info["description"] = description

    output = f"<b>Назва</b>: {drug_info['name']} " \
             f"\n<b>Діюча речовина</b>: {drug_info['active_ingredient']} " \
             f"\n<b>Опис</b>: {drug_info['description']} "

    reply_keyboard = [['Так, додати до бази даних', 'Ні, скасувати']]

    update.message.reply_text(text='<b>Введена інформація:</b>\n\n' + output +
                                   '\n\n❓Ви точно бажаєте додати її до бази даних?',
                              parse_mode='HTML',
                              reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                                               resize_keyboard=True,
                                                               input_field_placeholder="Оберіть опцію"
                                                               )
                              )

    return INSERT


def insert_to_db(update: Update, _: CallbackContext) -> int:
    user = update.message.from_user
    logger.info("Checked info.")
    if update.message.text == 'Так, додати до бази даних':
        post_id = collection.insert_one(drug_info).inserted_id
        logger.info("Added successfully")
        update.message.reply_text(
            '✅ Препарат успішно додано до бази даних'
        )
    else:
        logger.info("Canceled adding")
        update.message.reply_text(
            '☑️ Гаразд, додавання скасовано'
        )

    for key in drug_info.keys():
        drug_info[key] = None
    logger.info("Clearing info: %s", drug_info)
    return ConversationHandler.END


def cancel(update: Update, _: CallbackContext) -> int:
    user = update.message.from_user
    reply_keyboard = [['Перевірити наявність', 'Додати новий медикамент', 'Інструкції']]

    logger.info("User %s canceled the conversation.", user.first_name)
    update.message.reply_text(text='ℹ️ Операцію додавання скасовано',
                              reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                                               one_time_keyboard=True, resize_keyboard=True,
                                                               input_field_placeholder='Оберіть опцію'
                                                               )
                              )

    return ConversationHandler.END


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


def main_keyboard_handler(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    logger.info("%s: %s", user.first_name, update.message.text)

    reply_keyboard = [['Перевірити наявність', 'Додати новий медикамент', 'Інструкції']]

    if update.message.text not in ["Зрозуміло!", "Ні"]:
        update.message.reply_text(
            '☑️ Сканування завершено',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder='Оберіть опцію'),
        )
    else:
        update.message.reply_text(
            'Гаразд',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                             resize_keyboard=True,
                                             input_field_placeholder='Оберіть опцію'),
        )


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
                                       '\n\n 💬 Ви можете викликати це повідомлення у будь\-який момент, '
                                       'надіславши команду */help*',
                               parse_mode='MarkdownV2',
                               reply_markup=ReplyKeyboardMarkup(
                                   reply_keyboard, one_time_keyboard=True, resize_keyboard=True,
                                   input_field_placeholder='Оберіть опцію'),
                               )
    return ConversationHandler.END


def main() -> None:
    updater = Updater(config['Database']['token'])
    dispatcher = updater.dispatcher

    scan = MessageHandler(Filters.regex('^(Перевірити наявність|/scan|Ще раз)$'), scan_handler)
    start = CommandHandler('start', start_handler)
    decoder = MessageHandler(Filters.photo, retrieve_results)
    not_file = MessageHandler(Filters.attachment, file_warning)
    end_scan = MessageHandler(Filters.regex('^(Завершити сканування|Відмінити сканування|Зрозуміло!|Ні)$'),
                              main_keyboard_handler)
    instructions = MessageHandler(Filters.regex('^(Інструкції|/help)$'), instructions_handler)

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(Filters.regex('^(Так|Додати новий медикамент)$'), start_adding)],
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
            CHECK: [
                MessageHandler(Filters.text & ~Filters.command & ~Filters.text("Скасувати додавання"), check_info)
            ],
            INSERT: [
                MessageHandler(Filters.text & ~Filters.text("Скасувати додавання"), insert_to_db)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel),
                   MessageHandler(Filters.text("Скасувати додавання"), cancel),
                   CommandHandler("help", instructions_handler)],
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
