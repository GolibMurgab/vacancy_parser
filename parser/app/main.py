import os
import psycopg2
import time
import random
import requests
from flask import Flask, render_template, request, make_response, jsonify
from bs4 import BeautifulSoup

hh_token = os.getenv('HH_TOKEN')

app = Flask(__name__)


def create_tables():
    conn = psycopg2.connect(
        dbname=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        host=os.getenv('DB_HOST'),
        port="5432"
    )
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS vacancies (
        id SERIAL PRIMARY KEY,
        city VARCHAR(40),
        profession VARCHAR(80),
        company VARCHAR(300),
        description VARCHAR(400),
        name VARCHAR(300),
        skills TEXT,
        experience VARCHAR(50),
        schedule VARCHAR(50),
        salary VARCHAR(50),
        url VARCHAR(50)
        )""")
    conn.commit()
    cursor.close()
    conn.close()


def get_vacancies(city_id, vacancy_name, expectated_salary, page):
    url = "https://api.hh.ru/vacancies/"
    params = {
        "text": vacancy_name,
        "area": city_id,
        "only_with_salary": True,
        "salary": expectated_salary,
        "page": page,
        "per_page": 50,
    }
    headers = {"Authorization": f"Bearer {hh_token}"}

    response = requests.get(url, params=params)
    print(response.raise_for_status())
    return response.json()


def get_vacancy_info(vacancy_id):
    url = f"https://api.hh.ru/vacancies/{vacancy_id}"
    headers = {"Authorization": f"Bearer {hh_token}"}

    response = requests.get(url)
    return response.json()


def get_salary(item):
    salary = item["salary"]
    if salary is None:
        salary = "зп не указана"
    else:
        salary = salary.get("from", "зп не указана")

    return salary


def get_schedule(item):
    schedule = item["schedule"]
    if schedule is None:
        schedule = "график не указан"
    else:
        schedule = schedule.get("name")

    return schedule


def get_experience(item):
    experience = item["experience"]
    if experience is None:
        experience = "опыт не указан"
    else:
        experience = experience.get("name", "опыт не указан")

    return experience


def get_company(item):
    company = item["employer"]
    if company is None:
        company = "компания не указана"
    else:
        company = company.get("name", "компания не указана")

    return company


def get_skills(vacancy_info):
    skills = vacancy_info.get("key_skills", None)
    if skills is None:
        skills = "Навыки не указаны"
        return skills
    else:
        skills = [skill["name"] for skill in skills]
        return ", ".join(skills)


def get_description(vacancy_info):
    description = vacancy_info.get("description", "Описание отсутсвует")
    description = remove_tags(description)
    return description


def remove_tags(description):
    description = description[:399]
    soup = BeautifulSoup(description, "html.parser")

    for data in soup(['style', 'script']):
        data.decompose()
    return ' '.join(soup.stripped_strings)


@app.route('/parse', methods=['POST'])
def parse_vacancies():
    create_tables()
    cities = {
        "Казань": 88,
        "Волгоград": 24,
        "Москва": 1,
        "Санкт-Петербург": 2
    }

    parse_parameters = request.json
    city = parse_parameters["city"]
    city_id = cities[city]
    profession = parse_parameters["profession"]
    expectated_salary = parse_parameters['salary']

    conn = psycopg2.connect(
        dbname=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        host=os.getenv('DB_HOST'),
        port="5432"
    )
    total = 0
    page = 0
    try:
        while True:
            data = get_vacancies(city_id, profession, expectated_salary, page)
            if not data.get('items'):
                break
            print(data["pages"])
            curs = conn.cursor()
            for item in data['items']:
                vacancy_info = get_vacancy_info(item["id"])

                salary = get_salary(item)
                schedule = get_schedule(item)
                url = item.get("alternate_url", "нет ссылки")
                experience = get_experience(item)
                skills = get_skills(vacancy_info)
                description = get_description(vacancy_info)
                name = item.get("name", "Должность не указана")
                company = get_company(item)

                insert_query = """INSERT INTO vacancies (city, profession, company, description, name, skills, 
                experience, schedule, salary, url) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""

                search_duplicates = "SELECT id FROM vacancies WHERE url = %s"
                curs.execute(search_duplicates, (url,))
                duplicate = curs.fetchall()
                if duplicate:
                    insert_query = """UPDATE vacancies SET city=%s, profession=%s, company=%s, description=%s, 
                    name=%s, skills=%s, experience=%s, schedule=%s, salary=%s WHERE url=%s"""

                curs.execute(insert_query,
                             (city, profession, company, description, name, skills, experience, schedule, salary, url))
                total += 1

            if data["pages"] - page <= 1:
                break
            else:
                page += 1

            time.sleep(random.uniform(1.0, 4.0))

            conn.commit()
            curs.close()
    except Exception as e:
        response = make_response(f"Возникла ошибка во время парсинга: {type(e).__name__}: {str(e)}", 404)
        print(f"Возникла ошибка во время парсинга: {type(e).__name__}: {str(e)}")
        return response

    conn.close()
    print(total)
    response = jsonify({"total_vacancies": str(total)})
    return response


if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0")
