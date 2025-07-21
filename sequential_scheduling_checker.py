"""
Модуль для проверки возможности последовательного размещения занятий.
"""
from time_utils import time_to_minutes, minutes_to_time
from timewindow_utils import find_slot_for_time
from constraint_registry import ConstraintType
from effective_bounds_utils import get_effective_bounds, classify_bounds

def _check_sequential_scheduling(optimizer, fixed_idx, window_idx):
    """
    Проверяет, можно ли разместить занятие с временным окном до или после фиксированного занятия.
    Использует effective_bounds для получения точных временных границ.
    """
    fixed_c = optimizer.classes[fixed_idx]
    window_c = optimizer.classes[window_idx]

    if fixed_c.day != window_c.day:
        return False

    try:
        # Используем effective_bounds для получения границ
        fixed_bounds = get_effective_bounds(optimizer, fixed_idx, fixed_c)
        window_bounds = get_effective_bounds(optimizer, window_idx, window_c)
        
        # Проверяем, что одно фиксировано, а другое с окном
        fixed_type = classify_bounds(fixed_bounds)
        window_type = classify_bounds(window_bounds)
        
        if fixed_type != 'fixed' or window_type != 'window':
            print(f"Warning: Expected fixed vs window, got {fixed_type} vs {window_type}")
            return False
            
        fixed_start = time_to_minutes(fixed_bounds.min_time)
        fixed_end = fixed_start + fixed_c.duration + getattr(fixed_c, 'pause_after', 0)

        window_start = time_to_minutes(window_bounds.min_time)
        window_end = time_to_minutes(window_bounds.max_time)
        window_duration = window_c.duration + getattr(window_c, 'pause_before', 0) + getattr(window_c, 'pause_after', 0)

        # Сначала пробуем разместить ДО фиксированного занятия
        latest_end_before_fixed = fixed_start - getattr(fixed_c, 'pause_before', 0)
        can_fit_before = (latest_end_before_fixed - window_start) >= window_duration
        if can_fit_before:
            latest_start_slot = optimizer.minutes_to_slot(latest_end_before_fixed - window_duration)
            constraint_expr = optimizer.model.Add(optimizer.start_vars[window_idx] <= latest_start_slot)
            print(f"SEQUENTIAL SCHEDULING: Window class {window_c.subject}"
                  f" scheduled BEFORE fixed class {fixed_c.subject}"
                  f" at {fixed_bounds.min_time}")
            return True

        # Если «до» не подошло, пробуем «после»
        earliest_start_after_fixed = fixed_end
        can_fit_after = (window_end - earliest_start_after_fixed) >= window_duration
        if can_fit_after:
            earliest_start_slot = optimizer.minutes_to_slot(earliest_start_after_fixed)
            constraint_expr = optimizer.model.Add(optimizer.start_vars[window_idx] >= earliest_start_slot)
            print(f"SEQUENTIAL SCHEDULING: Window class {window_c.subject}"
                  f" scheduled AFTER fixed class {fixed_c.subject}"
                  f" at {fixed_bounds.min_time}")
            return True

        # Ни туда, ни туда не влезает
        print(f"NO SEQUENTIAL SCHEDULING POSSIBLE between {fixed_c.subject}"
              f" and {window_c.subject}")
        return False
        
    except Exception as e:
        print(f"Warning: Could not use effective bounds in _check_sequential_scheduling: {e}")
        # Fallback к оригинальной логике
        fixed_start = time_to_minutes(fixed_c.start_time)
        fixed_end = fixed_start + fixed_c.duration + getattr(fixed_c, 'pause_after', 0)

        window_start = time_to_minutes(window_c.start_time)
        window_end = time_to_minutes(window_c.end_time)
        window_duration = window_c.duration + getattr(window_c, 'pause_before', 0) + getattr(window_c, 'pause_after', 0)

        # Сначала пробуем разместить ДО фиксированного занятия
        latest_end_before_fixed = fixed_start - getattr(fixed_c, 'pause_before', 0)
        can_fit_before = (latest_end_before_fixed - window_start) >= window_duration
        if can_fit_before:
            latest_start_slot = optimizer.minutes_to_slot(latest_end_before_fixed - window_duration)
            constraint_expr = optimizer.model.Add(optimizer.start_vars[window_idx] <= latest_start_slot)
            print(f"SEQUENTIAL SCHEDULING (fallback): Window class {window_c.subject}"
                  f" scheduled BEFORE fixed class {fixed_c.subject}")
            return True

        # Если «до» не подошло, пробуем «после»
        earliest_start_after_fixed = fixed_end
        can_fit_after = (window_end - earliest_start_after_fixed) >= window_duration
        if can_fit_after:
            earliest_start_slot = optimizer.minutes_to_slot(earliest_start_after_fixed)
            constraint_expr = optimizer.model.Add(optimizer.start_vars[window_idx] >= earliest_start_slot)
            print(f"SEQUENTIAL SCHEDULING (fallback): Window class {window_c.subject}"
                  f" scheduled AFTER fixed class {fixed_c.subject}")
            return True

        print(f"NO SEQUENTIAL SCHEDULING POSSIBLE between {fixed_c.subject} and {window_c.subject} (fallback)")
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
            constraint = optimizer.model.Add(optimizer.start_vars[idx_b] >= optimizer.start_vars[idx_a] + duration_a_slots + pause_after_slots + min_gap)
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
    в рамках их временных окон. Использует effective_bounds для получения точных границ.

    Args:
        optimizer: Экземпляр оптимизатора расписания.
        idx1, idx2: Индексы занятий.
        class1, class2: Объекты ScheduleClass.

    Returns:
        bool: True, если возможно разместить последовательно без конфликтов, иначе False.
    """
    try:
        # Используем effective_bounds для получения границ
        bounds1 = get_effective_bounds(optimizer, idx1, class1)
        bounds2 = get_effective_bounds(optimizer, idx2, class2)
        
        # Проверяем, что оба занятия с временными окнами
        type1 = classify_bounds(bounds1)
        type2 = classify_bounds(bounds2)
        
        if type1 != 'window' or type2 != 'window':
            print(f"Warning: Expected both window classes, got {type1} and {type2}")
            # Fallback к оригинальной логике
            return _check_two_window_classes_fallback(optimizer, idx1, idx2, class1, class2)
            
        # Конвертация времени в минуты
        start1 = time_to_minutes(bounds1.min_time)
        end1 = time_to_minutes(bounds1.max_time)
        duration1 = class1.duration
        pause1_before = getattr(class1, 'pause_before', 0)
        pause1_after = getattr(class1, 'pause_after', 0)

        start2 = time_to_minutes(bounds2.min_time)
        end2 = time_to_minutes(bounds2.max_time)
        duration2 = class2.duration
        pause2_before = getattr(class2, 'pause_before', 0)
        pause2_after = getattr(class2, 'pause_after', 0)

        # Проверяем, можно ли class1 полностью ДО class2
        latest_start1 = end1 - duration1
        earliest_start2 = start2
        can_1_before_2 = (latest_start1 + duration1 + pause1_after <= earliest_start2)

        # Проверяем, можно ли class2 полностью ДО class1
        latest_start2 = end2 - duration2
        earliest_start1 = start1
        can_2_before_1 = (latest_start2 + duration2 + pause2_after <= earliest_start1)

        # Проверяем, можно ли class1 сразу перед class2 (встык)
        can_1_adjacent_2 = False
        for s1 in range(earliest_start1, latest_start1 + 1):
            end_s1 = s1 + duration1 + pause1_after
            for s2 in range(earliest_start2, latest_start2 + 1):
                if end_s1 <= s2:
                    can_1_adjacent_2 = True
                    break
            if can_1_adjacent_2:
                break
                
        return can_1_before_2 or can_2_before_1 or can_1_adjacent_2
                
    except Exception as e:
        print(f"Warning: Could not use effective bounds in check_two_window_classes: {e}")
        # Fallback к оригинальной логике
        return _check_two_window_classes_fallback(optimizer, idx1, idx2, class1, class2)


def _check_two_window_classes_fallback(optimizer, idx1, idx2, class1, class2):
    """
    Fallback версия check_two_window_classes используя оригинальные поля start_time/end_time.
    """
    # Конвертация времени в минуты
    start1 = time_to_minutes(class1.start_time)
    end1 = time_to_minutes(class1.end_time)
    duration1 = class1.duration
    pause1_before = getattr(class1, 'pause_before', 0)
    pause1_after = getattr(class1, 'pause_after', 0)

    start2 = time_to_minutes(class2.start_time)
    end2 = time_to_minutes(class2.end_time)
    duration2 = class2.duration
    pause2_before = getattr(class2, 'pause_before', 0)
    pause2_after = getattr(class2, 'pause_after', 0)

    # Проверяем, можно ли class1 полностью ДО class2
    latest_start1 = end1 - duration1
    earliest_start2 = start2
    can_1_before_2 = (latest_start1 + duration1 + pause1_after <= earliest_start2)

    # Проверяем, можно ли class2 полностью ДО class1
    latest_start2 = end2 - duration2
    earliest_start1 = start1
    can_2_before_1 = (latest_start2 + duration2 + pause2_after <= earliest_start1)

    # Проверяем, можно ли class1 сразу перед class2 (встык)
    can_1_adjacent_2 = False
    for s1 in range(earliest_start1, latest_start1 + 1):
        end_s1 = s1 + duration1 + pause1_after
        for s2 in range(earliest_start2, latest_start2 + 1):
            if end_s1 <= s2:
                can_1_adjacent_2 = True
                break
        if can_1_adjacent_2:
            break

    # Проверяем, можно ли class2 сразу перед class1 (встык)
    can_2_adjacent_1 = False
    for s2 in range(earliest_start2, latest_start2 + 1):
        end_s2 = s2 + duration2 + pause2_after
        for s1 in range(earliest_start1, latest_start1 + 1):
            if end_s2 <= s1:
                can_2_adjacent_1 = True
                break
        if can_2_adjacent_1:
            break

    # Если есть хотя бы один способ непересекающегося размещения — возвращаем True
    return can_1_before_2 or can_2_before_1 or can_1_adjacent_2 or can_2_adjacent_1

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