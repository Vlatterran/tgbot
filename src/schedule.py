import asyncio
import datetime
import json
import logging
import os
import re
import time
import urllib.parse
from typing import Union, Mapping, List

import httpx
from bs4 import BeautifulSoup

MINUTE = 60
HOUR = MINUTE * 60
DAY = HOUR * 24
PATH = Union[str, bytes, os.PathLike]


class Schedule:
    def __init__(self, schedule: Mapping):
        self.schedule = schedule

    @classmethod
    def from_json_file(cls, _file: PATH, /):
        with open(_file) as f:
            return cls(json.load(f))

    @classmethod
    def from_json(cls, _json_string: str, /):
        return cls(json.loads(_json_string))

    dec_ru = {
        0: 'Понедельник',
        1: 'Вторник',
        2: 'Среда',
        3: 'Четверг',
        4: 'Пятница',
        5: 'Суббота',
        6: 'Воскресенье'
    }
    ru_dec = {
        'Понедельник': 0,
        'Вторник': 1,
        'Среда': 2,
        'Четверг': 3,
        'Пятница': 4,
        'Суббота': 5,
        'Воскресенье': 6
    }
    shortens = {
        'Числ': 'Числитель',
        'Знам': 'Знаменатель',
        'Еж': 'Еженедельно',
    }

    @staticmethod
    def line_template(i):
        return f"\n{'=' * 40}\n{i['Время занятий']}: {i['Наименование дисциплины']}" \
               f"\n{i['Преподаватель']} | {i['Аудитория']} | {i['Вид занятий']}" \
               f" {('|' + i['Частота']) if 'Частота' in i else ''}"

    def lectures(self, day: str):
        date_regex = r'(\b(0?[1-9]|[1-2][0-9]|3[0-1])[\.\\]([1][0-2]|0?[1-9])\b)'
        if re.match(date_regex, day):
            date = [*map(int, re.split(r'[.\\-]', day))]
            requested_date = datetime.datetime(day=date[0], month=date[1], year=time.localtime().tm_year)
        else:
            requested_date = datetime.datetime.now()
            d = day.title()
            if d == '':
                pass
            if d == 'Завтра':
                requested_date += datetime.timedelta(days=1)
            elif d in self.ru_dec:
                requested_date += datetime.timedelta(days=(self.ru_dec[d] - requested_date.weekday()) % 7)
        try:
            requested_date = requested_date.timetuple()
            week_day = self.dec_ru[requested_date.tm_wday]
            week_type = 'Числитель' if self.is_week_even(requested_date) else 'Знаменатель'
            requested_schedule: List[dict] = (
                    self.schedule[week_day][week_type] +
                    self.schedule[week_day].get('Еженедельно', [])
            )
            result = f'Расписание на {time.strftime("%d.%m.%Y", requested_date)} ' \
                     f'({week_day.lower()}/{week_type.lower()})'
            for i in sorted(requested_schedule, key=lambda line: line['Время занятий']):
                result += self.line_template(i)
            return result
        except KeyError as e:
            print(e)
            return 'Не удалось найти расписание на указанный день'

    @staticmethod
    def is_week_even(day: time.struct_time):
        return ((day.tm_yday + datetime.datetime(day=1, month=1, year=2022).weekday()) // 7) % 2 == 1

    @classmethod
    async def parse(cls, *groups: str):
        async with httpx.AsyncClient() as client:
            response = await client.post('https://raspisanie.madi.ru/tplan/tasks/task3,7_fastview.php',
                                         data={'step_no': 1, 'task_id': 7})
            logging.info(response)
            soup = BeautifulSoup(response.text,
                                 features='lxml')
            _groups = dict(map(lambda x: (x.attrs['value'], x.text),
                               soup.select('ul>li')))
            weekday = None
            schedule = {}
            groups = set(map(str.lower, groups))
            for group_id, group_name in filter(lambda kv: kv[1].lower() in groups or not groups, _groups.items()):
                response = await client.post('https://raspisanie.madi.ru/tplan/tasks/tableFiller.php',
                                             data={'tab': 7, 'gp_name': group_name, 'gp_id': group_id})
                logging.info(response.text)
                soup = BeautifulSoup(response.text, features='lxml')
                raws = iter(soup.select('.timetable tr'))
                for raw in raws:
                    children = [*raw.findChildren(('td', 'th'))]
                    logging.info(children)
                    if sum(1 for _ in children) == 1:
                        try:
                            weekday = raw.text
                        except KeyError:
                            break
                        next(raws)
                    else:
                        context = {'weekday': weekday, 'group': group_name}
                        line = {}
                        for i, cell in enumerate(children):
                            logging.debug(i, cell)
                            if i == 0:
                                line['Время занятий'] = cell.text
                            elif i == 1:
                                line['Наименование дисциплины'] = cell.text
                            elif i == 2:
                                line['Вид занятий'] = cell.text
                            elif i == 3:
                                context['frequency'] = cell.text
                            elif i == 4:
                                line['Аудитория'] = cell.text
                            elif i == 5:
                                if cell.text == '':
                                    t = '--'
                                else:
                                    t = cell.text
                                line['Преподаватель'] = re.sub(r'\s{2,}', ' ', t)
                        try:
                            day = schedule.setdefault(context['weekday'], {})
                            logging.info(context)
                            if '.' in context['frequency']:
                                f = context['frequency'].split('.')
                                context['frequency'] = cls.shortens[f[0]]
                                line['Частота'] = f[1]

                            day.setdefault(context['frequency'], []).append(line)
                        except KeyError:
                            if context['weekday'] != '\nПолнодневные занятия\n':
                                raise
                        except Exception as e:
                            print(type(e), e, f'\n{context}')
                            logging.exception(e)
                            break
        return schedule

    def week_lectures(self, week_type: str):
        if week_type == '':
            f = 'Числитель' if self.is_week_even(datetime.date.today().timetuple()) else 'Знаменатель'
        else:
            f = week_type.title()
        result = f'Расписание на {f}'
        for day in self.ru_dec:
            try:
                requested_schedule = self.schedule[day][f]
                result += f'\n{day}'
                for i in requested_schedule:
                    result += self.line_template(i=i)
            except KeyError:
                pass
        return result

    async def update(self):
        self.schedule = await self.get_schedule(self.onedrive_url)

    @staticmethod
    async def get_schedule(onedrive_url):
        async with httpx.AsyncClient() as client:
            location_response = client.get(onedrive_url)
            location_url = (await location_response).headers['location']
            location = await client.get(location_url)
            query = urllib.parse.parse_qs(location.url.query)
            schedule_url = f'https://api.onedrive.com/drives/{(query[b"resid"][0].split(b"!")[0].decode())}' \
                           f'/items/{query[b"resid"][0].decode()}/content'
            return (await client.get(schedule_url, params={'authkey': query[b'authkey'][0].decode()},
                                     follow_redirects=True)).json()


if __name__ == '__main__':
    a = asyncio.run(Schedule.parse('4ВбИТС'))
    with open('schedule.json', 'w', encoding='utf8') as file:
        json.dump(a, file, indent=4, ensure_ascii=False)
