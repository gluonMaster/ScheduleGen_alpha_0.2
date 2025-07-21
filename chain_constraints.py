"""
Модуль для добавления ограничений CP-SAT на основе планов размещения.

Этот модуль преобразует планы размещения в конкретные ограничения 
для решателя CP-SAT с дедупликацией и оптимизацией.
"""

from time_utils import time_to_minutes, minutes_to_time
from timewindow_utils import find_slot_for_time
from linked_chain_utils import get_linked_chain_order
from effective_bounds_utils import (
    set_effective_bounds, get_effective_bounds, update_bounds_from_constraint,
    time_to_slot, slot_to_time
)


class ConstraintManager:
    """Класс для управления добавлением ограничений с дедупликацией."""
    
    def __init__(self, optimizer):
        """
        Инициализирует менеджер ограничений.
        
        Args:
            optimizer: Экземпляр ScheduleOptimizer
        """
        self.optimizer = optimizer
        self.applied_constraints = getattr(optimizer, "applied_constraints", {})
        self.constraint_counter = 0
        
        # Инициализируем словарь примененных ограничений в оптимизаторе
        if not hasattr(optimizer, "applied_constraints"):
            optimizer.applied_constraints = {}
        
        # Отслеживание типов ограничений
        self.constraints_by_type = {
            'sequential': {},
            'fixed_slot': {},
            'window_bounds': {},
            'separation': {},
            'anchor': {}
        }
    
    def add_constraint(self, constraint_type, constraint, pair_key=None, description=None):
        """
        Добавляет ограничение с проверкой дедупликации.
        
        Args:
            constraint_type: Тип ограничения
            constraint: Объект ограничения CP-SAT
            pair_key: Ключ пары классов для дедупликации (опционально)
            description: Описание ограничения для отладки
        """
        if pair_key and pair_key in self.applied_constraints:
            print(f"  Skipping duplicate constraint {constraint_type} for {pair_key}")
            return False
        
        # Добавляем ограничение
        constraint_id = f"{constraint_type}_{self.constraint_counter}"
        self.constraint_counter += 1
        
        if pair_key:
            self.applied_constraints[pair_key] = constraint
            self.optimizer.applied_constraints[pair_key] = constraint
        
        # Сохраняем в группе по типу
        if constraint_type not in self.constraints_by_type:
            self.constraints_by_type[constraint_type] = {}
        
        self.constraints_by_type[constraint_type][constraint_id] = {
            'constraint': constraint,
            'pair_key': pair_key,
            'description': description
        }
        
        if description:
            print(f"  Added {constraint_type} constraint: {description}")
        
        return True
    
    def get_stats(self):
        """Возвращает статистику добавленных ограничений."""
        stats = {'total': 0}
        for constraint_type, constraints in self.constraints_by_type.items():
            count = len(constraints)
            stats[constraint_type] = count
            stats['total'] += count
        return stats


