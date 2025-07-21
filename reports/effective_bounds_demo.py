"""
Тестовый файл для демонстрации системы эффективных границ.

Этот файл показывает, как использовать новую систему effective_bounds
для отслеживания актуальных временных ограничений занятий.
"""

from effective_bounds_utils import (
    initialize_effective_bounds, set_effective_bounds, get_effective_bounds,
    update_bounds_from_constraint, print_bounds_report, get_bounds_summary
)


def demo_effective_bounds(optimizer):
    """
    Демонстрация работы системы эффективных границ.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
    """
    print("\n" + "="*60)
    print("EFFECTIVE BOUNDS SYSTEM DEMONSTRATION")
    print("="*60)
    
    # Инициализируем систему
    initialize_effective_bounds(optimizer)
    
    # Пример 1: Установка границ для фиксированного времени
    print("\n1. Setting fixed time bounds for class 0:")
    if len(optimizer.classes) > 0:
        class_0 = optimizer.classes[0]
        print(f"   Class 0: {class_0.subject} at {class_0.start_time}")
        
        # Симулируем установку фиксированного времени
        if class_0.start_time:
            from effective_bounds_utils import time_to_slot
            fixed_slot = time_to_slot(optimizer, class_0.start_time)
            set_effective_bounds(optimizer, 0, fixed_slot, fixed_slot, 
                               "manual_demo", "Demo: Fixed time constraint")
    
    # Пример 2: Обновление границ после применения ограничения
    print("\n2. Updating bounds after applying chain constraint:")
    if len(optimizer.classes) > 1:
        # Симулируем ограничение цепочки: класс 1 должен начаться не раньше чем через 5 слотов после класса 0
        update_bounds_from_constraint(optimizer, 1, "chain_ordering", 
                                    min_slot=5, description="Demo: Chain constraint - must start after slot 5")
    
    # Пример 3: Получение эффективных границ с fallback
    print("\n3. Getting effective bounds with fallback:")
    for i in range(min(3, len(optimizer.classes))):
        bounds = get_effective_bounds(optimizer, i)
        print(f"   Class {i}: {bounds}")
    
    # Пример 4: Сводка по всем границам
    print("\n4. Bounds summary:")
    summary = get_bounds_summary(optimizer)
    print(f"   Total classes: {summary['total_classes']}")
    print(f"   Classes with bounds: {summary['classes_with_bounds']}")
    print(f"   Sources: {list(summary['bounds_by_source'].keys())}")
    
    # Полный отчет
    print_bounds_report(optimizer)
    
    print("\n" + "="*60)
    print("DEMONSTRATION COMPLETE")
    print("="*60)


def integrate_with_constraint_application():
    """
    Пример интеграции с применением ограничений.
    Этот код показывает, как система должна использоваться в реальных модулях.
    """
    example_code = '''
    # В chain_constraints.py при добавлении ограничения окна:
    
    constraint_expr = optimizer.start_vars[class_idx] >= window_start_slot
    optimizer.add_constraint(constraint_expr, ConstraintType.TIME_WINDOW, ...)
    
    # НОВОЕ: Сохраняем эффективные границы
    set_effective_bounds(optimizer, class_idx, window_start_slot, window_end_slot,
                        "time_window", f"Window: {start_time}-{end_time}")
    
    
    # В resource_constraints.py при проверке конфликтов:
    
    # СТАРОЕ: times_overlap(c1, c2) 
    # НОВОЕ: times_overlap(optimizer, c1, c2, idx1, idx2)  - использует эффективные границы
    
    
    # В sequential_scheduling.py при анализе:
    
    # СТАРОЕ: can_schedule_sequentially(c1, c2, idx1, idx2, verbose)
    # НОВОЕ: can_schedule_sequentially(c1, c2, idx1, idx2, verbose, optimizer)  - использует эффективные границы
    '''
    
    print("\nINTEGRATION EXAMPLE:")
    print(example_code)


if __name__ == "__main__":
    print("This is a utility module for effective bounds system.")
    print("Import and use the functions in your scheduler code.")
    integrate_with_constraint_application()
