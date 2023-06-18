from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext, MessageHandler, Filters
import sqlite3
import time
from datetime import datetime, timedelta
import pytz
import random


SECONDS = {}
PAUSED_TIME = {}
ADMINS = set()
EUROPE_BERLIN = pytz.timezone('Europe/Berlin')
user_states = {}


from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if user_id in ADMINS:
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton('Результаты', callback_data='results')],
            [InlineKeyboardButton('Выдача материалов', callback_data='admin_get_materials')],
            [InlineKeyboardButton('Просмотр криптокошельков', callback_data='admin_view_wallets')],
        ])
    else:
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton('Мои результаты', callback_data='myresults')],
            [InlineKeyboardButton('Старт', callback_data='start')],
            [InlineKeyboardButton('Выдача материала', callback_data='get_materials')],
            [InlineKeyboardButton('Привязать криптокошелек', callback_data='link_wallet')],
        ])

    if update.message:
        update.message.reply_text('Добро пожаловать в секундомер!', reply_markup=reply_markup)
    else:
        query = update.callback_query
        query.edit_message_text('Добро пожаловать в секундомер!', reply_markup=reply_markup)


def link_wallet(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    query = update.callback_query
    query.answer()

    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton('Отмена', callback_data='cancel')],
    ])
    query.message.reply_text('Введите данные вашего криптокошелька (USDT TRC-20):', reply_markup=reply_markup)
    user_states[user_id] = 'link_wallet'


def save_wallet_data(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    wallet_data = update.message.text.strip()

    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()

    cursor.execute('INSERT INTO wallets (user_id, wallet_data) VALUES (?, ?)', (user_id, wallet_data))
    conn.commit()
    conn.close()

    query = update.callback_query
    query.edit_message_text('Данные криптокошелька сохранены!')

    # Возвращаем пользователя в обычное меню после сохранения данных
    start(update, context)


def admin_view_wallets(update: Update, context: CallbackContext):
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('SELECT wallets.user_id, wallets.wallet_data, users.username FROM wallets LEFT JOIN users ON wallets.user_id = users.user_id')
    rows = cursor.fetchall()
    conn.close()

    if rows:
        wallet_info = "\n".join([f"User: @{row[2]}, Wallet Data: {row[1]}" for row in rows])
    else:
        wallet_info = "Нет сохраненных данных о криптокошельках."

    query = update.callback_query
    query.edit_message_text(f"Данные криптокошельков:\n\n{wallet_info}")

    # Возвращаем администратора в админ-панель после просмотра данных
    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton('Результаты', callback_data='results')],
        [InlineKeyboardButton('Выдача материалов', callback_data='admin_get_materials')],
        [InlineKeyboardButton('Просмотр криптокошельков', callback_data='admin_view_wallets')],
    ])
    query.message.reply_text(text='Выберите опцию:', reply_markup=reply_markup)
    user_states[update.effective_user.id] = 'results'



def add_material(update: Update, context: CallbackContext) -> None:
    material_name = context.args[0]
    material_description = context.args[1]
    material_content = ' '.join(context.args[2:])

    conn = sqlite3.connect('materials.db')
    cursor = conn.cursor()

    # Проверяем, существует ли уже запись для данного материала
    cursor.execute('SELECT id FROM materials WHERE name = ?', (material_name,))
    row = cursor.fetchone()
    if row:
        # Обновляем существующую запись
        material_id = row[0]
        cursor.execute('UPDATE materials SET description = ?, content = ? WHERE id = ?',
                       (material_description, material_content, material_id))
    else:
        # Добавляем новую запись
        cursor.execute('INSERT INTO materials (name, description, content) VALUES (?, ?, ?)',
                       (material_name, material_description, material_content))

    conn.commit()
    conn.close()

    create_materials_table()  # Изменение: Обновление таблицы материалов

    update.message.reply_text('Материал добавлен.')






