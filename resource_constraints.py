"""
Модуль для добавления ограничений ресурсов (преподаватели, аудитории, группы).
"""

from conflict_detector import check_potential_conflicts
from time_conflict_constraints import _add_time_conflict_constraints
from time_utils import time_to_minutes
from sequential_scheduling import can_schedule_sequentially as can_schedule_sequentially_full, minutes_to_time 
from constraint_registry import ConstraintType
from effective_bounds_utils import get_effective_bounds, EffectiveBounds
from linked_chain_utils import are_classes_in_same_chain, get_chain_window
from chain_helpers import invalidate_chain_window

def times_overlap(optimizer, c1, c2, idx1=None, idx2=None):
    """
    Проверяет пересечение по времени двух занятий с использованием эффективных границ.
    Для занятий внутри одной цепочки использует окно цепочки вместо individual effective_bounds.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        c1, c2: Объекты занятий
        idx1, idx2: Индексы занятий (для получения эффективных границ)
    """
    # НОВОЕ: Проверяем, принадлежат ли занятия одной цепочке
    if idx1 is not None and idx2 is not None and are_classes_in_same_chain(optimizer, idx1, idx2):
        from linked_chain_utils import find_chain_containing_classes
        
        chain_indices = find_chain_containing_classes(optimizer, idx1, idx2)
        
        # Инвалидируем кеш окна цепочки перед получением окна
        if chain_indices:
            schedule_class = optimizer.classes[chain_indices[0]]
            invalidate_chain_window(schedule_class)
        
        chain_window = get_chain_window(optimizer, chain_indices)
        
        if chain_window is not None:
            # Для занятий внутри одной цепочки используем окно цепочки
            window_start = chain_window['min_minutes']
            window_end = chain_window['max_minutes']
            
            # Рассчитываем общее время, необходимое для обоих занятий
            total_duration = c1.duration + c2.duration
            min_gap = max(getattr(c1, 'pause_after', 0), getattr(c2, 'pause_before', 0))
            required_time = total_duration + min_gap
            available_time = window_end - window_start
            
            # Занятия пересекаются по времени, если они не могут поместиться последовательно в окне цепочки
            overlap = available_time < required_time
            
            print(f"  Time overlap analysis using chain window:")
            print(f"    Chain window: {chain_window['min_time']}-{chain_window['max_time']}")
            print(f"    Available time: {available_time} min, Required time: {required_time} min")
            print(f"    Overlap (cannot fit sequentially): {'YES' if overlap else 'NO'}")
            
            return overlap
        else:
            print(f"  WARNING: Could not determine chain window for classes {idx1}, {idx2}")
    
    # Получаем эффективные границы для более точного анализа (для занятий не в одной цепочке)
    if idx1 is not None and idx2 is not None:
        bounds1 = get_effective_bounds(optimizer, idx1, c1)
        bounds2 = get_effective_bounds(optimizer, idx2, c2)
        
        # Конвертируем в минуты для сравнения
        start1_min = time_to_minutes(bounds1.min_time)
        end1_min = time_to_minutes(bounds1.max_time) + c1.duration
        start2_min = time_to_minutes(bounds2.min_time)
        end2_min = time_to_minutes(bounds2.max_time) + c2.duration
        
        overlap = (start1_min < end2_min) and (start2_min < end1_min)
        
        print(f"  Time overlap analysis using effective bounds:")
        print(f"    Class {idx1}: {bounds1.min_time}-{bounds1.max_time} + {c1.duration}min = {start1_min}-{end1_min}")
        print(f"    Class {idx2}: {bounds2.min_time}-{bounds2.max_time} + {c2.duration}min = {start2_min}-{end2_min}")
        print(f"    Overlap: {'YES' if overlap else 'NO'}")
        
        return overlap
    
    # Fallback к исходной логике для обратной совместимости
    if not c1.start_time or not c2.start_time:
        # Одно из занятий не имеет фиксированного времени — считаем пересекающимся
        return True
    start1 = time_to_minutes(c1.start_time)
    end1 = start1 + c1.duration
    start2 = time_to_minutes(c2.start_time)
    end2 = start2 + c2.duration
    return (start1 < end2) and (start2 < end1)


