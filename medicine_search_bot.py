"""
Author: Andrew Yaroshevych
Version: 2.0.0
"""
from telegram import Update, ReplyKeyboardRemove, ReplyKeyboardMarkup
from telegram.ext import Updater, Filters, CallbackContext, CommandHandler, MessageHandler

from PIL import Image
from pyzbar.pyzbar import decode

import os
import logging
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


def start_handler(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    logger.info("%s: %s", user.first_name, update.message.text)

    reply_keyboard = [['Сканувати', 'Інструкції', 'Про мене']]

    update.message.reply_text(
        '🇺🇦 '
        '*Привіт\! Я бот для пошуку медикаментів\.*'
        '\nЯ допоможу Вам знайти коротку інформацію про ліки\.'
        '\n\nОберіть опцію, будь ласка\. Якщо ви користуєтесь ботом вперше \- рекомендую подивитись розділ "Інструкції"'
        '\n\nЦе можна зробити будь\-коли за допомогою команди */help*',
        parse_mode='MarkdownV2',
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, resize_keyboard=True, input_field_placeholder='Оберіть опцію'
        ),
    )


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


def end_scan_handler(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    logger.info("%s: %s", user.first_name, update.message.text)

    reply_keyboard = [['Сканувати', 'Інструкції']]

    update.message.reply_text(
        '☑️ Сканування завершено',
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


def goto_scan(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    logger.info("%s: %s", user.first_name, update.message.text)

    if update.message.text != 'Ще раз':
        update.message.reply_text(
            'Це добре😊 Можемо перейти до сканування.',
            reply_markup=ReplyKeyboardRemove(),
        )
    return scan_handler(update=update, context=context)


def db_query(code) -> str:
    if collection.count_documents({"code": code}) != 0:
        query_result = collection.find_one({"code": code}, {"_id": 0})
        output = f"<b>Штрих-код</b>: {query_result['code']}" \
                 f"\n<b>Назва</b>: {query_result['name']} " \
                 f"\n<b>Діюча речовина</b>: {query_result['active_ingredient']} " \
                 f"\n<b>Опис</b>: {query_result['description']} "
        return output
    else:
        return "Цей штрих-код відсутній у моїй базі даних ❌"


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
        link = 'https://www.google.com/search?q=' + code_str

        reply_keyboard = [['Завершити сканування']]

        update.message.reply_text(parse_mode='HTML',
                                  reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                                                   resize_keyboard=True,
                                                                   input_field_placeholder='Продовжуйте'),
                                  text='Ось відсканований штрихкод ✅:\n' + '<b>' + code_str + '</b>' +
                                       '<b>' + '\n\n🔍 Результати пошуку:\n' + '</b>' +
                                       db_query(code_str),
                                  quote=True)

        # update.message.reply_text(parse_mode='HTML',
        #                           reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
        #                                                            resize_keyboard=True,
        #                                                            input_field_placeholder='Продовжуйте'),
        #                           text='<b>' + 'Також можете перевірити цей штрихкод у Google:' + '</b>' +
        #                                '\n\nЙмовірно це: ' + '<b>' + get_query_heading(code_str) + '</b>' +
        #                                ' - ' + f'<a href="{link}"><b>Google</b></a>')

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


def undefined_input(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    logger.info("%s: %s", user.first_name, update.message.text)

    reply_keyboard = [['Сканувати', 'Інструкції']]

    update.message.reply_text(
        'Я вас не розумію 🧐.\nОберіть, будь ласка, одну з доступних опцій',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію'),
    )


def cancel_operation(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    logger.info("%s: %s", user.first_name, update.message.text)

    reply_keyboard = [['Сканувати', 'Інструкції']]

    update.message.reply_text(
        '☑️ Гаразд, операцію скасовано',
        parse_mode='MarkdownV2',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True,
                                         input_field_placeholder='Оберіть опцію'),
    )


def tell_about(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    logger.info("%s: %s", user.first_name, update.message.text)

    reply_keyboard = [['Зрозуміло!']]

    update.message.reply_text(
        'Слава Україні! 🇺🇦\n\n'
        '🤖 Я - бот, створений командою студентів зі Львова.\n\n✅ Моє завдання - допомогти волонтерам, що праwюють на '
        'пункnах сортування гуманітарної допомоги. Я допоможу Вам знайти інформацію та короткий опис про медичні '
        'препарати за допомогою штрих-коду.'
        '\n\n🥇 Це дозволить пришвидшити роботу, а також якість сортування медикаментів '
        'для допомоги Збройним Силам України 💛💙',
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, resize_keyboard=True),
    )


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
    do_not_understand = MessageHandler(~ Filters.regex('^(Сканувати|/scan)$') &
                                       ~ Filters.regex('^(Інструкції|/help)$') &
                                       ~ Filters.regex('^(Зрозуміло!|Ще раз)$') &
                                       ~ Filters.regex('Завершити сканування') &
                                       ~ Filters.regex('Про мене') &
                                       ~ Filters.photo &
                                       ~ Filters.attachment, undefined_input)
    cancel = CommandHandler('cancel', cancel_operation)
    about = MessageHandler(Filters.regex('Про мене'), tell_about)

    dispatcher.add_handler(start)
    dispatcher.add_handler(scan)
    dispatcher.add_handler(end_scan)
    dispatcher.add_handler(cancel)
    dispatcher.add_handler(instructions)
    dispatcher.add_handler(continue_scan)
    dispatcher.add_handler(decoder)
    dispatcher.add_handler(not_file)
    dispatcher.add_handler(do_not_understand)
    dispatcher.add_handler(about)

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
