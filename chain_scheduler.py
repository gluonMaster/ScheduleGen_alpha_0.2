"""
Модуль для планирования цепочек связанных занятий.

Этот модуль содержит функции для размещения цепочек занятий внутри временных окон
и определения занятых интервалов времени.
"""

from time_utils import time_to_minutes, minutes_to_time

__all__ = ['schedule_chain', 'chain_busy_intervals']


def schedule_chain(chain, window):
    """
    Размещает все занятия цепочки back-to-back, начиная с window.start (в минутах),
    вставляет pause_after после каждого занятия (кроме последнего).
    Если итоговое время > window.end, кидает ValueError.
    Возвращает {klass: (start_min, end_min)}.
    
    Args:
        chain: Список занятий (классов) для размещения
        window: Временное окно с атрибутами start и end (в минутах)
        
    Returns:
        dict: Словарь {класс: (начало_в_минутах, конец_в_минутах)}
        
    Raises:
        ValueError: Если цепочка не помещается в указанное временное окно
    """
    if not chain:
        return {}
    
    schedule = {}
    current_time = window.start
    
    for i, class_obj in enumerate(chain):
        # Получаем продолжительность занятия
        duration = getattr(class_obj, 'duration', 45)  # По умолчанию 45 минут
        
        # Вычисляем время начала и окончания
        start_time = current_time
        end_time = start_time + duration
        
        # Добавляем в расписание
        schedule[class_obj] = (start_time, end_time)
        
        # Подготавливаем время для следующего занятия
        current_time = end_time
        
        # Добавляем паузу после занятия (кроме последнего)
        if i < len(chain) - 1:
            pause_duration = getattr(class_obj, 'pause_after', 15)  # По умолчанию 15 минут
            current_time += pause_duration
    
    # Проверяем, что вся цепочка помещается в окно
    if current_time > window.end:
        total_duration = current_time - window.start
        window_duration = window.end - window.start
        raise ValueError(
            f"Цепочка не помещается в временное окно. "
            f"Требуется {total_duration} минут, доступно {window_duration} минут. "
            f"Окно: {minutes_to_time(window.start)}-{minutes_to_time(window.end)}"
        )
    
    return schedule


def chain_busy_intervals(schedule):
    """
    По расписанию цепочки возвращает отсортированный список busy-intervals.
    
    Args:
        schedule: Словарь {класс: (начало_в_минутах, конец_в_минутах)}
        
    Returns:
        list: Отсортированный список кортежей (начало, конец) занятых интервалов
    """
    if not schedule:
        return []
    
    # Извлекаем все интервалы времени
    intervals = list(schedule.values())
    
    # Сортируем по времени начала
    intervals.sort(key=lambda x: x[0])
    
    # Объединяем перекрывающиеся или смежные интервалы
    merged_intervals = []
    current_start, current_end = intervals[0]
    
    for start, end in intervals[1:]:
        if start <= current_end:  # Интервалы перекрываются или смежные
            current_end = max(current_end, end)
        else:
            # Сохраняем текущий интервал и начинаем новый
            merged_intervals.append((current_start, current_end))
            current_start, current_end = start, end
    
    # Добавляем последний интервал
    merged_intervals.append((current_start, current_end))
    
    return merged_intervals