def create_materials_table():
    conn = sqlite3.connect('materials.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            content TEXT NOT NULL
        )
    ''')

    cursor.execute("UPDATE materials SET description = '' WHERE description IS NULL")

    cursor.execute("INSERT OR IGNORE INTO materials (name, description, content) VALUES (?, ?, ?)",
                   ('Discord', '', ''))
    cursor.execute("INSERT OR IGNORE INTO materials (name, description, content) VALUES (?, ?, ?)",
                   ('Twitter', '', ''))

    cursor.execute('SELECT * FROM materials ORDER BY id DESC')  # Изменение: Устанавливаем порядок материалов

    conn.commit()
    conn.close()


def can_user_receive_material(user_id):
    conn = sqlite3.connect('timer_db.sqlite')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM received_materials WHERE user_id = ? AND date = ?',
                   (user_id, datetime.now(EUROPE_BERLIN).date().strftime('%Y-%m-%d')))
    count = cursor.fetchone()[0]
    conn.close()
    return count == 0




def get_materials(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if not can_user_receive_material(user_id):
        update.message.reply_text('Вы уже получили материал сегодня.')
        return

    conn = sqlite3.connect('materials.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM materials')
    rows = cursor.fetchall()[::-1]  # Изменение: Переворачиваем порядок материалов
    if rows:
        random_material = random.choice(rows)
        material_id, material_name, material_description, material_content = random_material

        # Удаляем материал из базы данных
        cursor.execute('DELETE FROM materials WHERE id = ?', (material_id,))
        conn.commit()  # Сохраняем изменения в базе данных

        # Записываем информацию о полученном материале для пользователя
        cursor.execute('INSERT INTO received_materials (user_id, material_id, date) VALUES (?, ?, ?)',
                       (user_id, material_id, datetime.now(EUROPE_BERLIN).date().strftime('%Y-%m-%d')))
        conn.commit()

        conn.close()

        update.message.reply_text(
            text=f'Материал: {material_name}\nОписание: {material_description}\n\n{material_content}')
    else:
        conn.close()
        update.message.reply_text(text='Нет доступных материалов.')

def admin_get_materials(update: Update, context: CallbackContext):
    conn = sqlite3.connect('materials.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM materials')
    rows = cursor.fetchall()[::-1]  # Изменение: Переворачиваем порядок материалов
    if rows:
        random_material = random.choice(rows)
        material_id, material_name, material_description, material_content = random_material

        # Удаляем материал из базы данных
        cursor.execute('DELETE FROM materials WHERE id = ?', (material_id,))
        conn.commit()  # Сохраняем изменения в базе данных

        conn.close()

        query = update.callback_query
        query.edit_message_text(
            text=f'Материал: {material_name}\nОписание: {material_description}\n\n{material_content}')
    else:
        conn.close()
        query.edit_message_text(text='Нет доступных материалов.')

    user_states[update.effective_user.id] = 'start'


def mark_material_as_used(material_id):
    conn = sqlite3.connect('materials.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM materials WHERE id = ?', (material_id,))
    conn.commit()
    conn.close()



def button(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    current_state = user_states.get(user_id)

    if query.data == 'results':
        if user_id in ADMINS:
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton('Просмотреть результаты всех пользователей', callback_data='viewall')],
                [InlineKeyboardButton('Результаты за неделю', callback_data='weeklyresults')],
                [InlineKeyboardButton('Результаты за сегодня', callback_data='dailyresults')],
                [InlineKeyboardButton('Назад', callback_data='back')],
            ])

            query.edit_message_text(text='Выберите опцию:', reply_markup=reply_markup)
            user_states[user_id] = 'results'
        else:
            query.edit_message_text('Доступ запрещён')


    elif query.data == 'admin_get_materials':  # Добавлено: обработка кнопки "Выдача материалов" в админ-панели

        reply_markup = InlineKeyboardMarkup([

            [InlineKeyboardButton('Дискорд', callback_data='admin_discord')],

            [InlineKeyboardButton('Твиттер', callback_data='admin_twitter')],

            [InlineKeyboardButton('Назад', callback_data='back')],

        ])

        query.edit_message_text(text='Выберите материал для выдачи:', reply_markup=reply_markup)

        user_states[user_id] = 'admin_get_materials'


    elif query.data == 'admin_discord':  # Добавлено: обработка выбора выдачи Discord в админ-панели

        issue_material(update, context, 'Discord')


    elif query.data == 'admin_twitter':  # Добавлено: обработка выбора выдачи Twitter в админ-панели

        issue_material(update, context, 'Twitter')


    elif query.data == 'link_wallet':  # Добавлено: обработка кнопки "Привязать криптокошелек" в обычном меню
        link_wallet(update, context)

    elif query.data == 'admin_view_wallets':  # Добавлено: обработка кнопки "Просмотр криптокошельков" в админ-панели
        admin_view_wallets(update, context)

    elif query.data == 'weeklyresults':
        if user_id in ADMINS:
            one_week_ago = (datetime.now(EUROPE_BERLIN) - timedelta(days=7)).strftime('%Y-%m-%d')
            conn = sqlite3.connect('timer_db.sqlite')
            cursor = conn.cursor()
            cursor.execute('SELECT user_id, SUM(elapsed_time) FROM timer_results WHERE date >= ? GROUP BY user_id',
                           (one_week_ago,))
            rows = cursor.fetchall()
            conn.close()

            results = "\n".join(
                [f"User: @{context.bot.get_chat(row[0]).username}, Total Time: {format_time(row[1])}" for row in rows])

            query.edit_message_text(f"Результаты за неделю:\n{results}")

            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton('Назад', callback_data='results')],
            ])
            query.message.reply_text(text='Выберите опцию:', reply_markup=reply_markup)
            user_states[user_id] = 'weeklyresults'
        else:
            query.edit_message_text('Доступ запрещён')

    elif query.data == 'dailyresults':
        if user_id in ADMINS:
            today = datetime.now(EUROPE_BERLIN).date().strftime('%Y-%m-%d')
            conn = sqlite3.connect('timer_db.sqlite')
            cursor = conn.cursor()
            cursor.execute('SELECT user_id, SUM(elapsed_time) FROM timer_results WHERE date = ? GROUP BY user_id',
                           (today,))
            rows = cursor.fetchall()
            conn.close()

            results = "\n".join(
                [f"User: @{context.bot.get_chat(row[0]).username}, Total Time: {format_time(row[1])}" for row in rows])

            query.edit_message_text(f"Результаты за сегодня:\n{results}")

            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton('Назад', callback_data='results')],
            ])
            query.message.reply_text(text='Выберите опцию:', reply_markup=reply_markup)
            user_states[user_id] = 'dailyresults'
        else:
            query.edit_message_text('Доступ запрещён')

    elif query.data == 'viewall':
        if user_id in ADMINS:
            conn = sqlite3.connect('timer_db.sqlite')
            cursor = conn.cursor()
            cursor.execute('SELECT user_id, SUM(elapsed_time) FROM timer_results GROUP BY user_id')
            rows = cursor.fetchall()
            conn.close()

            results = "\n".join(
                [f"User: @{context.bot.get_chat(row[0]).username}, Total Time: {format_time(row[1])}" for row in rows])

            query.edit_message_text(f"Результаты:\n{results}")

            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton('Назад', callback_data='results')],
            ])
            query.message.reply_text(text='Выберите опцию:', reply_markup=reply_markup)
            user_states[user_id] = 'viewall'
        else:
            query.edit_message_text('Доступ запрещён')

    elif query.data == 'get_materials':

        keyboard = [

            [InlineKeyboardButton('Дискорд', callback_data='discord')],

            [InlineKeyboardButton('Твиттер', callback_data='twitter')]

        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        query.edit_message_text(text='Выберите материал:', reply_markup=reply_markup)

        user_states[user_id] = 'get_materials'




    elif query.data == 'discord' or query.data == 'twitter':

        user_id = query.from_user.id

        if not can_user_receive_material(user_id):
            query.edit_message_text('Вы уже получили материал сегодня.')

            return

        conn = sqlite3.connect('materials.db')

        cursor = conn.cursor()

        cursor.execute('SELECT * FROM materials WHERE name = ?', (query.data.capitalize(),))

        rows = cursor.fetchall()

        conn.close()

        if rows:

            random_material = random.choice(rows)

            material_id, material_name, material_description, material_content = random_material

            query.edit_message_text(

                text=f'Материал: {material_name}\nОписание: {material_description}\n\n{material_content}')

            mark_material_as_used(material_id)  # Изменение: Помечаем материал как использованный

            # Записываем информацию о полученном материале для пользователя

            conn = sqlite3.connect('timer_db.sqlite')

            cursor = conn.cursor()

            cursor.execute('INSERT INTO received_materials (user_id, material_id, date) VALUES (?, ?, ?)',

                           (user_id, material_id, datetime.now(EUROPE_BERLIN).date().strftime('%Y-%m-%d')))

            conn.commit()

            conn.close()


        else:

            query.edit_message_text(text='Доступный материал не найден.')

        user_states[user_id] = 'start'



    elif query.data == 'myresults':
        conn = sqlite3.connect('timer_db.sqlite')
        cursor = conn.cursor()
        cursor.execute('SELECT SUM(elapsed_time) FROM timer_results WHERE user_id = ?', (user_id,))
        rows = cursor.fetchall()
        conn.close()

        if rows[0][0]:
            total_time = rows[0][0]
            query.edit_message_text(f"Ваши результаты:\nОбщее время: {format_time(total_time)}")
        else:
            query.edit_message_text("У вас пока нет результатов. Продолжайте работу!")

    elif query.data == 'start':
        if user_id not in SECONDS and user_id not in PAUSED_TIME:
            start_time = time.monotonic()
            SECONDS[user_id] = (start_time, 0)
            query.edit_message_text(text="Секундомер запущен!")
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton('Пауза', callback_data='pause')],
                [InlineKeyboardButton('Стоп', callback_data='stop')],
            ])
            query.message.reply_text(text='Выберите опцию:', reply_markup=reply_markup)
            user_states[user_id] = 'running'
        else:
            query.edit_message_text(text=f"Выбранный материал: {query.data}")



    elif query.data == 'pause':
        if user_id in SECONDS:
            start_time, elapsed_time = SECONDS[user_id]
            paused_time = time.monotonic() - start_time
            PAUSED_TIME[user_id] = (start_time, elapsed_time + paused_time)
            del SECONDS[user_id]
            query.edit_message_text(
                text=f"Секундомер приостановлен! Прошло времени: {format_time(elapsed_time + paused_time)}")
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton('Продолжить', callback_data='continue')],
                [InlineKeyboardButton('Стоп', callback_data='stop')],
            ])
            query.message.reply_text(text='Выберите опцию:', reply_markup=reply_markup)
            user_states[user_id] = 'paused'
        else:
            query.edit_message_text(text="Секундомер не был запущен!")

    elif query.data == 'continue':
        if user_id in PAUSED_TIME:
            start_time, paused_time = PAUSED_TIME[user_id]
            SECONDS[user_id] = (time.monotonic(), paused_time)
            del PAUSED_TIME[user_id]
            query.edit_message_text(text="Секундомер продолжен!")
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton('Пауза', callback_data='pause')],
                [InlineKeyboardButton('Стоп', callback_data='stop')],
            ])
            query.message.reply_text(text='Выберите опцию:', reply_markup=reply_markup)
            user_states[user_id] = 'running'
        else:
            query.edit_message_text(text="Секундомер не был на паузе!")

    elif query.data == 'stop':
        if user_id in SECONDS:
            start_time, elapsed_time = SECONDS[user_id]
            paused_time = time.monotonic() - start_time
            total_time = elapsed_time + paused_time
            del SECONDS[user_id]
            query.edit_message_text(text=f"Секундомер остановлен! Фиксированное время: {format_time(total_time)}")

            conn = sqlite3.connect('timer_db.sqlite')
            cursor = conn.cursor()
            cursor.execute('SELECT elapsed_time, date FROM timer_results WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            if row:
                current_elapsed_time, date = row[0], row[1]
                total_time += current_elapsed_time
                current_date = datetime.now(EUROPE_BERLIN).date().strftime('%Y-%m-%d')
                cursor.execute('UPDATE timer_results SET elapsed_time = ?, date = ? WHERE user_id = ?',
                               (total_time, current_date, user_id))
            else:
                current_date = datetime.now(EUROPE_BERLIN).date().strftime('%Y-%m-%d')
                cursor.execute('INSERT INTO timer_results (user_id, elapsed_time, date) VALUES (?, ?, ?)',
                               (user_id, total_time, current_date))

            conn.commit()
            conn.close()



        elif user_id in PAUSED_TIME:
            start_time, paused_time = PAUSED_TIME[user_id]
            total_time = paused_time
            del PAUSED_TIME[user_id]
            query.edit_message_text(text=f"Секундомер остановлен! Фиксированное время: {format_time(total_time)}")



        else:
            query.edit_message_text(text="Секундомер не был запущен!")

    elif query.data == 'back':
        if current_state == 'results':
            start(update, context)
        elif current_state == 'weeklyresults':
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton('Просмотреть результаты всех пользователей', callback_data='viewall')],
                [InlineKeyboardButton('Результаты за неделю', callback_data='weeklyresults')],
                [InlineKeyboardButton('Результаты за сегодня', callback_data='dailyresults')],
                [InlineKeyboardButton('Назад', callback_data='back')],
            ])
            query.edit_message_text('Выберите опцию:', reply_markup=reply_markup)
        elif current_state == 'dailyresults':
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton('Просмотреть результаты всех пользователей', callback_data='viewall')],
                [InlineKeyboardButton('Результаты за неделю', callback_data='weeklyresults')],
                [InlineKeyboardButton('Результаты за сегодня', callback_data='dailyresults')],
                [InlineKeyboardButton('Назад', callback_data='back')],
            ])
            query.edit_message_text('Выберите опцию:', reply_markup=reply_markup)
        elif current_state == 'viewall':
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton('Просмотреть результаты всех пользователей', callback_data='viewall')],
                [InlineKeyboardButton('Результаты за неделю', callback_data='weeklyresults')],
                [InlineKeyboardButton('Результаты за сегодня', callback_data='dailyresults')],
                [InlineKeyboardButton('Назад', callback_data='back')],
            ])
            query.edit_message_text('Выберите опцию:', reply_markup=reply_markup)


    elif query.data == 'discord':
        conn = sqlite3.connect('materials.db')
        cursor = conn.cursor()
        cursor.execute('SELECT content FROM materials WHERE name = "Discord"')
        row = cursor.fetchone()
        conn.close()

        if row:
            content = row[0]
            query.edit_message_text(text=content)

        else:
            query.edit_message_text(text='Доступный материал не найден.')


    elif query.data == 'twitter':
        conn = sqlite3.connect('materials.db')
        cursor = conn.cursor()
        cursor.execute('SELECT content FROM materials WHERE name = "Twitter"')
        row = cursor.fetchone()
        conn.close()

        if row:
            content = row[0]
            query.edit_message_text(text=content)

        else:
            query.edit_message_text(text='Доступный материал не найден.')


def issue_material(update: Update, context: CallbackContext, material: str):
    conn = sqlite3.connect('materials.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM materials WHERE name = ?', (material,))
    rows = cursor.fetchall()

    if rows:
        random_material = random.choice(rows)
        material_id, material_name, material_description, material_content = random_material

        # Удаляем материал из базы данных
        cursor.execute('DELETE FROM materials WHERE id = ?', (material_id,))
        conn.commit()  # Сохраняем изменения в базе данных

        conn.close()

        query = update.callback_query
        query.edit_message_text(
            text=f'Материал: {material_name}\nОписание: {material_description}\n\n{material_content}')

        # Добавляем информацию о выданном материале в отдельную таблицу "used_materials"
        conn = sqlite3.connect('used_materials.db')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO used_materials (material_id, user_id) VALUES (?, ?)',
                       (material_id, update.effective_user.id))
        conn.commit()
        conn.close()

    else:
        conn.close()
        update.message.reply_text(text='Нет доступных материалов.')

    # Возвращаем пользователя в админ-панель после выдачи материала
    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton('Результаты', callback_data='results')],
        [InlineKeyboardButton('Выдача материалов', callback_data='admin_get_materials')],
        # Добавлено: кнопка выдачи материалов в админ-панели
    ])
    query.message.reply_text(text='Выберите опцию:', reply_markup=reply_markup)
    user_states[update.effective_user.id] = 'results'


def format_time(seconds):
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"


def update_timer(context: CallbackContext):
    current_time = datetime.now(EUROPE_BERLIN)
    current_day = current_time.strftime('%Y-%m-%d')
    current_week_start = (current_time - timedelta(days=current_time.weekday())).strftime('%Y-%m-%d')

    # Проверяем, если текущий день изменился
    if current_day != context.job.context:
        # Обнуляем результаты за предыдущий день
        reset_previous_day_results()

        # Обновляем текущий день
        context.job.context = current_day

    for user_id, (start_time, paused_time) in SECONDS.items():
        if user_id in PAUSED_TIME:
            elapsed_time = PAUSED_TIME[user_id]
        else:
            elapsed_time = time.monotonic() - start_time + paused_time

        if user_id not in SECONDS and user_id in PAUSED_TIME:
            del PAUSED_TIME[user_id]

        conn = sqlite3.connect('timer_db.sqlite')
        cursor = conn.cursor()
        cursor.execute('UPDATE timer_results SET elapsed_time = ? WHERE user_id = ?',
                       (elapsed_time, user_id))

        # Update daily_results
        cursor.execute('SELECT elapsed_time FROM daily_results WHERE user_id = ? AND day = ?', (user_id, current_day))
        row = cursor.fetchone()
        if row:
            cursor.execute('UPDATE daily_results SET elapsed_time = ? WHERE user_id = ? AND day = ?',
                           (elapsed_time, user_id, current_day))
        else:
            cursor.execute('INSERT INTO daily_results (user_id, elapsed_time, day) VALUES (?, ?, ?)',
                           (user_id, elapsed_time, current_day))

        # Update weekly_results
        cursor.execute('SELECT elapsed_time FROM weekly_results WHERE user_id = ? AND week_start = ?',
                       (user_id, current_week_start))
        row = cursor.fetchone()
        if row:
            cursor.execute('UPDATE weekly_results SET elapsed_time = ? WHERE user_id = ? AND week_start = ?',
                           (elapsed_time, user_id, current_week_start))
        else:
            cursor.execute('INSERT INTO weekly_results (user_id, elapsed_time, week_start) VALUES (?, ?, ?)',
                           (user_id, elapsed_time, current_week_start))

        # Add/update date in timer_results
        cursor.execute('SELECT date FROM timer_results WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        if row:
            current_date = datetime.now(EUROPE_BERLIN).date().strftime('%Y-%m-%d')
            cursor.execute('UPDATE timer_results SET elapsed_time = ?, date = ? WHERE user_id = ?',
                           (elapsed_time, current_date, user_id))
        else:
            current_date = datetime.now(EUROPE_BERLIN).date().strftime('%Y-%m-%d')
            cursor.execute('INSERT INTO timer_results (user_id, elapsed_time, date) VALUES (?, ?, ?)',
                           (user_id, elapsed_time, current_date))

        conn.commit()
        conn.close()

    for admin_id in ADMINS:
        conn = sqlite3.connect('timer_db.sqlite')
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, elapsed_time FROM timer_results')
        rows = cursor.fetchall()
        conn.close()

        results = "\n".join(
            [f"User: @{context.bot.get_chat(row[0]).username}, Total Time: {format_time(row[1])}" for row in rows])

        context.bot.send_message(chat_id=admin_id, text=f"Current Timer Results:\n{results}")


def reset_previous_day_results():
    previous_day = (datetime.now(EUROPE_BERLIN) - timedelta(days=1)).strftime('%Y-%m-%d')

    conn = sqlite3.connect('timer_db.sqlite')
    cursor = conn.cursor()
    cursor.execute('UPDATE daily_results SET elapsed_time = 0 WHERE day = ?', (previous_day,))
    conn.commit()
    conn.close()

    for admin_id in ADMINS:
        conn = sqlite3.connect('timer_db.sqlite')
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, elapsed_time FROM timer_results')
        rows = cursor.fetchall()
        conn.close()

        results = "\n".join(
            [f"User: @{context.bot.get_chat(row[0]).username}, Total Time: {format_time(row[1])}" for row in rows])

        context.bot.send_message(chat_id=admin_id, text=f"Current Timer Results:\n{results}")

def create_received_materials_table():
    conn = sqlite3.connect('timer_db.sqlite')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS received_materials (
            user_id INTEGER,
            material_id INTEGER,
            date TEXT
        )
    ''')
    conn.commit()
    conn.close()