def add_chain_sequence_constraints(optimizer, placement_plan):
    """
    Добавляет строгие ограничения порядка для связанных цепочек.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        placement_plan: Объект PlacementPlan с планом размещения цепочки
    """
    print("Adding chain sequence constraints...")
    
    # Инициализируем linked_chains если еще не сделано
    if not hasattr(optimizer, 'linked_chains'):
        print("  Initializing linked chains...")
        from linked_chain_utils import build_linked_chains
        build_linked_chains(optimizer)
    
    if not placement_plan.is_valid:
        print("  Chain plan is not valid, skipping")
        return
    
    manager = ConstraintManager(optimizer)
    placements = placement_plan.placements
    
    # Ищем chain_order в атрибутах или создаем из порядка размещений
    if hasattr(placement_plan, 'chain_order'):
        chain_order = placement_plan.chain_order
    else:
        chain_order = [p['class_idx'] for p in placements]
    
    print(f"  Processing chain with {len(placements)} classes")
    
    # Добавляем ограничения последовательности между соседними элементами цепочки
    for i in range(len(placements) - 1):
        current_placement = placements[i]
        next_placement = placements[i + 1]
        
        current_idx = current_placement['class_idx']
        next_idx = next_placement['class_idx']
        
        current_class = optimizer.classes[current_idx]
        next_class = optimizer.classes[next_idx]
        
        # Рассчитываем минимальный разрыв между занятиями
        duration_slots = current_class.duration // optimizer.time_interval
        pause_after_slots = current_class.pause_after // optimizer.time_interval
        pause_before_slots = next_class.pause_before // optimizer.time_interval
        min_gap = duration_slots + pause_after_slots + pause_before_slots
        
        # Используем централизованное логирование
        from constraint_registry import ConstraintType
        constraint_expr = optimizer.model.Add(optimizer.start_vars[next_idx] >= optimizer.start_vars[current_idx] + min_gap)
        
        optimizer.add_constraint(
            constraint_expr=constraint_expr,
            constraint_type=ConstraintType.CHAIN_ORDERING,
            origin_module=__name__,
            origin_function="add_chain_sequence_constraints",
            class_i=current_idx,
            class_j=next_idx,
            description=f"Chain: class {current_idx} -> class {next_idx} (gap: {min_gap} slots)",
            variables_used=[f"start_var[{current_idx}]", f"start_var[{next_idx}]"]
        )
        
        # Обновляем эффективные границы для следующего класса
        update_bounds_from_constraint(
            optimizer, next_idx, "chain_ordering",
            min_slot=min_gap,  # Минимальное смещение относительно предыдущего
            description=f"Chain constraint: must start at least {min_gap} slots after class {current_idx}"
        )
        
        pair_key = (current_idx, next_idx)
        description = f"Chain: class {current_idx} -> class {next_idx} (gap: {min_gap} slots)"
        
        manager.add_constraint('sequential', constraint_expr, pair_key, description)
    
    # ОТМЕТКА: Записываем, что для этих классов применены ограничения цепочки
    if not hasattr(optimizer, 'chain_constraints_applied'):
        optimizer.chain_constraints_applied = set()
    
    for placement in placements:
        class_idx = placement['class_idx']
        optimizer.chain_constraints_applied.add(class_idx)
        print(f"  Marked class {class_idx} as having chain constraints applied")
    
    # Добавляем ограничения на временные окна для цепочки с учетом последовательности
    chain_start_time = None
    chain_end_time = None
    
    # Определяем общие границы цепочки (объединение всех временных окон)
    for placement in placements:
        class_idx = placement['class_idx']
        c = optimizer.classes[class_idx]
        if c.start_time and c.end_time:
            if chain_start_time is None or time_to_minutes(c.start_time) < time_to_minutes(chain_start_time):
                chain_start_time = c.start_time
            if chain_end_time is None or time_to_minutes(c.end_time) > time_to_minutes(chain_end_time):
                chain_end_time = c.end_time
    
    if chain_start_time and chain_end_time:
        # Находим слоты для границ цепочки
        chain_start_slot = None
        chain_end_slot = None
        
        for slot_idx, slot_time in enumerate(optimizer.time_slots):
            if chain_start_slot is None and time_to_minutes(slot_time) >= time_to_minutes(chain_start_time):
                chain_start_slot = slot_idx
            if chain_end_slot is None and time_to_minutes(slot_time) >= time_to_minutes(chain_end_time):
                chain_end_slot = slot_idx
                break
        
        if chain_start_slot is not None and chain_end_slot is not None:
            # Рассчитываем правильные границы для каждого класса в цепочке
            current_min_slot = chain_start_slot
            
            for i, placement in enumerate(placements):
                class_idx = placement['class_idx']
                c = optimizer.classes[class_idx]
                
                # Проверяем, что переменная не зафиксирована
                if isinstance(optimizer.start_vars[class_idx], int):
                    continue
                
                duration_slots = c.duration // optimizer.time_interval
                
                if i == 0:
                    # Первый класс: может начинаться в любое время от начала цепочки
                    min_start_slot = chain_start_slot
                else:
                    # Последующие классы: не раньше чем после предыдущего + паузы
                    min_start_slot = current_min_slot
                
                # Максимальное время начала - чтобы уложиться в окно цепочки
                max_start_slot = chain_end_slot - duration_slots
                
                # Добавляем ограничения
                if min_start_slot == max_start_slot:
                    # Строгое равенство - занятие должно начаться в конкретное время
                    print(f"DEBUG: Setting FIXED start time for class {class_idx} at slot {min_start_slot}")
                    constraint_expr = optimizer.model.Add(optimizer.start_vars[class_idx] == min_start_slot)
                    
                    # Используем централизованное логирование
                    from constraint_registry import ConstraintType
                    optimizer.add_constraint(
                        constraint_expr=constraint_expr,
                        constraint_type=ConstraintType.FIXED_TIME,
                        origin_module=__name__,
                        origin_function="add_chain_sequence_constraints",
                        class_i=class_idx,
                        description=f"Fixed start time: class {class_idx} == slot {min_start_slot}",
                        variables_used=[f"start_var[{class_idx}]"]
                    )
                    
                    manager.add_constraint('window_bounds', constraint_expr, None,
                                         f"Fixed start time: class {class_idx} == slot {min_start_slot}")
                else:
                    # Обычные ограничения диапазона
                    constraint1_expr = optimizer.model.Add(optimizer.start_vars[class_idx] >= min_start_slot)
                    constraint2_expr = optimizer.model.Add(optimizer.start_vars[class_idx] <= max_start_slot)
                    
                    # Используем централизованное логирование
                    from constraint_registry import ConstraintType
                    optimizer.add_constraint(
                        constraint_expr=constraint1_expr,
                        constraint_type=ConstraintType.TIME_WINDOW,
                        origin_module=__name__,
                        origin_function="add_chain_sequence_constraints",
                        class_i=class_idx,
                        description=f"Time window lower bound: class {class_idx} >= slot {min_start_slot}",
                        variables_used=[f"start_var[{class_idx}]"]
                    )
                    
                    optimizer.add_constraint(
                        constraint_expr=constraint2_expr,
                        constraint_type=ConstraintType.TIME_WINDOW,
                        origin_module=__name__,
                        origin_function="add_chain_sequence_constraints",
                        class_i=class_idx,
                        description=f"Time window upper bound: class {class_idx} <= slot {max_start_slot}",
                        variables_used=[f"start_var[{class_idx}]"]
                    )
                    
                    manager.add_constraint('window_bounds', constraint1_expr, None,
                                         f"Window lower bound: class {class_idx} >= slot {min_start_slot}")
                    manager.add_constraint('window_bounds', constraint2_expr, None,
                                         f"Window upper bound: class {class_idx} <= slot {max_start_slot}")
                    
                    manager.add_constraint('window_bounds', constraint1_expr, None,
                                         f"Window lower bound: class {class_idx} >= slot {min_start_slot}")
                    manager.add_constraint('window_bounds', constraint2_expr, None,
                                         f"Window upper bound: class {class_idx} <= slot {max_start_slot}")
                
                # Обновляем минимальный слот для следующего класса
                if i < len(placements) - 1:
                    pause_after_slots = c.pause_after // optimizer.time_interval
                    next_class = optimizer.classes[placements[i + 1]['class_idx']]
                    pause_before_slots = next_class.pause_before // optimizer.time_interval
                    current_min_slot = min_start_slot + duration_slots + pause_after_slots + pause_before_slots
    
    stats = manager.get_stats()
    print(f"  Added {stats['sequential']} sequential constraints, {stats['window_bounds']} window constraints")


