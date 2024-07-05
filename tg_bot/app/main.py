import os
import psycopg2
import requests
import telebot
from telebot import types

bot = telebot.TeleBot(os.getenv('TELEGRAM_TOKEN'))

professions = ["Финансовый аналитик", "Аналитик данных", "ML-разработчик", "Data Scientist", "Computer vision",
               "Специалист по подбору персонала", "Бизнес-тренер", "Бармен", "Уборщик"]

cities = ["Москва", "Санкт-Петербург", "Казань", "Волгоград"]

user_data = {}


def get_vacancies(city, profession, salary):
    conn = psycopg2.connect(
        dbname=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        host=os.getenv('DB_HOST'),
        port="5432"
    )
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM vacancies WHERE city=%s AND profession=%s AND salary > %s",
                   (city, profession, salary))
    vacancies = cursor.fetchall()
    conn.close()
    return vacancies


@bot.message_handler(commands=["start"])
def handle_start(message):
    keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    buttons = [types.KeyboardButton(ct) for ct in cities]
    keyboard.add(*buttons)
    bot.send_message(message.chat.id, "Здравствуйте, выберите город, в котором вы ищите вакансии",
                     reply_markup=keyboard)
    user_data[message.chat.id] = {}
    bot.register_next_step_handler(message, handle_city)


def handle_city(message):
    if message.text not in cities:
        handle_start(message)
        return

    city = message.text
    user_data[message.chat.id]['city'] = city

    keyboard = types.ReplyKeyboardMarkup(row_width=4, resize_keyboard=True)
    buttons = [types.KeyboardButton(prof) for prof in professions]
    keyboard.add(*buttons)
    bot.send_message(message.chat.id, "Выберите профессию", reply_markup=keyboard)
    bot.register_next_step_handler(message, handle_profession)


def handle_profession(message):
    if message.text not in professions:
        handle_start(message)
        return

    profession = message.text
    user_data[message.chat.id]['profession'] = profession
    bot.send_message(message.chat.id, text="Введите минимальную желаемую зарплату. Например 30000",
                     reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(message, handle_salary)


def handle_salary(message):
    try:
        salary = str(int(message.text))
        user_data[message.chat.id]["salary"] = salary
        city = user_data[message.chat.id]['city']
        profession = user_data[message.chat.id]['profession']

        keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        yes_button = types.KeyboardButton("Да")
        no_button = types.KeyboardButton("Нет")
        keyboard.add(yes_button, no_button)

        bot.send_message(message.chat.id,
                         text=f"Город: {city},\nПрофессию: {profession}\nЗарплату: {salary} руб.\nВсё верно?",
                         reply_markup=keyboard)
        bot.register_next_step_handler(message, handle_confirmation)

    except ValueError:
        handle_start(message)
        return


def handle_confirmation(message):
    if message.text == "Да":
        city = user_data[message.chat.id]['city']
        profession = user_data[message.chat.id]['profession']
        salary = user_data[message.chat.id]['salary']

        data = {
            "city": city,
            "profession": profession,
            "salary": salary
        }
        bot.send_message(message.chat.id, "Пожалуйста, дождитесь конца парсинга",
                         reply_markup=types.ReplyKeyboardRemove())
        response = requests.post("http://parser:5000/parse", json=data)

        if response.status_code == 200:
            keyboard = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
            show_button = types.KeyboardButton("Показать ваканасии")
            keyboard.add(show_button)
            bot.send_message(message.chat.id, "Парсинг завершен. Вакансий: " + response.json()["total_vacancies"],
                             reply_markup=keyboard)
            bot.register_next_step_handler(message, show_vacancies)
        else:
            bot.send_message(message.chat.id, "Произошла ошибка при парсинге. Попробуйте снова.")
            handle_start(message)
    else:
        handle_start(message)


def show_vacancies(message):
    city = user_data[message.chat.id]['city']
    profession = user_data[message.chat.id]['profession']
    salary = user_data[message.chat.id]['salary']
    vacancies = get_vacancies(city, profession, salary)
    user_data[message.chat.id]["vacancies"] = vacancies
    user_data[message.chat.id]["current_index"] = 0
    show_next_vacancy(message)


def show_next_vacancy(message):
    current_index = user_data[message.chat.id]["current_index"]
    vacancies = user_data[message.chat.id]["vacancies"]

    if current_index < len(vacancies):
        keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        next_button = types.KeyboardButton("Следующая вакансия")
        stop_button = types.KeyboardButton("Искать другую вакансию")
        keyboard.add(next_button, stop_button)

        vacancy = vacancies[current_index]
        vac_text1 = f"Компания: {vacancy[3]}\nВакансия: {vacancy[2]}\nГород: {vacancy[1]}\nОпыт: {vacancy[-4]}\n"
        vac_text2 = f"Скилы: {vacancy[-5]}\nЗарплата: {vacancy[-2]}\nОписание: {vacancy[4]}\n\nСсылка: {vacancy[-1]}"
        vacancy_text = vac_text1 + vac_text2
        bot.send_message(message.chat.id, text=vacancy_text, reply_markup=keyboard)

        user_data[message.chat.id]['current_index'] += 1
        bot.register_next_step_handler(message, handle_vacancy_navigation)
    else:
        bot.send_message(message.chat.id, "Больше вакансий нет.")
        handle_start(message)


def handle_vacancy_navigation(message):
    if message.text == "Следующая вакансия":
        show_next_vacancy(message)
    elif message.text == "Искать другую вакансию":
        handle_start(message)
    else:
        bot.send_message(message.chat.id, "Пожалуйста, используйте кнопки для навигации.")
        show_next_vacancy(message)


bot.polling(non_stop=True)
