# Генератор школьного расписания с OR-Tools

## Обзор

Данная система использует библиотеку Google OR-Tools для создания оптимизированного школьного расписания на основе входных данных из Excel-файла. Результатом работы является Excel-файл `optimized_schedule.xlsx` с оптимизированным расписанием.

## Структура проекта

Проект разделен на несколько модулей:

1. `reader.py` - содержит классы и функции для чтения данных из Excel-файла
2. `scheduler_base.py` - основной класс оптимизатора расписания
3. `model_variables.py` - создание переменных оптимизационной модели
4. `constraints.py` - добавление ограничений в модель
5. `objective.py` - определение функции оптимизации
6. `output_utils.py` - утилиты для вывода и экспорта результатов
7. `main_sch.py` - основной скрипт для запуска приложения

## Установка

1. Установите необходимые зависимости:

```bash
pip install pandas numpy openpyxl ortools
```

## Использование

Для генерации расписания выполните:

```bash
python main_sch.py xlsx_initial/schedule_planning.xlsx --time-limit 300 --verbose --time-interval 5
```

Параметры:
- `schedule_planning.xlsx` - путь к Excel-файлу с исходными данными
- `--output optimized_schedule.xlsx` - путь к выходному Excel-файлу (по умолчанию: optimized_schedule.xlsx)
- `--time-limit 300` - ограничение времени оптимизации в секундах (по умолчанию: 300)
- `--time-interval 5` - интервал времени для планирования в минутах (в даннном случае 5 минкт, но по умолчанию: 15)
- `--verbose` - включить подробный вывод

## Формат входного Excel-файла

Excel-файл должен содержать лист "Plannung" со следующей структурой:

- Информация о занятиях расположена в столбцах B, C, D и начинается со второй строки
- Каждое описание занятия занимает 14 последовательных строк
- Структура секции планирования:
  - Строка 1: Название предмета
  - Строка 2: Название группы
  - Строка 3: Имя преподавателя
  - Строка 4: Основной кабинет
  - Строки 5-7: Альтернативные кабинеты
  - Строка 8: Название здания
  - Строка 9: Продолжительность занятия в минутах
  - Строка 10: День недели (Mo, Di, Mi, Do, Fr, Sa)
  - Строка 11: Время начала (формат ЧЧ:ММ)
  - Строка 12: Время окончания (формат ЧЧ:ММ) - опционально
  - Строка 13: Пауза до занятия (в минутах)
  - Строка 14: Пауза после занятия (в минутах)

- Занятия в столбцах C и D связаны с занятием в столбце B и представляют последовательные активности

## Ограничения оптимизации

При генерации расписания учитываются следующие ограничения:

1. **Конфликты ресурсов**: 
   - Преподаватель не может вести два занятия одновременно
   - Группа не может посещать два занятия одновременно
   - Кабинет не может использоваться для двух занятий одновременно

2. **Связанные занятия**:
   - Занятия в столбцах C и D следуют за занятием в столбце B
   - Связанные занятия должны быть запланированы на один день
   - Связанные занятия должны быть запланированы с соответствующими паузами между ними

3. **Фиксированное время и кабинеты**:
   - Занятия с указанным временем начала должны быть запланированы на это время
   - Занятия с указанными кабинетами должны быть запланированы в этих кабинетах

## Цели оптимизации

Оптимизатор расписания стремится:

1. Минимизировать количество перемещений преподавателей между кабинетами в течение дня
2. Минимизировать "окна" в расписании преподавателей и групп
3. Эффективно использовать доступные кабинеты и временные слоты

## Выходные данные

Результатом работы приложения является файл `optimized_schedule.xlsx` с оптимизированным расписанием. В случае невозможности построения расписания (противоречивые ограничения) выводится соответствующее информативное сообщение.

## Исправленные проблемы

1. **Обработка связанных классов** - теперь все классы (включая связанные) добавляются в общий список для обработки
2. **Обработка булевых значений** - исправлена проблема с использованием булевых переменных/литералов в OR-Tools
3. **Модульная структура** - код разбит на логические модули для удобства поддержки и расширения