def initialize_db():
    conn = sqlite3.connect('timer_db.sqlite')
    cursor = conn.cursor()
    cursor.execute('''
            CREATE TABLE IF NOT EXISTS timer_results (
                user_id INTEGER,
                elapsed_time INTEGER,
                date TEXT
            )
        ''')
    cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_results (
                user_id INTEGER,
                elapsed_time REAL,
                day TEXT
            )
        ''')
    cursor.execute('''
            CREATE TABLE IF NOT EXISTS weekly_results (
                user_id INTEGER,
                elapsed_time REAL,
                week_start TEXT
            )
        ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fixed_times (
            user_id INTEGER,
            fixed_time REAL
        )
    ''')

    conn.commit()
    conn.close()

    create_materials_table()
    create_received_materials_table()

def initialize_wallets_db():
     conn = sqlite3.connect('wallets.db')
     cursor = conn.cursor()
     cursor.execute('''
        CREATE TABLE IF NOT EXISTS wallets (
            user_id INTEGER PRIMARY KEY,
            wallet_data TEXT
         )
     ''')
     conn.commit()
     conn.close()

initialize_wallets_db()









def initialize_admins(context: CallbackContext):
    chat_id = "@carecrypto_eu"
    administrators = context.bot.get_chat_administrators(chat_id)
    for admin in administrators:
        ADMINS.add(admin.user.id)


def main():
    initialize_db()

    updater = Updater("6158509659:AAGWdJ9uUzE1HI1WbXIvvZOxFI5hXDE2jk8")

    updater.dispatcher.add_handler(CommandHandler('start', start))
    updater.dispatcher.add_handler(CommandHandler("add_material", add_material))
    updater.dispatcher.add_handler(CallbackQueryHandler(button))
    updater.dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, save_wallet_data))
    updater.dispatcher.add_handler(CommandHandler('link_wallet', link_wallet))
    updater.dispatcher.add_handler(CallbackQueryHandler(button))

    job_queue = updater.job_queue
    job_queue.run_once(initialize_admins, 0)

    create_materials_table()

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':

    main()