def add_anchor_constraints(optimizer, placement_plan):
    """
    Добавляет жесткую фиксацию занятий в конкретные временные слоты.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        placement_plan: Объект PlacementPlan с планом размещения относительно якорей
    """
    print("Adding anchor constraints...")
    
    # Инициализируем linked_chains если еще не сделано
    if not hasattr(optimizer, 'linked_chains'):
        print("  Initializing linked chains...")
        from linked_chain_utils import build_linked_chains
        build_linked_chains(optimizer)
    
    if not placement_plan.is_valid:
        print("  Anchor plan is not valid, skipping")
        return
    
    manager = ConstraintManager(optimizer)
    placements = placement_plan.placements
    
    print(f"  Processing {len(placements)} anchor-based placements")
    
    for placement in placements:
        class_idx = placement['class_idx']
        placement_info = placement.get('info', {})
        placement_type = placement_info.get('placement_type', 'unknown')
        
        if placement_type == 'relative_to_anchor':
            # Размещение относительно якоря - добавляем ограничения диапазона
            start_slot = placement_info.get('start_slot')
            end_slot = placement_info.get('end_slot')
            
            if start_slot is not None and end_slot is not None:
                duration_slots = optimizer.classes[class_idx].duration // optimizer.time_interval
                max_start_slot = end_slot - duration_slots
                
                constraint1 = optimizer.model.Add(optimizer.start_vars[class_idx] >= start_slot)
                constraint2 = optimizer.model.Add(optimizer.start_vars[class_idx] <= max_start_slot)
                
                manager.add_constraint('anchor', constraint1, None, 
                                     f"Anchor lower bound: class {class_idx} >= slot {start_slot}")
                manager.add_constraint('anchor', constraint2, None,
                                     f"Anchor upper bound: class {class_idx} <= slot {max_start_slot}")
        
        elif placement_type == 'free_slot':
            # Размещение в свободном слоте
            start_slot = placement_info.get('start_slot')
            end_slot = placement_info.get('end_slot')
            
            if start_slot is not None and end_slot is not None:
                duration_slots = optimizer.classes[class_idx].duration // optimizer.time_interval
                max_start_slot = end_slot - duration_slots
                
                constraint1 = optimizer.model.Add(optimizer.start_vars[class_idx] >= start_slot)
                constraint2 = optimizer.model.Add(optimizer.start_vars[class_idx] <= max_start_slot)
                
                manager.add_constraint('anchor', constraint1, None,
                                     f"Free slot lower bound: class {class_idx} >= slot {start_slot}")
                manager.add_constraint('anchor', constraint2, None,
                                     f"Free slot upper bound: class {class_idx} <= slot {max_start_slot}")
    
    stats = manager.get_stats()
    print(f"  Added {stats['anchor']} anchor constraints")