def add_resource_conflict_constraints(optimizer):
    """Add constraints to prevent conflicts in resources (teachers, rooms, groups)."""
    print("\n=== ADDING RESOURCE CONFLICT CONSTRAINTS ===")
    
    # ИСПРАВЛЕНО: Гарантируем инициализацию linked_chains до проверок
    if not hasattr(optimizer, 'linked_chains'):
        from linked_chain_utils import build_linked_chains
        build_linked_chains(optimizer)
        print(f"  Initialized linked chains: {len(optimizer.linked_chains)} chains found")
    
    # Напечатать подробную информацию о занятиях для отладки
    print("\nDetailed class information:")
    for idx, c in enumerate(optimizer.classes):
        time_info = f"{c.start_time}"
        if c.end_time:
            time_info += f"-{c.end_time}"
        
        room_info = ", ".join(c.possible_rooms)
        print(f"Class {idx}: {c.subject} - {c.group} - {c.teacher} - {c.day} {time_info}")
        print(f"  Duration: {c.duration} min, Pause before: {c.pause_before} min, Pause after: {c.pause_after} min")
        print(f"  Room(s): {room_info}")
        
    # Предварительная проверка конфликтов
    check_potential_conflicts(optimizer)

    # For each pair of classes
    num_classes = len(optimizer.classes)
    total_pairs = 0
    processed_pairs = 0
    skipped_pairs = 0
    
    for i in range(num_classes):
        c_i = optimizer.classes[i]
        
        for j in range(i + 1, num_classes):
            c_j = optimizer.classes[j]
            total_pairs += 1

            # Пропускаем сравнение, если занятия в разные дни
            if c_i.day != c_j.day:
                optimizer.skip_constraint(
                    constraint_type=ConstraintType.RESOURCE_CONFLICT,
                    origin_module=__name__,
                    origin_function="add_resource_conflict_constraints",
                    class_i=i,
                    class_j=j,
                    reason=f"Different days: {c_i.day} vs {c_j.day}"
                )
                skipped_pairs += 1
                continue

            # ВАЖНОЕ ИЗМЕНЕНИЕ: Всегда проверяем возможные конфликты по комнатам,
            # даже если у классов разные учителя и группы
            shared_rooms = set(c_i.possible_rooms) & set(c_j.possible_rooms)
            if shared_rooms:
                print(f"Checking room conflict between classes {i} and {j} in rooms {shared_rooms}")
                # Добавляем ограничения, чтобы предотвратить конфликты по времени в одной комнате
                _add_time_conflict_constraints(optimizer, i, j, c_i, c_j)
                processed_pairs += 1
                continue  # Продолжаем со следующей парой классов

            # Пропускаем сравнение, если занятия не пересекаются по времени
            if not times_overlap(optimizer, c_i, c_j, i, j):
                optimizer.skip_constraint(
                    constraint_type=ConstraintType.RESOURCE_CONFLICT,
                    origin_module=__name__,
                    origin_function="add_resource_conflict_constraints",
                    class_i=i,
                    class_j=j,
                    reason="No time overlap (effective bounds)"
                )
                skipped_pairs += 1
                continue
            
            # Skip if classes are linked (already handled)
            if hasattr(c_i, 'linked_classes') and c_j in c_i.linked_classes:
                optimizer.skip_constraint(
                    constraint_type=ConstraintType.RESOURCE_CONFLICT,
                    origin_module=__name__,
                    origin_function="add_resource_conflict_constraints",
                    class_i=i,
                    class_j=j,
                    reason="Classes are linked"
                )
                skipped_pairs += 1
                continue
            if hasattr(c_j, 'linked_classes') and c_i in c_j.linked_classes:
                optimizer.skip_constraint(
                    constraint_type=ConstraintType.RESOURCE_CONFLICT,
                    origin_module=__name__,
                    origin_function="add_resource_conflict_constraints",
                    class_i=i,
                    class_j=j,
                    reason="Classes are linked"
                )
                skipped_pairs += 1
                continue
            
            # Skip if one class is the previous_class of the other
            # ИСПРАВЛЕНО: previous_class теперь ссылка на объект, а не строка
            if (hasattr(c_i, 'previous_class') and c_i.previous_class and c_i.previous_class == c_j) or \
               (hasattr(c_j, 'previous_class') and c_j.previous_class and c_j.previous_class == c_i):
                optimizer.skip_constraint(
                    constraint_type=ConstraintType.RESOURCE_CONFLICT,
                    origin_module=__name__,
                    origin_function="add_resource_conflict_constraints",
                    class_i=i,
                    class_j=j,
                    reason="One class is previous_class of the other"
                )
                skipped_pairs += 1
                continue
            
            # Check if both classes share resources (teacher, room, group)
            resource_conflict = False
            conflict_description = []
            
            # Проверка конфликта преподавателя
            if c_i.teacher == c_j.teacher and c_i.teacher:
                # Проверяем, есть ли общие группы
                shared_groups = set(c_i.get_groups()) & set(c_j.get_groups())
                if shared_groups:
                    # Если есть общие группы, всегда считаем конфликтом
                    resource_conflict = True
                    conflict_description.append(f"teacher '{c_i.teacher}' and shared groups {shared_groups}")
                else:
                    # Если группы разные, проверяем возможность последовательного планирования
                    can_schedule, _ = can_schedule_sequentially_full(c_i, c_j, i, j, verbose=False, optimizer=optimizer)
                    if not can_schedule:
                        # Если последовательное планирование невозможно, отмечаем конфликт
                        resource_conflict = True
                        conflict_description.append(f"teacher '{c_i.teacher}' with different groups (cannot schedule sequentially)")
            
            # Проверка конфликта аудитории
            shared_rooms = set(c_i.possible_rooms) & set(c_j.possible_rooms)
            if shared_rooms:
                # Проверяем возможность последовательного размещения
                can_schedule, _ = can_schedule_sequentially_full(c_i, c_j, i, j, verbose=False, optimizer=optimizer)
                if not can_schedule:
                    resource_conflict = True
                    conflict_description.append(f"rooms {shared_rooms}")
            
            # Проверка конфликта групп
            shared_groups = set(c_i.get_groups()) & set(c_j.get_groups())
            if shared_groups:
                resource_conflict = True
                conflict_description.append(f"groups {shared_groups}")
            
            # Если обнаружен потенциальный конфликт, добавляем ограничения по времени
            if resource_conflict:
                conflict_str = ", ".join(conflict_description)
                print(f"Detected potential conflict between '{c_i.subject}' and '{c_j.subject}' (shared {conflict_str})")
                
                _add_time_conflict_constraints(optimizer, i, j, c_i, c_j)
                processed_pairs += 1
            else:
                optimizer.skip_constraint(
                    constraint_type=ConstraintType.RESOURCE_CONFLICT,
                    origin_module=__name__,
                    origin_function="add_resource_conflict_constraints",
                    class_i=i,
                    class_j=j,
                    reason="No resource conflicts detected"
                )
                skipped_pairs += 1
    
    print(f"\n=== RESOURCE CONFLICT CONSTRAINTS SUMMARY ===")
    print(f"Total class pairs: {total_pairs}")
    print(f"Processed pairs: {processed_pairs}")
    print(f"Skipped pairs: {skipped_pairs}")
    print(f"Processing rate: {processed_pairs/total_pairs*100:.1f}%")
    print("="*50)
                
