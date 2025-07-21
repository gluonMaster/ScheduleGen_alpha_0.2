"""
Адаптер для улучшения обработки временных окон в планировании расписания.

Этот модуль предоставляет высокоуровневые функции для применения улучшений
временных окон и настройки целевой функции оптимизатора.
"""

from time_utils import time_to_minutes, minutes_to_time
from timewindow_utils import find_slot_for_time
from separation_constraints import analyze_related_classes
from constraint_registry import ConstraintType
from effective_bounds_utils import (
    initialize_effective_bounds, set_effective_bounds, get_effective_bounds,
    update_bounds_from_constraint, print_bounds_report
)

__all__ = ['apply_timewindow_improvements', 'add_objective_weights_for_timewindows']


def apply_timewindow_improvements(optimizer):
    """
    Применяет улучшения для обработки временных окон к оптимизатору.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        
    Returns:
        bool: True, если улучшения применены успешно
    """
    print("\nApplying timewindow scheduling improvements...")

    # ЗАЩИТА: Проверяем, не применялись ли уже улучшения временных окон
    if hasattr(optimizer, 'timewindow_already_processed') and optimizer.timewindow_already_processed:
        print("WARNING: Timewindow improvements already applied, skipping to prevent constraint conflicts")
        return True

    # Инициализируем систему эффективных границ
    initialize_effective_bounds(optimizer)

    prefer_late_start = set()  # Индексы занятий, которым лучше начинаться позже

    # Сбрасываем кэш обработанных проверок между занятиями
    try:
        from sequential_scheduling_checker import reset_window_checks_cache
        reset_window_checks_cache()
    except ImportError:
        print("Warning: Could not reset window checks cache.")
    
    # Словарь для отслеживания уже обработанных пар занятий
    processed_pairs = set()

    # Проверяем, инициализированы ли уже переменные оптимизатора
    if not hasattr(optimizer, 'start_vars') or not optimizer.start_vars:
        print("Warning: Optimizer variables not initialized yet. Call optimizer.build_model() before applying timewindow improvements.")
        return False
                    
    # Общий анализ занятий с временными окнами
    window_classes = []
    for idx, c in enumerate(optimizer.classes):
        if c.start_time and c.end_time:
            window_classes.append((idx, c))
    
    print(f"\nFound {len(window_classes)} classes with time windows.")
    
    # Для каждого занятия с временным окном добавляем ограничения на временное окно
    for idx_i, c_i in window_classes:
        # ЗАЩИТА: Проверяем, не применены ли уже ограничения цепочки для этого класса
        if hasattr(optimizer, 'chain_constraints_applied') and idx_i in optimizer.chain_constraints_applied:
            print(f"  Skipping window constraints for class {idx_i} - chain constraints already applied")
            continue
            
        # Проверяем имеется ли уже фиксированное ограничение для этого занятия
        # и если нет, добавляем ограничения на временное окно
        if not isinstance(optimizer.start_vars[idx_i], int):
            window_start_time = c_i.start_time
            window_end_time = c_i.end_time
            
            # Используем функции из effective_bounds_utils
            from effective_bounds_utils import time_to_slot
            
            window_start_slot = time_to_slot(optimizer, window_start_time)
            window_end_slot = time_to_slot(optimizer, window_end_time)
            
            if window_start_slot is not None and window_end_slot is not None:
                # Рассчитываем максимальное время начала, чтобы уложиться в окно
                duration_slots = c_i.duration // optimizer.time_interval
                max_start_slot = window_end_slot - duration_slots
                
                # Добавляем ограничения на временное окно
                constraint1 = optimizer.model.Add(optimizer.start_vars[idx_i] >= window_start_slot)
                constraint2 = optimizer.model.Add(optimizer.start_vars[idx_i] <= max_start_slot)
                
                # Устанавливаем эффективные границы
                set_effective_bounds(optimizer, idx_i, window_start_slot, max_start_slot,
                                   "timewindow_adapter", f"Window: {window_start_time}-{window_end_time}")
                
                print(f"  Added window constraints for class {idx_i}: start between slots {window_start_slot} and {max_start_slot}")
    
    # Применяем новый алгоритм комплексного анализа связанных занятий
    processed_pairs = analyze_related_classes(optimizer)
    
    # Добавляем веса в целевую функцию для временных окон
    add_objective_weights_for_timewindows(optimizer)
    
    # Отмечаем, что улучшения применены
    optimizer.timewindow_already_processed = True
    
    # Выводим отчет по эффективным границам
    print_bounds_report(optimizer)
    
    print(f"Timewindow improvements applied successfully. Processed {len(processed_pairs)} class pairs.")
    return True


def add_objective_weights_for_timewindows(optimizer):
    """
    Добавляет веса в целевую функцию для улучшения обработки временных окон.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
    """
    print("\nAdding objective weights for timewindow optimization...")
    
    # Получаем предпочтения для позднего старта
    prefer_late_start = getattr(optimizer, 'prefer_late_start', set())
    
    # Создаем дополнительные переменные для целевой функции
    timewindow_objectives = []
    
    for idx, c in enumerate(optimizer.classes):
        if c.start_time and c.end_time:  # Занятие с временным окном
            # Поощряем размещение ближе к началу временного окна для большинства занятий
            if idx not in prefer_late_start:
                # Создаем переменную для "раннего" начала
                early_start_bonus = optimizer.model.NewIntVar(0, 1000, f"early_start_bonus_{idx}")
                
                # Рассчитываем слоты для временного окна
                window_start_slot = find_slot_for_time(optimizer.time_slots, c.start_time, optimizer.time_interval)
                if window_start_slot is not None:
                    # Бонус за начало ближе к началу окна
                    constraint_expr = optimizer.model.Add(early_start_bonus >= (window_start_slot + 10) - optimizer.start_vars[idx])
                    constraint_expr = optimizer.model.Add(early_start_bonus >= 0)
                    
                    timewindow_objectives.append(early_start_bonus)
            
            else:
                # Для занятий с предпочтением позднего старта
                late_start_bonus = optimizer.model.NewIntVar(0, 1000, f"late_start_bonus_{idx}")
                
                # Рассчитываем слоты для временного окна
                window_end_slot = find_slot_for_time(optimizer.time_slots, c.end_time, optimizer.time_interval)
                if window_end_slot is not None:
                    # Бонус за начало ближе к концу окна
                    duration_slots = c.duration // optimizer.time_interval
                    max_start_slot = window_end_slot - duration_slots
                    
                    constraint_expr = optimizer.model.Add(late_start_bonus >= optimizer.start_vars[idx] - (max_start_slot - 10))
                    constraint_expr = optimizer.model.Add(late_start_bonus >= 0)
                    
                    timewindow_objectives.append(late_start_bonus)
    
    # Сохраняем дополнительные цели в оптимизаторе
    if not hasattr(optimizer, 'additional_objectives'):
        optimizer.additional_objectives = []
    
    optimizer.additional_objectives.extend(timewindow_objectives)
    
    print(f"Added {len(timewindow_objectives)} timewindow objectives to the model.")
    
    # Возвращаем список целей для использования в objective.py
    return timewindow_objectives