def add_flexible_constraints(optimizer, placement_plan):
    """
    Добавляет двунаправленные ограничения разделения для несвязанных занятий.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        placement_plan: Объект PlacementPlan с планом гибкого размещения
    """
    print("Adding flexible separation constraints...")
    
    # Инициализируем linked_chains если еще не сделано
    if not hasattr(optimizer, 'linked_chains'):
        print("  Initializing linked chains...")
        from linked_chain_utils import build_linked_chains
        build_linked_chains(optimizer)
    
    manager = ConstraintManager(optimizer)
    
    # Извлекаем список классов из плана размещения
    if hasattr(placement_plan, 'class_group') and hasattr(placement_plan.class_group, 'classes'):
        classes_list = placement_plan.class_group.classes
    else:
        classes_list = []
    
    print(f"  Processing {len(classes_list)} classes for flexible constraints")
    
    # Добавляем ограничения между всеми парами классов
    for i in range(len(classes_list)):
        idx_i, c_i = classes_list[i]
        for j in range(i + 1, len(classes_list)):
            idx_j, c_j = classes_list[j]
            
            pair_key = (min(idx_i, idx_j), max(idx_i, idx_j))
            
            # Проверяем, не добавлены ли уже ограничения для этой пары
            if pair_key in manager.applied_constraints:
                continue
            
            # Проверяем, являются ли классы частью связанной цепочки
            in_same_chain, chain_order = get_linked_chain_order(optimizer, idx_i, idx_j)
            
            if in_same_chain and chain_order != 0:
                # Для связанных классов добавляем одностороннее ограничение
                add_one_way_constraint(optimizer, idx_i, idx_j, c_i, c_j, chain_order, manager)
            else:
                # Для несвязанных классов добавляем двустороннее ограничение
                add_bidirectional_constraint(optimizer, idx_i, idx_j, c_i, c_j, manager)
    
    stats = manager.get_stats()
    print(f"  Added {stats['separation']} separation constraints")


