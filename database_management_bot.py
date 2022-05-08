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
INGREDIENT, ABOUT, CHECK, INSERT = range(4)

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
        'Будь ласка, надішліть мені фото пакування, де я можу *чітко* побачити штрихкод\.',
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


# noinspection DuplicatedCode
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

    os.remove("code.png")


def get_name(update: Update, _: CallbackContext) -> int:
    user = update.message.from_user
    logger.info("Started collecting info")
    update.message.reply_text(
        'Добре. \nСпершу, надішліть назву медикаменту',
        reply_markup=ReplyKeyboardRemove(),
    )

    return INGREDIENT


def get_active_ingredient(update: Update, _: CallbackContext) -> int:
    logger.info("Entered name of the drug: %s", update.message.text)

    user = update.message.from_user
    name = update.message.text
    drug_info["name"] = name

    update.message.reply_text(
        'Вкажіть, будь ласка, діючу речовину медикаменту'
    )

    return ABOUT


def get_about(update: Update, _: CallbackContext) -> int:
    logger.info("Entered active ingredient of the drug: %s", update.message.text)

    user = update.message.from_user
    active_ingredient = update.message.text
    drug_info["active_ingredient"] = active_ingredient

    update.message.reply_text(
        'Тепер надішліть короткий опис даного препарату'
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
                                                               resize_keyboard=True,)
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
    logger.info("User %s canceled the conversation.", user.first_name)
    update.message.reply_text(
        '☑️ Гаразд, операцію додавання скасовано', reply_markup=ReplyKeyboardRemove()
    )

    return ConversationHandler.END


def main() -> None:
    updater = Updater(config['Database']['token'])
    dispatcher = updater.dispatcher

    scan = MessageHandler(Filters.regex('^(Перевірити наявність|/scan)$'), scan_handler)
    start = CommandHandler('start', start_handler)
    decoder = MessageHandler(Filters.photo, retrieve_results)

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(Filters.text("Так"), get_name)],
        states={
            INGREDIENT: [
                MessageHandler(Filters.text & ~Filters.command, get_active_ingredient)
            ],
            ABOUT: [
                MessageHandler(Filters.text & ~Filters.command, get_about),
            ],
            CHECK: [
                MessageHandler(Filters.text & ~Filters.command, check_info)
            ],
            INSERT: [
                MessageHandler(Filters.text, insert_to_db)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    dispatcher.add_handler(conv_handler)
    dispatcher.add_handler(start)
    dispatcher.add_handler(scan)
    dispatcher.add_handler(decoder)

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
