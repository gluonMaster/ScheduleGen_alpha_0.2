"""
Модуль для добавления ограничений разделения времени между занятиями.

Этот модуль содержит функции для анализа связанных занятий и добавления
соответствующих ограничений для предотвращения конфликтов по времени.
РЕФАКТОРИРОВАННАЯ ВЕРСИЯ: Основная логика вынесена в специализированные модули.
"""

from time_utils import time_to_minutes, minutes_to_time
from timewindow_utils import find_slot_for_time, build_transitive_links
from linked_chain_utils import get_linked_chain_order, is_in_linked_chain
from sequential_scheduling import can_schedule_sequentially
from constraint_registry import ConstraintType
from effective_bounds_utils import get_effective_bounds, classify_bounds

# НОВЫЕ ИМПОРТЫ: Специализированные модули после рефакторинга
from timeline_manager import create_timeline
from group_analyzer import group_classes_by_criteria, find_independent_groups, analyze_group_constraints
from window_scheduler import create_placement_plan
from chain_constraints import apply_placement_constraints

__all__ = ['add_time_separation_constraints', 'analyze_related_classes']


def add_time_separation_constraints(optimizer, idx_i, idx_j, c_i, c_j):
    """
    Добавляет ограничения для гарантированного разделения занятий по времени
    с добавлением минимального интервала между занятиями
    """
    # Проверяем, не был ли уже проведен детальный анализ этой пары
    if not hasattr(optimizer, '_detailed_analysis_done'):
        optimizer._detailed_analysis_done = set()
    
    pair_key = (min(idx_i, idx_j), max(idx_i, idx_j))
    verbose = pair_key not in optimizer._detailed_analysis_done
    
    if verbose:
        optimizer._detailed_analysis_done.add(pair_key)
        print(f"\n=== ADD TIME SEPARATION CONSTRAINTS ===")
        print(f"Class {idx_i}: {getattr(c_i, 'subject', 'Unknown')} - {getattr(c_i, 'group', 'Unknown')} (Teacher: {getattr(c_i, 'teacher', 'Unknown')})")
        print(f"Class {idx_j}: {getattr(c_j, 'subject', 'Unknown')} - {getattr(c_j, 'group', 'Unknown')} (Teacher: {getattr(c_j, 'teacher', 'Unknown')})")
        
        # Анализ конфликтов ресурсов
        same_teacher = c_i.teacher == c_j.teacher
        shared_groups = set(c_i.get_groups()) & set(c_j.get_groups())
        shared_rooms = set(c_i.possible_rooms) & set(c_j.possible_rooms)
        
        print(f"RESOURCE CONFLICT ANALYSIS:")
        print(f"  Same teacher: {'YES' if same_teacher else 'NO'} ({c_i.teacher} vs {c_j.teacher})")
        print(f"  Shared groups: {'YES' if shared_groups else 'NO'} ({shared_groups if shared_groups else 'none'})")
        print(f"  Shared rooms: {'YES' if shared_rooms else 'NO'} ({shared_rooms if shared_rooms else 'none'})")
    else:
        print(f"[BRIEF] Classes {idx_i}+{idx_j}: {c_i.subject}+{c_j.subject}")
    
    # NEW: Handle chain_and_resource_gap case first
    can_schedule, info = can_schedule_sequentially(c_i, c_j, idx_i, idx_j, verbose=verbose)
    if can_schedule and info.get("reason") == "chain_and_resource_gap":
        # Extract the intervals from the info
        c1_interval = info.get("c1_interval")
        c2_interval = info.get("c2_interval")
        gap = info.get("gap", 0)
        
        if c1_interval and c2_interval:
            # Determine which class should come first based on the intervals
            c1_start, c1_end = c1_interval
            c2_start, c2_end = c2_interval
            
            # Convert minutes back to slots
            c1_start_slot = c1_start // optimizer.time_interval
            c1_end_slot = c1_end // optimizer.time_interval
            c2_start_slot = c2_start // optimizer.time_interval
            
            print(f"CHAIN_AND_RESOURCE_GAP CONSTRAINT:")
            print(f"  c1_interval: {c1_start}-{c1_end} min ({minutes_to_time(c1_start)}-{minutes_to_time(c1_end)})")
            print(f"  c2_interval: {c2_start}-{c2_end} min ({minutes_to_time(c2_start)}-{minutes_to_time(c2_end)})")
            print(f"  Gap: {gap} min")
            
            if c1_end <= c2_start:
                # c_i должен быть перед c_j
                print(f"  CONSTRAINT TYPE: Sequential (class {idx_i} → class {idx_j})")
                print(f"  CP-SAT CONSTRAINT: start_var[{idx_i}] + {c_i.duration // optimizer.time_interval} ≤ start_var[{idx_j}]")
                
                # Добавляем ограничение: end(c_i) ≤ start(c_j)
                constraint_expr = optimizer.model.Add(optimizer.start_vars[idx_i] + (c_i.duration // optimizer.time_interval) <= optimizer.start_vars[idx_j])
                constraint = optimizer.add_constraint(
                    constraint_expr=constraint_expr,
                    constraint_type=ConstraintType.SEQUENTIAL,
                    origin_module=__name__,
                    origin_function="add_time_separation_constraints",
                    class_i=idx_i,
                    class_j=idx_j,
                    description=f"Sequential: class {idx_i} → class {idx_j}",
                    variables_used=[f"start_var[{idx_i}]", f"start_var[{idx_j}]"]
                )
                print(f"  ✓ Added constraint: end({idx_i}) ≤ start({idx_j})")
            else:
                # c_j должен быть перед c_i
                print(f"  CONSTRAINT TYPE: Sequential (class {idx_j} → class {idx_i})")
                print(f"  CP-SAT CONSTRAINT: start_var[{idx_j}] + {c_j.duration // optimizer.time_interval} ≤ start_var[{idx_i}]")
                
                # Добавляем ограничение: end(c_j) ≤ start(c_i)
                constraint_expr = optimizer.model.Add(optimizer.start_vars[idx_j] + (c_j.duration // optimizer.time_interval) <= optimizer.start_vars[idx_i])
                constraint = optimizer.add_constraint(
                    constraint_expr=constraint_expr,
                    constraint_type=ConstraintType.SEQUENTIAL,
                    origin_module=__name__,
                    origin_function="add_time_separation_constraints",
                    class_i=idx_j,
                    class_j=idx_i,
                    description=f"Sequential: class {idx_j} → class {idx_i}",
                    variables_used=[f"start_var[{idx_j}]", f"start_var[{idx_i}]"]
                )
                print(f"  ✓ Added constraint: end({idx_j}) ≤ start({idx_i})")
            
            # Сохраняем примененные ограничения
            if not hasattr(optimizer, "applied_constraints"):
                optimizer.applied_constraints = {}
            pair_key = (idx_i, idx_j)
            optimizer.applied_constraints[pair_key] = constraint_expr
            print(f"  ✓ Constraint saved for pair ({idx_i}, {idx_j})")
            return  # Important: skip other branches for this pair
        else:
            print(f"WARNING: chain_and_resource_gap detected but intervals not available, fallback to default logic")
            # Fallback to simpler constraint
            duration_j_slots = c_j.duration // optimizer.time_interval
            pause_j = getattr(c_j, "pause_after", 0)
            pause_j_slots = pause_j // optimizer.time_interval
            
            # Calculate end of class j and add constraint
            end_j_slots = optimizer.start_vars[idx_j] + duration_j_slots
            constraint_expr = optimizer.model.Add(end_j_slots + pause_j_slots <= optimizer.start_vars[idx_i])
            optimizer.add_constraint(
                constraint_expr=constraint_expr,
                constraint_type=ConstraintType.SEQUENTIAL,
                origin_module=__name__,
                origin_function="add_time_separation_constraints",
                class_i=idx_j,
                class_j=idx_i,
                description=f"Fallback chain/resource-gap: end({idx_j})+{pause_j_slots}slots ≤ start({idx_i})",
                variables_used=[f"start_var[{idx_j}]", f"start_var[{idx_i}]"]
            )
            print(f"Added fallback chain/resource-gap constraint: "
                  f"end({idx_j})+{pause_j_slots}slots ≤ start({idx_i})")
            return  # Important: skip other branches for this pair

    # Проверка на существующие ограничения между этими классами
    pair_key = (idx_i, idx_j)
    reversed_key = (idx_j, idx_i)
    
    if hasattr(optimizer, "applied_constraints") and (pair_key in optimizer.applied_constraints or 
                                                     reversed_key in optimizer.applied_constraints):
        print(f"  Skipping separation constraints for {idx_i} and {idx_j} - already constrained")
        return

    # НОВОЕ: Проверка исключений для предотвращения циклов
    if hasattr(optimizer, "constraint_exceptions") and (pair_key in optimizer.constraint_exceptions or 
                                                       reversed_key in optimizer.constraint_exceptions):
        print(f"  Skipping separation constraints for {idx_i} and {idx_j} - cycle prevention exception")
        return

    # ДИАГНОСТИКА: Проверяем текущие временные окна классов
    _log_class_time_window_info(optimizer, idx_i, c_i, "Class i")
    _log_class_time_window_info(optimizer, idx_j, c_j, "Class j")
    
    # Проверяем, являются ли классы частью одной связанной цепочки
    c_i_chain_classes = []
    c_j_chain_classes = []
    
    print(f"CHAIN ANALYSIS:")
    
    # Check if c_i has linked classes (is a root)
    if hasattr(c_i, 'linked_classes') and c_i.linked_classes:
        c_i_chain_classes = get_linked_chain_order(c_i)
        chain_subjects = [getattr(cls, 'subject', 'Unknown') for cls in c_i_chain_classes]
        print(f"  Class {idx_i} is root of chain: {' → '.join(chain_subjects)}")
    else:
        print(f"  Class {idx_i} is not a chain root")
    
    # Check if c_j has linked classes (is a root)  
    if hasattr(c_j, 'linked_classes') and c_j.linked_classes:
        c_j_chain_classes = get_linked_chain_order(c_j)
        chain_subjects = [getattr(cls, 'subject', 'Unknown') for cls in c_j_chain_classes]
        print(f"  Class {idx_j} is root of chain: {' → '.join(chain_subjects)}")
    else:
        print(f"  Class {idx_j} is not a chain root")
    
    # Determine if they're in the same chain and their order
    in_same_chain = False
    chain_order = 0
    
    if c_i in c_j_chain_classes:
        # c_i is part of c_j's chain
        in_same_chain = True
        i_pos = c_j_chain_classes.index(c_i)
        j_pos = c_j_chain_classes.index(c_j) if c_j in c_j_chain_classes else 0
        chain_order = -1 if i_pos < j_pos else 1
        print(f"  Classes are in SAME CHAIN (c_j's chain): {idx_i} at pos {i_pos}, {idx_j} at pos {j_pos}")
        print(f"    Chain order: {chain_order} ({'i→j' if chain_order > 0 else 'j→i' if chain_order < 0 else 'transitive'})")
    elif c_j in c_i_chain_classes:
        # c_j is part of c_i's chain
        in_same_chain = True
        i_pos = c_i_chain_classes.index(c_i) if c_i in c_i_chain_classes else 0
        j_pos = c_i_chain_classes.index(c_j)
        chain_order = 1 if i_pos < j_pos else -1
        print(f"  Classes are in SAME CHAIN (c_i's chain): {idx_i} at pos {i_pos}, {idx_j} at pos {j_pos}")
        print(f"    Chain order: {chain_order} ({'i→j' if chain_order > 0 else 'j→i' if chain_order < 0 else 'transitive'})")
    else:
        print(f"  Classes are in DIFFERENT CHAINS or independent")
    
    if in_same_chain:
        print(f"SAME CHAIN CONSTRAINT:")
        # Если порядок определен точно (chain_order != 0)
        if chain_order > 0:  # i должен быть перед j
            duration_i_slots = c_i.duration // optimizer.time_interval
            min_pause = max(1, (getattr(c_i, 'pause_after', 0) + getattr(c_j, 'pause_before', 0)) // optimizer.time_interval)
            
            print(f"  CONSTRAINT TYPE: One-way chain (class {idx_i} → class {idx_j})")
            print(f"  Duration slots: {duration_i_slots}, pause slots: {min_pause}")
            print(f"  CP-SAT CONSTRAINT: start_var[{idx_i}] + {duration_i_slots} + {min_pause} ≤ start_var[{idx_j}]")
            
            constraint_expr = optimizer.model.Add(optimizer.start_vars[idx_i] + duration_i_slots + min_pause <= optimizer.start_vars[idx_j])
            constraint = optimizer.add_constraint(
                constraint_expr=constraint_expr,
                constraint_type=ConstraintType.CHAIN_ORDERING,
                origin_module=__name__,
                origin_function="add_time_separation_constraints",
                class_i=idx_i,
                class_j=idx_j,
                description=f"One-way chain: class {idx_i} → class {idx_j}",
                variables_used=[f"start_var[{idx_i}]", f"start_var[{idx_j}]"]
            )
            
            # Используем реестр ограничений
            optimizer.add_constraint(
                constraint_expr=constraint,
                constraint_type=ConstraintType.CHAIN_ORDERING,
                origin_module=__name__,
                origin_function="add_time_separation_constraints",
                class_i=idx_i,
                class_j=idx_j,
                description=f"One-way chain: class {idx_i} → class {idx_j}",
                variables_used=[f"start_var[{idx_i}]", f"start_var[{idx_j}]"]
            )
            
            # Сохраняем примененные ограничения (для обратной совместимости)
            if not hasattr(optimizer, "applied_constraints"):
                optimizer.applied_constraints = {}
            optimizer.applied_constraints[pair_key] = constraint_expr
            print(f"  ✓ Constraint saved for pair ({idx_i}, {idx_j})")
            return
        elif chain_order < 0:  # j должен быть перед i
            duration_j_slots = c_j.duration // optimizer.time_interval
            min_pause = max(1, (getattr(c_j, 'pause_after', 0) + getattr(c_i, 'pause_before', 0)) // optimizer.time_interval)
            
            print(f"  CONSTRAINT TYPE: One-way chain (class {idx_j} → class {idx_i})")
            print(f"  Duration slots: {duration_j_slots}, pause slots: {min_pause}")
            print(f"  CP-SAT CONSTRAINT: start_var[{idx_j}] + {duration_j_slots} + {min_pause} ≤ start_var[{idx_i}]")
            
            constraint_expr = optimizer.model.Add(optimizer.start_vars[idx_j] + duration_j_slots + min_pause <= optimizer.start_vars[idx_i])
            constraint = optimizer.add_constraint(
                constraint_expr=constraint_expr,
                constraint_type=ConstraintType.CHAIN_ORDERING,
                origin_module=__name__,
                origin_function="add_time_separation_constraints",
                class_i=idx_j,
                class_j=idx_i,
                description=f"One-way chain: class {idx_j} → class {idx_i}",
                variables_used=[f"start_var[{idx_j}]", f"start_var[{idx_i}]"]
            )
            print(f"  ✓ Added one-way chain constraint: class {idx_j} before class {idx_i}")
            
            # Сохраняем примененные ограничения
            if not hasattr(optimizer, "applied_constraints"):
                optimizer.applied_constraints = {}
            optimizer.applied_constraints[reversed_key] = constraint_expr
            print(f"  ✓ Constraint saved for pair ({idx_j}, {idx_i})")
            return
        else:  # chain_order == 0 - классы связаны транзитивно, но порядок не определен
            # Для транзитивно связанных классов добавляем гибкие ограничения
            print(f"  CONSTRAINT TYPE: Flexible transitivity (classes {idx_i} and {idx_j} are transitively linked)")
            
            # Добавляем одностороннее ограничение для последовательности связанных классов
            # Выбираем порядок на основе индексов (меньший индекс идет первым)
            if idx_i < idx_j:
                duration_i_slots = c_i.duration // optimizer.time_interval
                min_pause = max(1, (getattr(c_i, 'pause_after', 0) + getattr(c_j, 'pause_before', 0)) // optimizer.time_interval)
                
                print(f"  Using index-based order: {idx_i} → {idx_j}")
                print(f"  CP-SAT CONSTRAINT: start_var[{idx_i}] + {duration_i_slots} + {min_pause} ≤ start_var[{idx_j}]")
                
                constraint_expr = optimizer.model.Add(optimizer.start_vars[idx_i] + duration_i_slots + min_pause <= optimizer.start_vars[idx_j])
                constraint = optimizer.add_constraint(
                    constraint_expr=constraint_expr,
                    constraint_type=ConstraintType.CHAIN_ORDERING,
                    origin_module=__name__,
                    origin_function="add_time_separation_constraints",
                    class_i=idx_i,
                    class_j=idx_j,
                    description=f"Flexible transitivity: class {idx_i} → class {idx_j}",
                    variables_used=[f"start_var[{idx_i}]", f"start_var[{idx_j}]"]
                )
                print(f"  ✓ Added flexible transitivity constraint: class {idx_i} before class {idx_j}")
            else:
                duration_j_slots = c_j.duration // optimizer.time_interval
                min_pause = max(1, (getattr(c_j, 'pause_after', 0) + getattr(c_i, 'pause_before', 0)) // optimizer.time_interval)
                
                print(f"  Using index-based order: {idx_j} → {idx_i}")
                print(f"  CP-SAT CONSTRAINT: start_var[{idx_j}] + {duration_j_slots} + {min_pause} ≤ start_var[{idx_i}]")
                
                constraint_expr = optimizer.model.Add(optimizer.start_vars[idx_j] + duration_j_slots + min_pause <= optimizer.start_vars[idx_i])
                constraint = optimizer.add_constraint(
                    constraint_expr=constraint_expr,
                    constraint_type=ConstraintType.CHAIN_ORDERING,
                    origin_module=__name__,
                    origin_function="add_time_separation_constraints",
                    class_i=idx_j,
                    class_j=idx_i,
                    description=f"Flexible transitivity: class {idx_j} → class {idx_i}",
                    variables_used=[f"start_var[{idx_j}]", f"start_var[{idx_i}]"]
                )
                print(f"  ✓ Added flexible transitivity constraint: class {idx_j} before class {idx_i}")
            
            # Сохраняем примененные ограничения
            if not hasattr(optimizer, "applied_constraints"):
                optimizer.applied_constraints = {}
            optimizer.applied_constraints[pair_key] = constraint_expr
            print(f"  ✓ Constraint saved for pair ({idx_i}, {idx_j})")
            return
    
    # СУЩЕСТВУЮЩИЙ КОД: для несвязанных классов или если порядок не определен
    print(f"INDEPENDENT CLASSES CONSTRAINT:")
    print(f"  Classes {idx_i} and {idx_j} not in same chain, adding bidirectional constraints")
    
    # Создаем булеву переменную для определения порядка занятий
    i_before_j = optimizer.model.NewBoolVar(f"strict_i_before_j_{idx_i}_{idx_j}")
    print(f"  Created boolean variable: {i_before_j.Name()}")
    
    # Расчет длительности в слотах времени
    duration_i_slots = c_i.duration // optimizer.time_interval
    duration_j_slots = c_j.duration // optimizer.time_interval
    
    # Минимальный интервал между занятиями (хотя бы 1 слот)
    min_pause_i_j = max(1, (getattr(c_i, 'pause_after', 0) + getattr(c_j, 'pause_before', 0)) // optimizer.time_interval)
    min_pause_j_i = max(1, (getattr(c_j, 'pause_after', 0) + getattr(c_i, 'pause_before', 0)) // optimizer.time_interval)
    
    print(f"  Duration slots: i={duration_i_slots}, j={duration_j_slots}")
    print(f"  Pause slots: i→j={min_pause_i_j}, j→i={min_pause_j_i}")
    
    # Если i перед j
    constraint1_expr = optimizer.model.Add(optimizer.start_vars[idx_i] + duration_i_slots + min_pause_i_j <= optimizer.start_vars[idx_j]).OnlyEnforceIf(i_before_j)
    constraint1 = optimizer.add_constraint(
        constraint_expr=constraint1_expr,
        constraint_type=ConstraintType.SEPARATION,
        origin_module=__name__,
        origin_function="add_time_separation_constraints",
        class_i=idx_i,
        class_j=idx_j,
        description=f"Bidirectional separation (i→j): class {idx_i} → class {idx_j}",
        variables_used=[f"start_var[{idx_i}]", f"start_var[{idx_j}]", f"strict_i_before_j_{idx_i}_{idx_j}"]
    )
    
    # Если j перед i
    constraint2_expr = optimizer.model.Add(optimizer.start_vars[idx_j] + duration_j_slots + min_pause_j_i <= optimizer.start_vars[idx_i]).OnlyEnforceIf(i_before_j.Not())
    constraint2 = optimizer.add_constraint(
        constraint_expr=constraint2_expr,
        constraint_type=ConstraintType.SEPARATION,
        origin_module=__name__,
        origin_function="add_time_separation_constraints",
        class_i=idx_j,
        class_j=idx_i,
        description=f"Bidirectional separation (j→i): class {idx_j} → class {idx_i}",
        variables_used=[f"start_var[{idx_i}]", f"start_var[{idx_j}]", f"strict_i_before_j_{idx_i}_{idx_j}"]
    )
    
    # Сохраняем примененные ограничения (для обратной совместимости)
    if not hasattr(optimizer, "applied_constraints"):
        optimizer.applied_constraints = {}
    
    optimizer.applied_constraints[pair_key] = [constraint1_expr, constraint2_expr]
    print(f"  ✓ Constraints saved for pair ({idx_i}, {idx_j})")
    
    print(f"  CP-SAT CONSTRAINT 1 (if i before j): start_var[{idx_i}] + {duration_i_slots} + {min_pause_i_j} ≤ start_var[{idx_j}]")
    print(f"  CP-SAT CONSTRAINT 2 (if j before i): start_var[{idx_j}] + {duration_j_slots} + {min_pause_j_i} ≤ start_var[{idx_i}]")
    print(f"  ✓ Added strict time separation constraints between classes {idx_i} and {idx_j}")


def analyze_related_classes(optimizer):
    """
    РЕФАКТОРИРОВАННАЯ ВЕРСИЯ: Тонкий слой оркестрации для анализа связанных занятий.
    
    Решает "проблему Анны" путем разделения преподавателей с непересекающимися 
    временными окнами на независимые группы вместо поиска общего временного окна.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        
    Returns:
        set: Множество обработанных пар занятий
    """
    print("\n=== ANALYZE RELATED CLASSES (REFACTORED) ===")
    print("Using specialized modules for timeline, grouping, scheduling and constraints")
    
    processed_pairs = set()
    
    # ШАГ 1: Группировка занятий по критериям (группы студентов, преподаватели, аудитории)
    print("\nStep 1: Grouping classes by criteria...")
    grouped_classes = group_classes_by_criteria(optimizer)
    
    # Статистика группировки
    total_groups = sum(len(days_dict) for criteria_dict in grouped_classes.values() 
                      for days_dict in criteria_dict.values())
    print(f"Created {total_groups} groups across all criteria")
    
    # ШАГ 2: Обработка каждого критерия группировки
    for criteria_type in ['student_groups', 'teachers']:  # ИСПРАВЛЕНИЕ: Убрали 'rooms'
        criteria_dict = grouped_classes[criteria_type]
        if not criteria_dict:
            continue
            
        print(f"\nStep 2.{criteria_type}: Processing {len(criteria_dict)} {criteria_type}")
        
        for group_key, days_dict in criteria_dict.items():
            for day, class_group in days_dict.items():
                print(f"  Processing {criteria_type} '{group_key}' on {day}")
                
                # ШАГ 3: Разделение на независимые группы (РЕШЕНИЕ "ПРОБЛЕМЫ АННЫ")
                independent_groups = find_independent_groups(class_group)
                
                if not independent_groups:
                    print(f"    No independent groups found, using simple separation")
                    # ИСПРАВЛЕНИЕ: Добавляем проверку на минимальное количество классов
                    if len(class_group.classes) >= 2:
                        _add_simple_separation_constraints(optimizer, class_group.classes, processed_pairs)
                    else:
                        print(f"    Only {len(class_group.classes)} class(es), skipping constraints")
                    continue
                
                # ШАГ 4: Обработка каждой независимой группы
                for i, independent_group in enumerate(independent_groups):
                    print(f"    Independent group {i+1}/{len(independent_groups)}: {len(independent_group.classes)} classes")
                    
                    # ШАГ 5: Создание временной шкалы для группы
                    timeline = create_timeline(optimizer, independent_group.day, independent_group.classes)
                    print(f"      Created timeline with {len(timeline.anchors)} anchors, {len(timeline.free_slots)} free slots")
                    
                    # ШАГ 6: Анализ ограничений группы
                    constraints_info = analyze_group_constraints(optimizer, independent_group)
                    
                    # ШАГ 7: Создание плана размещения
                    placement_plan = create_placement_plan(optimizer, independent_group, timeline)
                    print(f"      Created {placement_plan.plan_type} placement plan (valid: {placement_plan.is_valid})")
                    
                    # ШАГ 8: Применение ограничений CP-SAT
                    if placement_plan.is_valid:
                        apply_placement_constraints(optimizer, placement_plan)
                        # Отмечаем обработанные пары
                        for placement in placement_plan.placements:
                            for other_placement in placement_plan.placements:
                                if placement['class_idx'] != other_placement['class_idx']:
                                    pair_key = (min(placement['class_idx'], other_placement['class_idx']),
                                              max(placement['class_idx'], other_placement['class_idx']))
                                    processed_pairs.add(pair_key)
                    else:
                        print(f"      WARNING: Invalid placement plan, using fallback separation")
                        # ИСПРАВЛЕНИЕ: Добавляем проверку на минимальное количество классов
                        if len(independent_group.classes) >= 2:
                            _add_simple_separation_constraints(optimizer, independent_group.classes, processed_pairs)
                        else:
                            print(f"      Only {len(independent_group.classes)} class(es), skipping fallback constraints")
    
    print(f"\n=== ANALYSIS COMPLETE ===")
    print(f"Total processed pairs: {len(processed_pairs)}")
    
    # Сохраняем информацию в оптимизаторе (совместимость с существующим кодом)
    if not hasattr(optimizer, 'prefer_late_start'):
        optimizer.prefer_late_start = set()
    
    return processed_pairs


def _add_simple_separation_constraints(optimizer, classes_list, processed_pairs):
    """
    Добавляет простые ограничения разделения между всеми парами классов.
    Используется как fallback для малых групп или в случае ошибок.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        classes_list: Список кортежей (idx, class_obj)
        processed_pairs: Множество уже обработанных пар для обновления
    """
    if len(classes_list) < 2:
        print(f"    Skipping separation constraints - less than 2 classes ({len(classes_list)})")
        return
        
    print(f"    Adding simple separation constraints for {len(classes_list)} classes")
    
    for i in range(len(classes_list)):
        idx_i, c_i = classes_list[i]
        for j in range(i + 1, len(classes_list)):
            idx_j, c_j = classes_list[j]
            pair_key = (min(idx_i, idx_j), max(idx_i, idx_j))
            
            if pair_key not in processed_pairs:
                # ИСПРАВЛЕНИЕ: Проверяем, действительно ли нужны ограничения
                # Не добавляем ограничения для занятий в разное время, которые не конфликтуют
                if _classes_need_separation_constraint(optimizer, idx_i, c_i, idx_j, c_j):
                    add_time_separation_constraints(optimizer, idx_i, idx_j, c_i, c_j)
                    processed_pairs.add(pair_key)
                else:
                    print(f"      Skipping constraint for classes {idx_i} and {idx_j} - no conflict potential")


def _classes_need_separation_constraint(optimizer, idx_c1, c1, idx_c2, c2):
    """
    Проверяет, нужны ли ограничения разделения между двумя классами,
    используя реальные CP-SAT переменные вместо статических значений.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer с доступом к start_vars
        idx_c1, idx_c2: Индексы классов в списке classes
        c1, c2: Объекты классов
        
    Returns:
        bool: True, если нужны ограничения разделения
    """
    # Классы на разных днях не нуждаются в ограничениях
    if c1.day != c2.day:
        print(f"      Classes on different days ({c1.day} vs {c2.day}) - no constraint needed")
        return False
    
    # Вспомогательная функция для создания переменных времени окончания
    def _get_class_time_variables(optimizer, idx, class_obj):
        """
        Получает переменные времени для класса, используя CP-SAT переменные где возможно.
        
        Returns:
            tuple: (start_var, end_var, start_minutes_for_display, end_minutes_for_display)
        """
        if hasattr(optimizer, 'start_vars') and idx < len(optimizer.start_vars):
            start_var = optimizer.start_vars[idx]
            
            # Создаем переменную конца занятия
            duration_slots = class_obj.duration // optimizer.time_interval
            if isinstance(start_var, int):
                # Переменная уже зафиксирована
                end_var = start_var + duration_slots
                # Для отображения в логах
                start_minutes = start_var * optimizer.time_interval + 8 * 60  # 8:00 - начало дня
                end_minutes = end_var * optimizer.time_interval + 8 * 60
            else:
                # Переменная еще гибкая - создаем переменную конца
                max_slot = len(optimizer.time_slots) - 1
                end_var = optimizer.model.NewIntVar(0, max_slot, f"end_{idx}")
                constraint_expr = optimizer.model.Add(end_var == start_var + duration_slots)
                optimizer.add_constraint(
                    constraint_expr=constraint_expr,
                    constraint_type=ConstraintType.OTHER,
                    origin_module=__name__,
                    origin_function="_get_class_time_variables",
                    class_i=idx,
                    description=f"End time variable: end_{idx} = start_{idx} + {duration_slots}",
                    variables_used=[f"start_var[{idx}]", f"end_var[{idx}]"]
                )
                
                # Используем effective_bounds для получения временных границ
                try:
                    bounds = get_effective_bounds(optimizer, idx, class_obj)
                    
                    if classify_bounds(bounds) == 'fixed':
                        # Занятие фиксировано
                        start_minutes = time_to_minutes(bounds.min_time)
                        end_minutes = start_minutes + class_obj.duration
                    else:
                        # Занятие с временным окном
                        start_minutes = time_to_minutes(bounds.min_time)  # Начало окна для отображения
                        end_minutes = start_minutes + class_obj.duration
                except Exception as e:
                    print(f"Warning: Could not get effective bounds for class {idx}: {e}")
                    # Fallback к оригинальной логике
                    if class_obj.start_time:
                        start_minutes = time_to_minutes(class_obj.start_time)
                        end_minutes = start_minutes + class_obj.duration
                    else:
                        start_minutes = None
                        end_minutes = None
                    
            return start_var, end_var, start_minutes, end_minutes
        else:
            # Fallback к effective_bounds если CP-SAT переменные недоступны
            try:
                bounds = get_effective_bounds(optimizer, idx, class_obj)
                
                if classify_bounds(bounds) == 'fixed':
                    start_minutes = time_to_minutes(bounds.min_time)
                    end_minutes = start_minutes + class_obj.duration
                else:
                    # Используем начало окна для fallback
                    start_minutes = time_to_minutes(bounds.min_time)
                    end_minutes = start_minutes + class_obj.duration
                    
                return None, None, start_minutes, end_minutes
            except Exception as e:
                print(f"Warning: Could not get effective bounds for class {idx}: {e}")
                # Последний fallback к оригинальным полям
                if class_obj.start_time:
                    start_minutes = time_to_minutes(class_obj.start_time)
                    end_minutes = start_minutes + class_obj.duration
                    return None, None, start_minutes, end_minutes
                else:
                    return None, None, None, None
    
    # Классы с одним преподавателем нуждаются в ограничениях только если пересекаются по времени
    if c1.teacher == c2.teacher:
        # Получаем переменные времени для обоих классов
        start_var1, end_var1, start_min1, end_min1 = _get_class_time_variables(optimizer, idx_c1, c1)
        start_var2, end_var2, start_min2, end_min2 = _get_class_time_variables(optimizer, idx_c2, c2)
        
        # Если у нас есть статические времена, используем их для анализа
        if start_min1 is not None and start_min2 is not None:
            # Get interval information from can_schedule_sequentially
            can_schedule, info = can_schedule_sequentially(c1, c2, idx_c1, idx_c2, verbose=False)
            
            # НОВОЕ: Специальная обработка для chain_and_resource_gap
            if can_schedule and info.get("reason") == "chain_and_resource_gap":
                print(f"      Same teacher with chain_and_resource_gap - constraint needed for proper sequencing")
                return True
            
            # Use intervals from can_schedule_sequentially if available
            start1, end1 = info.get("c1_interval", (start_min1, end_min1 + getattr(c1, 'pause_after', 0)))
            start2, end2 = info.get("c2_interval", (start_min2, end_min2 + getattr(c2, 'pause_after', 0)))
            
            # Если времена не пересекаются, ограничения не нужны даже для одного преподавателя
            if end1 <= start2 or end2 <= start1:
                print(f"      Same teacher but non-overlapping times [{minutes_to_time(start1)}-{minutes_to_time(end1)}] vs [{minutes_to_time(start2)}-{minutes_to_time(end2)}] - no constraint needed")
                return False
            else:
                print(f"      Same teacher with overlapping times - constraint needed")
                return True
        else:
            # Если время не фиксировано или переменные CP-SAT, нужны ограничения для одного преподавателя
            print(f"      Same teacher with flexible times (CP-SAT variables) - constraint needed")
            return True
    
    # Классы с общими группами студентов нуждаются в ограничениях только если пересекаются по времени
    shared_groups = set(c1.get_groups()) & set(c2.get_groups())
    if shared_groups:
        # Получаем переменные времени для обоих классов
        start_var1, end_var1, start_min1, end_min1 = _get_class_time_variables(optimizer, idx_c1, c1)
        start_var2, end_var2, start_min2, end_min2 = _get_class_time_variables(optimizer, idx_c2, c2)
        
        if start_min1 is not None and start_min2 is not None:
            # Проверяем возможность последовательного размещения
            can_schedule, info = can_schedule_sequentially(c1, c2, idx_c1, idx_c2, verbose=False)
            
            # НОВОЕ: Специальная обработка для chain_and_resource_gap
            if can_schedule and info.get("reason") == "chain_and_resource_gap":
                print(f"      Shared groups {shared_groups} with chain_and_resource_gap - constraint needed for proper sequencing")
                return True
            
            end1 = end_min1 + getattr(c1, 'pause_after', 0)
            end2 = end_min2 + getattr(c2, 'pause_after', 0)
            
            # Если времена не пересекаются, ограничения не нужны даже для общих групп
            if end1 <= start_min2 or end2 <= start_min1:
                print(f"      Shared groups {shared_groups} but non-overlapping times - no constraint needed")
                return False
            else:
                print(f"      Shared groups {shared_groups} with overlapping times - constraint needed")
                return True
        else:
            print(f"      Shared groups {shared_groups} with flexible times (CP-SAT variables) - constraint needed")
            return True
    
    # Классы с пересекающимися возможными аудиториями могут нуждаться в ограничениях
    shared_rooms = set(c1.possible_rooms) & set(c2.possible_rooms)
    if shared_rooms:
        # Получаем переменные времени для обоих классов
        start_var1, end_var1, start_min1, end_min1 = _get_class_time_variables(optimizer, idx_c1, c1)
        start_var2, end_var2, start_min2, end_min2 = _get_class_time_variables(optimizer, idx_c2, c2)
        
        # Проверяем пересечение времени выполнения
        if start_min1 is not None and start_min2 is not None:
            # Проверяем возможность последовательного размещения
            can_schedule, info = can_schedule_sequentially(c1, c2, idx_c1, idx_c2, verbose=False)
            
            # НОВОЕ: Специальная обработка для chain_and_resource_gap
            if can_schedule and info.get("reason") == "chain_and_resource_gap":
                print(f"      Shared rooms {shared_rooms} with chain_and_resource_gap - constraint needed for proper sequencing")
                return True
            
            # Для аудиторий не учитываем паузы, только время самих занятий
            
            # Если времена не пересекаются, ограничения не нужны
            if end_min1 <= start_min2 or end_min2 <= start_min1:
                print(f"      Shared rooms {shared_rooms} but non-overlapping times - no constraint needed")
                return False
            else:
                print(f"      Shared rooms {shared_rooms} with overlapping times - constraint needed")
                return True
        else:
            print(f"      Shared rooms {shared_rooms} with flexible times (CP-SAT variables) - constraint needed")
            return True
    
    # По умолчанию не добавляем ограничения
    print(f"      No resource conflicts detected - no constraint needed")
    return False


def _log_class_time_window_info(optimizer, idx, c, label):
    """
    Логирует информацию о временных окнах и ограничениях для класса.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        idx: Индекс класса
        c: Объект класса
        label: Метка для логирования
    """
    print(f"    {label} {idx}: {c.subject} - {c.group}")
    
    # Информация об effective bounds
    try:
        bounds = get_effective_bounds(optimizer, idx, c)
        print(f"      Effective bounds: {bounds.min_time} - {bounds.max_time} (source: {bounds.source})")
        print(f"      Type: {classify_bounds(bounds)}")
        
        if bounds.applied_constraints:
            print(f"      Applied constraints:")
            for constraint in bounds.applied_constraints:
                print(f"        - {constraint['type']}: {constraint['description']}")
    except Exception as e:
        print(f"      Warning: Could not get effective bounds: {e}")
        
        # Fallback к оригинальным полям
        if c.start_time and c.end_time:
            print(f"      Original time window: {c.start_time} - {c.end_time}")
        elif c.start_time:
            print(f"      Fixed start time: {c.start_time}")
        else:
            print(f"      No fixed time")
    
    # Информация о текущих ограничениях переменной
    if hasattr(optimizer, 'start_vars') and idx < len(optimizer.start_vars):
        start_var = optimizer.start_vars[idx]
        if isinstance(start_var, int):
            # Переменная уже зафиксирована
            time_slot = optimizer.time_slots[start_var] if start_var < len(optimizer.time_slots) else "INVALID"
            print(f"      Variable FIXED to slot {start_var} (time: {time_slot})")
        else:
            # Переменная все еще является переменной CP-SAT
            print(f"      Variable is flexible (CP-SAT variable)")
            
            # Проверяем, есть ли уже применённые ограничения на эту переменную
            if hasattr(optimizer, 'model') and optimizer.model:
                # Пытаемся получить информацию о доменах (это может не работать во всех версиях)
                try:
                    print(f"      Variable domain info not available during constraint building")
                except:
                    pass
    else:
        print(f"      Variable not yet created")
    
    # Информация о цепочках
    chain_info = getattr(c, 'linked_to', None)
    if chain_info:
        print(f"      Part of chain: linked to {chain_info}")
    else:
        print(f"      Not part of any chain")
