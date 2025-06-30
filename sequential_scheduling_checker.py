"""
Модуль для проверки возможности последовательного размещения занятий.
"""
from time_utils import time_to_minutes, minutes_to_time

def _check_sequential_scheduling(optimizer, fixed_idx, window_idx):
    """
    Проверяет, можно ли разместить занятие с временным окном до или после фиксированного занятия.
    Если возможно — добавляет соответствующее ограничение. Если оба варианта невозможны — возвращает False.
    """
    fixed_c = optimizer.classes[fixed_idx]
    window_c = optimizer.classes[window_idx]

    if fixed_c.day != window_c.day:
        return False

    fixed_start = time_to_minutes(fixed_c.start_time)
    fixed_end = fixed_start + fixed_c.duration + fixed_c.pause_after

    window_start = time_to_minutes(window_c.window_start)
    window_end = time_to_minutes(window_c.window_end)
    window_duration = window_c.duration + window_c.pause_before + window_c.pause_after

    # Сначала пробуем разместить ДО фиксированного занятия
    latest_end_before_fixed = fixed_start - fixed_c.pause_before
    can_fit_before = (latest_end_before_fixed - window_start) >= window_duration
    if can_fit_before:
        latest_start_slot = optimizer.minutes_to_slot(latest_end_before_fixed - window_duration)
        optimizer.model.Add(optimizer.start_vars[window_idx] <= latest_start_slot)
        print(f"SEQUENTIAL SCHEDULING: Window class {window_c.subject}"
              f" scheduled BEFORE fixed class {fixed_c.subject}"
              f" at {fixed_c.start_time}")
        return True

    # Если «до» не подошло, пробуем «после»
    earliest_start_after_fixed = fixed_end
    can_fit_after = (window_end - earliest_start_after_fixed) >= window_duration
    if can_fit_after:
        earliest_start_slot = optimizer.minutes_to_slot(earliest_start_after_fixed)
        optimizer.model.Add(optimizer.start_vars[window_idx] >= earliest_start_slot)
        print(f"SEQUENTIAL SCHEDULING: Window class {window_c.subject}"
              f" scheduled AFTER fixed class {fixed_c.subject}"
              f" at {fixed_c.start_time}")
        return True

    # Ни туда, ни туда не влезает
    print(f"NO SEQUENTIAL SCHEDULING POSSIBLE between {fixed_c.subject}"
          f" and {window_c.subject}")
    return False

# Дополнительно: поддержка связанных оконных занятий в одной цепочке (linked_constraints-aware scheduling)
def _group_window_linked_classes(optimizer):
    """
    Возвращает список списков — групп оконных занятий, связанных через linked_constraints.
    """
    linked_groups = []
    seen = set()
    for chain in optimizer.linked_chains:
        window_chain = [idx for idx in chain if optimizer.classes[idx].has_time_window]
        if len(window_chain) > 1:
            frozen = tuple(window_chain)
            if frozen not in seen:
                linked_groups.append(window_chain)
                seen.add(frozen)
    return linked_groups

def enforce_window_chain_sequencing(optimizer):
    """
    Добавляет ограничения между оконными занятиями, связанными логикой последовательности.
    """
    # Проверяем, были ли уже применены улучшения по обработке временных окон
    if hasattr(optimizer, "timewindow_already_processed") and optimizer.timewindow_already_processed:
        print("Skipping window chain sequencing - already processed by timewindow adapter")
        return
        
    # Отмечаем, что мы обработали эти ограничения
    optimizer.window_chains_processed = True
    
    for chain in _group_window_linked_classes(optimizer):
        for i in range(len(chain) - 1):
            idx_a = chain[i]
            idx_b = chain[i + 1]

            a = optimizer.classes[idx_a]
            b = optimizer.classes[idx_b]

            if a.day != b.day:
                continue  # Только один день поддерживается

            duration_a_slots = a.duration // optimizer.time_interval
            pause_after_slots = a.pause_after // optimizer.time_interval
            
            # Используем точное время паузы
            min_gap = b.pause_before // optimizer.time_interval
            
            # Явно обозначаем, что это ограничение связанных окон
            constraint = optimizer.model.Add(
                optimizer.start_vars[idx_b] >= optimizer.start_vars[idx_a] + duration_a_slots + pause_after_slots + min_gap
            )
            print(f"LINKED WINDOW SEQUENCING: {a.subject} → {b.subject} (constraint applied)")

            #---Debug---
            print(f"DEBUG: Preparing chain constraint between {idx_a} -> {idx_b}:")
            print(f"  - Class {idx_a} ({a.subject}): duration={duration_a_slots}, pause_after={pause_after_slots}")
            print(f"  - Class {idx_b} ({b.subject}): pause_before={min_gap}")
            print(f"  - Total gap required: {duration_a_slots + pause_after_slots + min_gap} slots")
            #-----------
            
            # Сохраняем примененные ограничения для будущей проверки
            if not hasattr(optimizer, "applied_constraints"):
                optimizer.applied_constraints = {}
            
            pair_key = (idx_a, idx_b)
            optimizer.applied_constraints[pair_key] = constraint

            #---Debug---
            print(f"DEBUG: Added chain constraint {constraint}: start_vars[{idx_b}] >= start_vars[{idx_a}] + {duration_a_slots + pause_after_slots + min_gap}")
            #-----------

