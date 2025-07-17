"""
Утилиты для работы с временными окнами в планировании расписания.

Этот модуль содержит чистые функции-помощники для работы с временными слотами,
построения транзитивных связей и других базовых операций с временными окнами.
"""

from time_utils import time_to_minutes, minutes_to_time

__all__ = ['find_slot_for_time', 'build_transitive_links', 'are_classes_transitively_linked']


def find_slot_for_time(time_slots, time_str, time_interval=15):
    """
    Находит индекс слота времени для заданной строки времени.
    
    Args:
        time_slots: Список строк времени (HH:MM)
        time_str: Строка времени для поиска
        time_interval: Интервал времени в минутах
        
    Returns:
        int: Индекс слота или None, если не найден
    """
    target_minutes = time_to_minutes(time_str)
    
    # Округляем к ближайшему действительному интервалу
    remainder = target_minutes % time_interval
    if remainder == 0:
        rounded_minutes = target_minutes
    else:
        rounded_minutes = target_minutes - remainder
    
    rounded_time = minutes_to_time(rounded_minutes)
    
    # Ищем точное совпадение с округленным временем
    for slot_idx, slot_time in enumerate(time_slots):
        if slot_time == rounded_time:
            return slot_idx
    
    # Если точного совпадения нет, ищем ближайший допустимый слот
    best_slot = None
    min_diff = float('inf')
    
    for slot_idx, slot_time in enumerate(time_slots):
        slot_minutes = time_to_minutes(slot_time)
        # Проверяем, является ли слот допустимым по интервалу
        if slot_minutes % time_interval == 0:
            diff = abs(slot_minutes - target_minutes)
            if diff < min_diff:
                min_diff = diff
                best_slot = slot_idx
    
    return best_slot


def build_transitive_links(optimizer):
    """
    Строит транзитивные связи между занятиями на основе linked_classes.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        
    Returns:
        dict: Словарь {class_idx: set(linked_class_indices)}
    """
    transitive_links = {}
    
    # Инициализируем пустые множества для каждого класса
    for idx in range(len(optimizer.classes)):
        transitive_links[idx] = set()
    
    # Добавляем прямые связи
    for idx, c in enumerate(optimizer.classes):
        if hasattr(c, 'linked_classes') and c.linked_classes:
            for linked_class in c.linked_classes:
                try:
                    linked_idx = optimizer._find_class_index(linked_class)
                    transitive_links[idx].add(linked_idx)
                except ValueError:
                    continue
    
    # Строим транзитивное замыкание
    changed = True
    while changed:
        changed = False
        for idx in transitive_links:
            # Для каждого связанного класса добавляем его связи
            new_links = set()
            for linked_idx in transitive_links[idx]:
                new_links.update(transitive_links[linked_idx])
            
            # Если добавились новые связи, отмечаем изменение
            old_size = len(transitive_links[idx])
            transitive_links[idx].update(new_links)
            if len(transitive_links[idx]) > old_size:
                changed = True
    
    return transitive_links


def are_classes_transitively_linked(optimizer, idx_i, idx_j):
    """
    Проверяет, связаны ли два класса транзитивно через linked_classes.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        idx_i, idx_j: Индексы проверяемых классов
        
    Returns:
        bool: True, если классы связаны транзитивно
    """
    if not hasattr(optimizer, '_transitive_links'):
        optimizer._transitive_links = build_transitive_links(optimizer)
    
    return (idx_j in optimizer._transitive_links.get(idx_i, set()) or 
            idx_i in optimizer._transitive_links.get(idx_j, set()))