def add_one_way_constraint(optimizer, idx_i, idx_j, c_i, c_j, order, manager):
    """Добавляет одностороннее ограничение между связанными классами."""
    from constraint_registry import ConstraintType
    
    if order > 0:
        # i должен быть перед j
        first_idx, first_class = idx_i, c_i
        second_idx, second_class = idx_j, c_j
    else:
        # j должен быть перед i
        first_idx, first_class = idx_j, c_j
        second_idx, second_class = idx_i, c_i
    
    duration_slots = first_class.duration // optimizer.time_interval
    min_pause = max(1, (first_class.pause_after + second_class.pause_before) // optimizer.time_interval)
    
    constraint_expr = optimizer.start_vars[first_idx] + duration_slots + min_pause <= optimizer.start_vars[second_idx]
    description = f"One-way chain: class {first_idx} → class {second_idx} (gap: {duration_slots + min_pause} slots)"
    
    constraint = optimizer.add_constraint(
        constraint_expr=constraint_expr,
        constraint_type=ConstraintType.CHAIN_ORDERING,
        origin_module=__name__,
        origin_function="add_one_way_constraint",
        class_i=first_idx,
        class_j=second_idx,
        description=description,
        variables_used=[f"start_vars[{first_idx}]", f"start_vars[{second_idx}]"]
    )
    
    pair_key = (first_idx, second_idx)
    manager.add_constraint('chain_ordering', constraint, pair_key, description)


def add_bidirectional_constraint(optimizer, idx_i, idx_j, c_i, c_j, manager):
    """Добавляет двустороннее ограничение между несвязанными классами."""
    from constraint_registry import ConstraintType
    
    # Создаем булеву переменную для определения порядка занятий
    i_before_j = optimizer.model.NewBoolVar(f"i_before_j_{idx_i}_{idx_j}")
    
    # Расчет длительности в слотах времени
    duration_i_slots = c_i.duration // optimizer.time_interval
    duration_j_slots = c_j.duration // optimizer.time_interval
    
    # Минимальный интервал между занятиями
    min_pause_i_j = max(1, (c_i.pause_after + c_j.pause_before) // optimizer.time_interval)
    min_pause_j_i = max(1, (c_j.pause_after + c_i.pause_before) // optimizer.time_interval)
    
    # Если i перед j
    constraint1_expr = optimizer.start_vars[idx_i] + duration_i_slots + min_pause_i_j <= optimizer.start_vars[idx_j]
    constraint1 = optimizer.add_constraint(
        constraint_expr=constraint1_expr,
        constraint_type=ConstraintType.SEPARATION,
        origin_module=__name__,
        origin_function="add_bidirectional_constraint",
        class_i=idx_i,
        class_j=idx_j,
        description=f"Bidirectional separation (i→j): class {idx_i} → class {idx_j}",
        variables_used=[f"start_vars[{idx_i}]", f"start_vars[{idx_j}]", f"i_before_j_{idx_i}_{idx_j}"]
    ).OnlyEnforceIf(i_before_j)
    
    # Если j перед i
    constraint2_expr = optimizer.start_vars[idx_j] + duration_j_slots + min_pause_j_i <= optimizer.start_vars[idx_i]
    constraint2 = optimizer.add_constraint(
        constraint_expr=constraint2_expr,
        constraint_type=ConstraintType.SEPARATION,
        origin_module=__name__,
        origin_function="add_bidirectional_constraint",
        class_i=idx_j,
        class_j=idx_i,
        description=f"Bidirectional separation (j→i): class {idx_j} → class {idx_i}",
        variables_used=[f"start_vars[{idx_i}]", f"start_vars[{idx_j}]", f"i_before_j_{idx_i}_{idx_j}"]
    ).OnlyEnforceIf(i_before_j.Not())
    
    pair_key = (min(idx_i, idx_j), max(idx_i, idx_j))
    description = f"Bidirectional separation: classes {idx_i} and {idx_j}"
    
    # Сохраняем оба ограничения как список для обратной совместимости
    manager.applied_constraints[pair_key] = [constraint1, constraint2]
    manager.optimizer.applied_constraints[pair_key] = [constraint1, constraint2]
    
    print(f"  Added bidirectional constraint: classes {idx_i} and {idx_j}")


def add_window_bounds_constraints(optimizer, class_idx, manager=None):
    """
    Добавляет ограничения временного окна для класса.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        class_idx: Индекс класса
        manager: Менеджер ограничений (опционально)
    """
    from constraint_registry import ConstraintType
    
    if manager is None:
        manager = ConstraintManager(optimizer)
    
    c = optimizer.classes[class_idx]
    
    # Проверяем, что это класс с временным окном
    if not (c.start_time and c.end_time):
        print(f"  Class {class_idx} has no time window, skipping")
        return
    
    # Проверяем, что переменная не зафиксирована
    if isinstance(optimizer.start_vars[class_idx], int):
        print(f"  Class {class_idx} start time is fixed, updating effective bounds only")
        # Обновляем эффективные границы для фиксированного времени
        fixed_slot = optimizer.start_vars[class_idx]
        set_effective_bounds(optimizer, class_idx, fixed_slot, fixed_slot, 
                           "fixed_assignment", f"Fixed to slot {fixed_slot}")
        return
    
    window_start_time = c.start_time
    window_end_time = c.end_time
    
    # Находим соответствующие временные слоты
    window_start_slot = time_to_slot(optimizer, window_start_time)
    window_end_slot = time_to_slot(optimizer, window_end_time)
    
    if window_start_slot is not None and window_end_slot is not None:
        # Рассчитываем максимальное время начала, чтобы уложиться в окно
        duration_slots = c.duration // optimizer.time_interval
        max_start_slot = window_end_slot - duration_slots
        
        # Добавляем ограничения на временное окно
        constraint1_expr = optimizer.start_vars[class_idx] >= window_start_slot
        constraint1 = optimizer.add_constraint(
            constraint_expr=constraint1_expr,
            constraint_type=ConstraintType.TIME_WINDOW,
            origin_module=__name__,
            origin_function="add_window_bounds_constraints",
            class_i=class_idx,
            description=f"Window lower bound: class {class_idx} >= slot {window_start_slot} ({window_start_time})",
            variables_used=[f"start_vars[{class_idx}]"]
        )
        
        constraint2_expr = optimizer.start_vars[class_idx] <= max_start_slot
        constraint2 = optimizer.add_constraint(
            constraint_expr=constraint2_expr,
            constraint_type=ConstraintType.TIME_WINDOW,
            origin_module=__name__,
            origin_function="add_window_bounds_constraints",
            class_i=class_idx,
            description=f"Window upper bound: class {class_idx} <= slot {max_start_slot} ({window_end_time})",
            variables_used=[f"start_vars[{class_idx}]"]
        )
        
        # Устанавливаем эффективные границы
        set_effective_bounds(optimizer, class_idx, window_start_slot, max_start_slot,
                           "time_window", f"Window constraints: {window_start_time}-{window_end_time}")
        
        manager.add_constraint('window_bounds', constraint1, None,
                             f"Window lower bound: class {class_idx} >= slot {window_start_slot}")
        manager.add_constraint('window_bounds', constraint2, None,
                             f"Window upper bound: class {class_idx} <= slot {max_start_slot}")
        
        print(f"  Added window constraints for class {class_idx}: start between slots {window_start_slot} and {max_start_slot}")
        print(f"  Effective bounds: {slot_to_time(optimizer, window_start_slot)} - {slot_to_time(optimizer, max_start_slot)}")
    else:
        print(f"  Could not determine time slots for class {class_idx} window {window_start_time}-{window_end_time}")


def apply_placement_constraints(optimizer, placement_plan):
    """
    Применяет ограничения на основе плана размещения.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        placement_plan: Объект PlacementPlan или словарь с планом
    """
    print("Applying placement constraints...")
    
    if hasattr(placement_plan, 'plan_type'):
        # Объект PlacementPlan
        plan_type = placement_plan.plan_type
        success = placement_plan.is_valid
    else:
        # Словарь
        plan_type = placement_plan.get('placement_type', 'unknown')
        success = placement_plan.get('success', False)
    
    if not success:
        print(f"  Plan type '{plan_type}' is not valid, skipping")
        return
    
    print(f"  Applying constraints for plan type: {plan_type}")
    
    if plan_type == 'sequential':
        add_chain_sequence_constraints(optimizer, placement_plan)
    elif plan_type == 'linked_chain':
        add_chain_sequence_constraints(optimizer, placement_plan)
    elif plan_type == 'anchored':
        add_anchor_constraints(optimizer, placement_plan)
    elif plan_type == 'flexible':
        add_flexible_constraints(optimizer, placement_plan)
    else:
        print(f"  Unknown plan type: {plan_type}")


def get_constraints_summary(optimizer):
    """
    Возвращает сводку по добавленным ограничениям.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        
    Returns:
        dict: Статистика ограничений
    """
    applied_constraints = getattr(optimizer, "applied_constraints", {})
    
    summary = {
        'total_constraint_pairs': len(applied_constraints),
        'constraint_types': {},
        'constraint_details': []
    }
    
    # Анализируем типы ограничений (приблизительно)
    for pair_key, constraint in applied_constraints.items():
        if isinstance(constraint, list):
            summary['constraint_types']['bidirectional'] = summary['constraint_types'].get('bidirectional', 0) + 1
        else:
            summary['constraint_types']['unidirectional'] = summary['constraint_types'].get('unidirectional', 0) + 1
        
        summary['constraint_details'].append({
            'pair': pair_key,
            'type': 'list' if isinstance(constraint, list) else 'single'
        })
    
    return summary