# Глобальный словарь для отслеживания уже обработанных проверок
# Это позволит избежать дублирующих сообщений и ограничений
_processed_window_checks = set()

# sequential_scheduling_checker.py

def check_two_window_classes(optimizer, idx1, idx2, class1, class2):
    """
    Проверяет, можно ли разместить два занятия последовательно без пересечения
    в рамках их временных окон.

    Args:
        optimizer: Экземпляр оптимизатора расписания.
        idx1, idx2: Индексы занятий.
        class1, class2: Объекты ScheduleClass.

    Returns:
        bool: True, если возможно разместить последовательно без конфликтов, иначе False.
    """

    # Конвертация времени в минуты
    start1 = time_to_minutes(class1.start_time)
    end1 = time_to_minutes(class1.end_time)

    start2 = time_to_minutes(class2.start_time)
    end2 = time_to_minutes(class2.end_time)

    # Длительности в минутах
    duration1 = class1.duration
    duration2 = class2.duration

    # Возможные временные диапазоны для начала
    earliest_start1 = start1
    latest_start1 = end1 - duration1

    earliest_start2 = start2
    latest_start2 = end2 - duration2

    # Проверяем, можем ли разместить class1 перед class2
    can_schedule_1_before_2 = (earliest_start1 + duration1 <= latest_start2)

    # Проверяем, можем ли разместить class2 перед class1
    can_schedule_2_before_1 = (earliest_start2 + duration2 <= latest_start1)

    # Проверяем наложение окон вообще
    overlap_start = max(start1, start2)
    overlap_end = min(end1, end2)
    total_overlap_time = overlap_end - overlap_start

    total_duration_needed = duration1 + duration2

    # Если общее пересечение окон достаточно большое для двух занятий подряд
    enough_overlap = total_overlap_time >= total_duration_needed

    # Логика возврата
    return can_schedule_1_before_2 or can_schedule_2_before_1 or enough_overlap

def time_to_minutes(time_str):
    """Преобразует строку времени 'HH:MM' в количество минут от начала суток."""
    hours, minutes = map(int, time_str.split(":"))
    return hours * 60 + minutes


def reset_window_checks_cache():
    """
    Сбрасывает кэш обработанных проверок. Эту функцию следует вызывать
    перед каждым новым запуском оптимизатора, чтобы избежать сохранения
    состояния между запусками.
    """
    global _processed_window_checks
    _processed_window_checks = set()
    print("Window checks cache has been reset.")

def find_slot_for_time(time_slots, time_str):
    """
    Находит индекс слота времени для заданной строки времени.
    
    Args:
        time_slots: Список строк времени (HH:MM)
        time_str: Строка времени для поиска
        
    Returns:
        int: Индекс слота или None, если не найден
    """
    target_minutes = time_to_minutes(time_str)
    
    # Ищем точное совпадение
    for slot_idx, slot_time in enumerate(time_slots):
        slot_minutes = time_to_minutes(slot_time)
        if slot_minutes == target_minutes:
            return slot_idx
    
    # Если точного совпадения нет, ищем ближайший слот
    best_slot = None
    min_diff = float('inf')
    
    for slot_idx, slot_time in enumerate(time_slots):
        slot_minutes = time_to_minutes(slot_time)
        diff = abs(slot_minutes - target_minutes)
        
        if diff < min_diff:
            min_diff = diff
            best_slot = slot_idx
    
    return best_slot