def _add_room_conflict_constraints(optimizer, i, j, c_i, c_j):
    """
    Добавляет ограничения для предотвращения конфликтов аудиторий.
    Если два занятия назначены в одну аудиторию И в одно время, то это конфликт.
    """
    from time_constraint_utils import create_conflict_variables, add_time_overlap_constraints
    
    # Создаем переменную для определения, находятся ли занятия в одной аудитории
    same_room = optimizer.model.NewBoolVar(f"same_room_{i}_{j}")
    
    # Устанавливаем значение same_room на основе назначенных аудиторий
    if isinstance(optimizer.room_vars[i], int) and isinstance(optimizer.room_vars[j], int):
        # Оба занятия имеют фиксированные аудитории
        if optimizer.room_vars[i] == optimizer.room_vars[j]:
            constraint_expr = optimizer.model.Add(same_room == 1)
            optimizer.add_constraint(
                constraint_expr=constraint_expr,
                constraint_type=ConstraintType.ROOM_CONFLICT,
                origin_module=__name__,
                origin_function="_add_room_conflict_constraints",
                class_i=i,
                class_j=j,
                description=f"Fixed rooms same: classes {i} and {j}",
                variables_used=[f"same_room_{i}_{j}"]
            )
        else:
            constraint_expr = optimizer.model.Add(same_room == 0)
            optimizer.add_constraint(
                constraint_expr=constraint_expr,
                constraint_type=ConstraintType.ROOM_CONFLICT,
                origin_module=__name__,
                origin_function="_add_room_conflict_constraints",
                class_i=i,
                class_j=j,
                description=f"Fixed rooms different: classes {i} and {j}",
                variables_used=[f"same_room_{i}_{j}"]
            )
    elif isinstance(optimizer.room_vars[i], int):
        # Только занятие i имеет фиксированную аудиторию
        constraint_expr1 = optimizer.model.Add(optimizer.room_vars[j] == optimizer.room_vars[i]).OnlyEnforceIf(same_room)
        constraint_expr2 = optimizer.model.Add(optimizer.room_vars[j] != optimizer.room_vars[i]).OnlyEnforceIf(same_room.Not())
        optimizer.add_constraint(
            constraint_expr=constraint_expr1,
            constraint_type=ConstraintType.ROOM_CONFLICT,
            origin_module=__name__,
            origin_function="_add_room_conflict_constraints",
            class_i=i,
            class_j=j,
            description=f"Room match check (fixed i): classes {i} and {j}",
            variables_used=[f"room_vars[{j}]", f"same_room_{i}_{j}"]
        )
        optimizer.add_constraint(
            constraint_expr=constraint_expr2,
            constraint_type=ConstraintType.ROOM_CONFLICT,
            origin_module=__name__,
            origin_function="_add_room_conflict_constraints",
            class_i=i,
            class_j=j,
            description=f"Room mismatch check (fixed i): classes {i} and {j}",
            variables_used=[f"room_vars[{j}]", f"same_room_{i}_{j}"]
        )
    elif isinstance(optimizer.room_vars[j], int):
        # Только занятие j имеет фиксированную аудиторию
        constraint_expr1 = optimizer.model.Add(optimizer.room_vars[i] == optimizer.room_vars[j]).OnlyEnforceIf(same_room)
        constraint_expr2 = optimizer.model.Add(optimizer.room_vars[i] != optimizer.room_vars[j]).OnlyEnforceIf(same_room.Not())
        optimizer.add_constraint(
            constraint_expr=constraint_expr1,
            constraint_type=ConstraintType.ROOM_CONFLICT,
            origin_module=__name__,
            origin_function="_add_room_conflict_constraints",
            class_i=i,
            class_j=j,
            description=f"Room match check (fixed j): classes {i} and {j}",
            variables_used=[f"room_vars[{i}]", f"same_room_{i}_{j}"]
        )
        optimizer.add_constraint(
            constraint_expr=constraint_expr2,
            constraint_type=ConstraintType.ROOM_CONFLICT,
            origin_module=__name__,
            origin_function="_add_room_conflict_constraints",
            class_i=i,
            class_j=j,
            description=f"Room mismatch check (fixed j): classes {i} and {j}",
            variables_used=[f"room_vars[{i}]", f"same_room_{i}_{j}"]
        )
    else:
        # Оба занятия имеют переменные аудитории
        constraint_expr1 = optimizer.model.Add(optimizer.room_vars[i] == optimizer.room_vars[j]).OnlyEnforceIf(same_room)
        constraint_expr2 = optimizer.model.Add(optimizer.room_vars[i] != optimizer.room_vars[j]).OnlyEnforceIf(same_room.Not())
        optimizer.add_constraint(
            constraint_expr=constraint_expr1,
            constraint_type=ConstraintType.ROOM_CONFLICT,
            origin_module=__name__,
            origin_function="_add_room_conflict_constraints",
            class_i=i,
            class_j=j,
            description=f"Room match check (variable): classes {i} and {j}",
            variables_used=[f"room_vars[{i}]", f"room_vars[{j}]", f"same_room_{i}_{j}"]
        )
        optimizer.add_constraint(
            constraint_expr=constraint_expr2,
            constraint_type=ConstraintType.ROOM_CONFLICT,
            origin_module=__name__,
            origin_function="_add_room_conflict_constraints",
            class_i=i,
            class_j=j,
            description=f"Room mismatch check (variable): classes {i} and {j}",
            variables_used=[f"room_vars[{i}]", f"room_vars[{j}]", f"same_room_{i}_{j}"]
        )
    
    # Создаем переменные для определения временного конфликта
    conflict, same_day, time_overlap = create_conflict_variables(optimizer, i, j, c_i, c_j)
    
    # Добавляем ограничения для определения перекрытия времени
    add_time_overlap_constraints(optimizer, i, j, c_i, c_j, time_overlap)
    
    # Temporal conflict if same day and time overlap
    temporal_conflict = optimizer.model.NewBoolVar(f"temporal_conflict_{i}_{j}")
    optimizer.model.AddBoolAnd([same_day, time_overlap]).OnlyEnforceIf(temporal_conflict)
    optimizer.model.AddBoolOr([same_day.Not(), time_overlap.Not()]).OnlyEnforceIf(temporal_conflict.Not())
    
    # Room conflict if same room and temporal conflict
    room_conflict = optimizer.model.NewBoolVar(f"room_conflict_{i}_{j}")
    optimizer.model.AddBoolAnd([same_room, temporal_conflict]).OnlyEnforceIf(room_conflict)
    optimizer.model.AddBoolOr([same_room.Not(), temporal_conflict.Not()]).OnlyEnforceIf(room_conflict.Not())
    
    # Prevent room conflicts
    constraint_expr = optimizer.model.Add(room_conflict == False)
    optimizer.add_constraint(
        constraint_expr=constraint_expr,
        constraint_type=ConstraintType.ROOM_CONFLICT,
        origin_module=__name__,
        origin_function="_add_room_conflict_constraints",
        class_i=i,
        class_j=j,
        description=f"Prevent room conflicts: classes {i} and {j}",
        variables_used=[f"room_conflict_{i}_{j}"]
    )
    
    print(f"  Added room conflict constraints between classes {i} and {j}")