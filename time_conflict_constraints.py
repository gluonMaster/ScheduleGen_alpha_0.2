"""
Модуль для добавления ограничений по времени и предотвращения конфликтов.
"""
from time_utils import time_to_minutes, minutes_to_time
from time_constraint_utils import create_conflict_variables, add_time_overlap_constraints
from sequential_scheduling_checker import _check_sequential_scheduling, check_two_window_classes
from timewindow_utils import find_slot_for_time
from sequential_scheduling import can_schedule_sequentially
from constraint_registry import ConstraintType
from effective_bounds_utils import get_effective_bounds, classify_bounds
from linked_chain_utils import pick_best_anchor
from chain_helpers import collect_full_chain_from_any_member

def add_anchor_based_constraint(optimizer, flex_class_idx, flex_class, target_class_idx, target_class):
    """
    Добавляет ограничение между гибким классом и якорным классом в цепочке.
    Заменяет прямое ограничение на умный выбор якорного урока внутри цепочки.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        flex_class_idx: Индекс гибкого класса
        flex_class: Объект гибкого класса
        target_class_idx: Индекс целевого класса (принадлежащего цепочке)
        target_class: Объект целевого класса
        
    Returns:
        bool: True если ограничение было добавлено, False если цепочка не найдена
    """
    print(f"\n=== ANCHOR-BASED CONSTRAINT PROCESSING ===")
    print(f"Flex class {flex_class_idx}: {flex_class.subject}")
    print(f"Target class {target_class_idx}: {target_class.subject}")
    
    # ИСПРАВЛЕНО: Используем более надежную стратегию поиска цепочек
    chain_classes = []
    
    # Приоритет 1: Проверяем через optimizer.linked_chains (наиболее надежно)
    if hasattr(optimizer, 'linked_chains'):
        for chain_indices in optimizer.linked_chains:
            if target_class_idx in chain_indices:
                chain_classes = [optimizer.classes[idx] for idx in chain_indices]
                print(f"  Found chain via optimizer.linked_chains: {len(chain_classes)} classes")
                break
    
    # Приоритет 2: Пытаемся найти цепочку через linked_classes
    if not chain_classes and hasattr(target_class, 'linked_classes') and target_class.linked_classes:
        # target_class - начало цепочки
        try:
            chain_classes = collect_full_chain_from_any_member(target_class)
            print(f"  Found chain starting from target class: {len(chain_classes)} classes")
        except Exception as e:
            print(f"  Warning: Failed to collect chain from target class: {e}")
    
    # Приоритет 3: target_class - продолжение цепочки, найдем начало
    if not chain_classes and hasattr(target_class, 'previous_class') and target_class.previous_class:
        try:
            root_class = target_class
            while hasattr(root_class, 'previous_class') and root_class.previous_class:
                root_class = root_class.previous_class
            chain_classes = collect_full_chain_from_any_member(root_class)
            print(f"  Found chain from root class: {len(chain_classes)} classes")
        except Exception as e:
            print(f"  Warning: Failed to collect chain from root class: {e}")
    
    if not chain_classes:
        print(f"  No chain found for target class {target_class_idx}")
        return False
    
    # Выбираем лучший якорный урок
    anchor = pick_best_anchor(flex_class, chain_classes, direction="before", optimizer=optimizer)
    
    if anchor is None:
        print(f"  No suitable anchor found in chain")
        return False
    
    # Находим индекс якорного урока
    try:
        anchor_idx = optimizer.classes.index(anchor)
    except ValueError:
        print(f"  Error: anchor class not found in optimizer.classes")
        return False
    
    print(f"  Selected anchor: {anchor.subject} (index {anchor_idx})")
    
    # Создаем ограничение: flex_class должен закончиться до начала anchor
    duration_slots = flex_class.duration // optimizer.time_interval
    pause_slots = max(1, (getattr(flex_class, 'pause_after', 0) + 
                         getattr(anchor, 'pause_before', 0)) // optimizer.time_interval)
    
    constraint_expr = optimizer.model.Add(
        optimizer.start_vars[flex_class_idx] + duration_slots + pause_slots <= optimizer.start_vars[anchor_idx]
    )
    
    optimizer.add_constraint(
        constraint_expr=constraint_expr,
        constraint_type=ConstraintType.SEQUENTIAL,
        origin_module=__name__,
        origin_function="add_anchor_based_constraint",
        class_i=flex_class_idx,
        class_j=anchor_idx,
        description=f"Anchor-based sequential: {flex_class.subject} before {anchor.subject}",
        variables_used=[f"start_var[{flex_class_idx}]", f"start_var[{anchor_idx}]"]
    )
    
    print(f"  ✓ Added anchor-based constraint: class {flex_class_idx} + {duration_slots} + {pause_slots} <= class {anchor_idx}")
    print("=" * 50)
    
    return True


def add_sequential_constraints(optimizer, i, j, c_i, c_j):
    """
    Добавляет строгие ограничения для последовательного размещения занятий.
    Теперь с проверкой на цепочки и использованием якорных уроков.
    """
    print(f"\n=== ADDING SEQUENTIAL CONSTRAINTS ===")
    print(f"Classes {i} and {j}: {c_i.subject} vs {c_j.subject}")
    
    # НОВОЕ: Проверяем, принадлежат ли занятия цепочкам
    from sequential_scheduling import is_class_in_linked_chain
    
    c_i_in_chain = is_class_in_linked_chain(c_i)
    c_j_in_chain = is_class_in_linked_chain(c_j)
    
    print(f"  Class {i} ({c_i.subject}) in chain: {c_i_in_chain}")
    print(f"  Class {j} ({c_j.subject}) in chain: {c_j_in_chain}")
    
    # Якорная логика применяется только когда одно занятие в цепочке, а другое - нет
    if c_j_in_chain and not c_i_in_chain:
        # c_j в цепочке, c_i свободное - привязываем c_i к якорю в цепочке c_j
        if add_anchor_based_constraint(optimizer, i, c_i, j, c_j):
            print(f"  ✓ Used anchor-based constraint: free class {i} anchored to chain containing class {j}")
            return
    elif c_i_in_chain and not c_j_in_chain:
        # c_i в цепочке, c_j свободное - привязываем c_j к якорю в цепочке c_i
        if add_anchor_based_constraint(optimizer, j, c_j, i, c_i):
            print(f"  ✓ Used anchor-based constraint: free class {j} anchored to chain containing class {i}")
            return
    elif c_i_in_chain and c_j_in_chain:
        print(f"  Both classes are in chains - using standard sequential constraints")
    else:
        print(f"  Neither class is in a chain - using standard sequential constraints")
    
    # Оригинальная логика для случаев без якорной привязки
    print(f"  Applying direct sequential constraints")
    
    # Создаем булеву переменную для определения порядка занятий
    i_before_j = optimizer.model.NewBoolVar(f"seq_strict_{i}_{j}")
    
    # Расчет длительности в слотах времени
    duration_i_slots = c_i.duration // optimizer.time_interval
    duration_j_slots = c_j.duration // optimizer.time_interval
    
    # Переменные для конца занятий
    end_i = optimizer.model.NewIntVar(0, len(optimizer.time_slots), f"seq_end_{i}")
    end_j = optimizer.model.NewIntVar(0, len(optimizer.time_slots), f"seq_end_{j}")
    
    # Устанавливаем значения концов занятий
    constraint1 = optimizer.model.Add(end_i == optimizer.start_vars[i] + duration_i_slots)
    constraint2 = optimizer.model.Add(end_j == optimizer.start_vars[j] + duration_j_slots)
    
    optimizer.add_constraint(
        constraint_expr=constraint1,
        constraint_type=ConstraintType.SEQUENTIAL,
        origin_module=__name__,
        origin_function="add_sequential_constraints",
        class_i=i,
        class_j=j,
        description=f"End time calculation for class {i}",
        variables_used=[str(end_i), f"start_var[{i}]"]
    )
    
    optimizer.add_constraint(
        constraint_expr=constraint2,
        constraint_type=ConstraintType.SEQUENTIAL,
        origin_module=__name__,
        origin_function="add_sequential_constraints",
        class_i=i,
        class_j=j,
        description=f"End time calculation for class {j}",
        variables_used=[str(end_j), f"start_var[{j}]"]
    )
    
    # Минимальный интервал между занятиями - с исправленным округлением вверх
    min_pause = (c_i.pause_after + c_j.pause_before + optimizer.time_interval - 1) // optimizer.time_interval
    
    # Строгое ограничение: i перед j или j перед i, без перекрытия
    constraint3 = optimizer.model.Add(end_i + min_pause <= optimizer.start_vars[j]).OnlyEnforceIf(i_before_j)
    constraint4 = optimizer.model.Add(end_j + min_pause <= optimizer.start_vars[i]).OnlyEnforceIf(i_before_j.Not())
    
    optimizer.add_constraint(
        constraint_expr=constraint3,
        constraint_type=ConstraintType.SEQUENTIAL,
        origin_module=__name__,
        origin_function="add_sequential_constraints",
        class_i=i,
        class_j=j,
        description=f"Sequential ordering (i→j): class {i} before class {j}",
        variables_used=[str(end_i), f"start_var[{j}]", str(i_before_j)]
    )
    
    optimizer.add_constraint(
        constraint_expr=constraint4,
        constraint_type=ConstraintType.SEQUENTIAL,
        origin_module=__name__,
        origin_function="add_sequential_constraints",
        class_i=j,
        class_j=i,
        description=f"Sequential ordering (j→i): class {j} before class {i}",
        variables_used=[str(end_j), f"start_var[{i}]", str(i_before_j)]
    )
    
    print(f"  ✓ Added STRICT sequential constraints between classes {i} and {j} with min pause {min_pause} slots")

def _add_time_conflict_constraints(optimizer, i, j, c_i, c_j):
    """
    Добавляет ограничения для предотвращения конфликтов времени между занятиями.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        i, j: Индексы классов
        c_i, c_j: Экземпляры ScheduleClass
    """
    print(f"\n=== ADDING TIME CONFLICT CONSTRAINTS ===")
    print(f"Classes {i} and {j}: {c_i.subject} vs {c_j.subject}")
    
    # Проверка: если занятия в разные дни — не анализируем конфликт
    if c_i.day != c_j.day:
        optimizer.skip_constraint(
            constraint_type=ConstraintType.TIME_WINDOW,
            origin_module=__name__,
            origin_function="_add_time_conflict_constraints",
            class_i=i,
            class_j=j,
            reason=f"Different days: {c_i.day} vs {c_j.day}"
        )
        return
    
    # Проверяем наличие общих аудиторий и групп
    shared_rooms = set(c_i.possible_rooms) & set(c_j.possible_rooms)
    shared_groups = set(c_i.get_groups()) & set(c_j.get_groups())

    # Флаг для обязательного добавления ограничений при общих группах
    must_add_constraints = (shared_groups and c_i.day == c_j.day) or (shared_rooms and c_i.day == c_j.day)
    
    print(f"  Shared rooms: {shared_rooms}")
    print(f"  Shared groups: {shared_groups}")
    print(f"  Must add constraints: {must_add_constraints}")
    
    # Если оба занятия имеют фиксированное время начала
    if c_i.fixed_start_time and c_j.fixed_start_time:
        print(f"  Both classes have fixed start times")
        # Оба занятия фиксированные - проверяем реальное пересечение
        conflict, same_day, time_overlap = create_conflict_variables(optimizer, i, j, c_i, c_j)
        add_time_overlap_constraints(optimizer, i, j, c_i, c_j, time_overlap)
        
        # Правильная логика определения конфликта
        constraint1 = optimizer.model.AddBoolAnd([same_day, time_overlap]).OnlyEnforceIf(conflict)
        constraint2 = optimizer.model.AddBoolOr([same_day.Not(), time_overlap.Not()]).OnlyEnforceIf(conflict.Not())
        
        optimizer.add_constraint(
            constraint_expr=constraint1,
            constraint_type=ConstraintType.TIME_WINDOW,
            origin_module=__name__,
            origin_function="_add_time_conflict_constraints",
            class_i=i,
            class_j=j,
            description=f"Fixed time conflict detection (AND): {c_i.subject} vs {c_j.subject}",
            variables_used=[str(conflict), str(same_day), str(time_overlap)]
        )
        
        optimizer.add_constraint(
            constraint_expr=constraint2,
            constraint_type=ConstraintType.TIME_WINDOW,
            origin_module=__name__,
            origin_function="_add_time_conflict_constraints",
            class_i=i,
            class_j=j,
            description=f"Fixed time conflict detection (OR): {c_i.subject} vs {c_j.subject}",
            variables_used=[str(conflict), str(same_day), str(time_overlap)]
        )
        
        # Запрещаем конфликты
        constraint3 = optimizer.model.Add(conflict == False)
        optimizer.add_constraint(
            constraint_expr=constraint3,
            constraint_type=ConstraintType.TIME_WINDOW,
            origin_module=__name__,
            origin_function="_add_time_conflict_constraints",
            class_i=i,
            class_j=j,
            description=f"Forbid time conflicts: {c_i.subject} vs {c_j.subject}",
            variables_used=[str(conflict)]
        )
        
        # Проверяем конфликты аудиторий, даже для фиксированного времени
        if shared_rooms:
            # Добавляем проверку конфликтов с общими аудиториями
            same_room = optimizer.model.NewBoolVar(f"same_room_{i}_{j}")
            if isinstance(optimizer.room_vars[i], int) and isinstance(optimizer.room_vars[j], int):
                if optimizer.room_vars[i] == optimizer.room_vars[j]:
                    constraint4 = optimizer.model.Add(same_room == 1)
                else:
                    constraint4 = optimizer.model.Add(same_room == 0)
                    
                optimizer.add_constraint(
                    constraint_expr=constraint4,
                    constraint_type=ConstraintType.ROOM_CONFLICT,
                    origin_module=__name__,
                    origin_function="_add_time_conflict_constraints",
                    class_i=i,
                    class_j=j,
                    description=f"Room assignment constraint: {c_i.subject} vs {c_j.subject}",
                    variables_used=[str(same_room)]
                )
            else:
                # Добавляем условные ограничения для переменных комнат
                if isinstance(optimizer.room_vars[i], int):
                    constraint4 = optimizer.model.Add(optimizer.room_vars[j] == optimizer.room_vars[i]).OnlyEnforceIf(same_room)
                    constraint5 = optimizer.model.Add(optimizer.room_vars[j] != optimizer.room_vars[i]).OnlyEnforceIf(same_room.Not())
                elif isinstance(optimizer.room_vars[j], int):
                    constraint4 = optimizer.model.Add(optimizer.room_vars[i] == optimizer.room_vars[j]).OnlyEnforceIf(same_room)
                    constraint5 = optimizer.model.Add(optimizer.room_vars[i] != optimizer.room_vars[j]).OnlyEnforceIf(same_room.Not())
                else:
                    constraint4 = optimizer.model.Add(optimizer.room_vars[i] == optimizer.room_vars[j]).OnlyEnforceIf(same_room)
                    constraint5 = optimizer.model.Add(optimizer.room_vars[i] != optimizer.room_vars[j]).OnlyEnforceIf(same_room.Not())
                
                optimizer.add_constraint(
                    constraint_expr=constraint4,
                    constraint_type=ConstraintType.ROOM_CONFLICT,
                    origin_module=__name__,
                    origin_function="_add_time_conflict_constraints",
                    class_i=i,
                    class_j=j,
                    description=f"Room equality constraint: {c_i.subject} vs {c_j.subject}",
                    variables_used=[str(same_room), f"room_var[{i}]", f"room_var[{j}]"]
                )
                
                optimizer.add_constraint(
                    constraint_expr=constraint5,
                    constraint_type=ConstraintType.ROOM_CONFLICT,
                    origin_module=__name__,
                    origin_function="_add_time_conflict_constraints",
                    class_i=i,
                    class_j=j,
                    description=f"Room inequality constraint: {c_i.subject} vs {c_j.subject}",
                    variables_used=[str(same_room), f"room_var[{i}]", f"room_var[{j}]"]
                )
            
            # Если одна и та же аудитория, проверяем конфликты
            room_conflict = optimizer.model.NewBoolVar(f"room_conflict_{i}_{j}")
            constraint6 = optimizer.model.AddBoolAnd([same_room, conflict]).OnlyEnforceIf(room_conflict)
            constraint7 = optimizer.model.Add(room_conflict == False)
            
            optimizer.add_constraint(
                constraint_expr=constraint6,
                constraint_type=ConstraintType.ROOM_CONFLICT,
                origin_module=__name__,
                origin_function="_add_time_conflict_constraints",
                class_i=i,
                class_j=j,
                description=f"Room conflict detection: {c_i.subject} vs {c_j.subject}",
                variables_used=[str(room_conflict), str(same_room), str(conflict)]
            )
            
            optimizer.add_constraint(
                constraint_expr=constraint7,
                constraint_type=ConstraintType.ROOM_CONFLICT,
                origin_module=__name__,
                origin_function="_add_time_conflict_constraints",
                class_i=i,
                class_j=j,
                description=f"Forbid room conflicts: {c_i.subject} vs {c_j.subject}",
                variables_used=[str(room_conflict)]
            )
        
        print(f"  ✓ Added fixed time conflict constraints for classes {i} and {j}")
        return  # Только после добавления всех проверок для общих аудиторий

    # Изменение логики проверки временного перекрытия
    # Проверяем наличие пересечения времени или общих аудиторий
    time_overlaps = times_overlap(c_i, c_j, optimizer, i, j)
    if not time_overlaps and not shared_rooms:
        # Нет пересечения времени и нет общих аудиторий - можно пропустить проверку
        return
    
    # 0) Проверяем типы занятий через effective_bounds
    try:
        bounds_i = get_effective_bounds(optimizer, i, c_i)
        bounds_j = get_effective_bounds(optimizer, j, c_j)
        
        type_i = classify_bounds(bounds_i)
        type_j = classify_bounds(bounds_j)
        
        # Оба занятия с временными окнами
        if type_i == 'window' and type_j == 'window' and not must_add_constraints:
            # Дополнительно проверим день еще раз для уверенности
            if c_i.day != c_j.day:
                return
            
            # Если оба занятия оконные и имеют общие группы, всегда добавляем строгие ограничения
            shared_groups = set(c_i.get_groups()) & set(c_j.get_groups())
            if shared_groups:
                print(f"  [WINDOW-WINDOW] Adding mandatory constraints for window classes with shared groups: {i},{j}")
                add_sequential_constraints(optimizer, i, j, c_i, c_j)
                return

            # Попытаться посадить их подряд в общем окне
            if check_two_window_classes(optimizer, i, j, c_i, c_j):
                # Сначала проверяем общие аудитории
                if shared_rooms:
                    # Проверяем, есть ли альтернативные аудитории для хотя бы одного из занятий
                    has_alternatives_i = len(c_i.possible_rooms) > 1
                    has_alternatives_j = len(c_j.possible_rooms) > 1
                    
                    if has_alternatives_i or has_alternatives_j:
                        print(f"  [ROOM CONFLICT] Classes {i},{j} have shared rooms {shared_rooms}, but alternatives exist - adding room conflict constraints")
                        # Добавляем ограничения: если они в одной аудитории И в одно время, то конфликт
                        from resource_constraints import _add_room_conflict_constraints
                        _add_room_conflict_constraints(optimizer, i, j, c_i, c_j)
                        return
                    else:
                        print(f"  [CRITICAL] Adding mandatory constraints for classes with no room alternatives: {i},{j}")
                        add_sequential_constraints(optimizer, i, j, c_i, c_j)
                        return

                # НОВЫЙ КОД: Для занятий с общими группами всегда добавляем ограничения
                if shared_groups:
                    print(f"  [CRITICAL] Adding mandatory constraints for classes with shared groups: {i},{j}")
                    # Создаем временные ограничения и добавляем их
                    add_sequential_constraints(optimizer, i, j, c_i, c_j)
                    return
                
                # Не навязываем никаких конфликтных ограничений — solver сам расставит их в любом порядке
                print(f"  [window-window teacher] no-conflict via common window for classes {i},{j}")
                return
                
    except Exception as e:
        print(f"  Warning: Could not use effective bounds for classes {i},{j}: {e}")
        # Fallback к оригинальной логике
        if c_i.start_time and c_i.end_time and c_j.start_time and c_j.end_time and not must_add_constraints:
            print(f"  [FALLBACK] Using original logic for window classes {i},{j}")
            # Здесь можно добавить оригинальную логику если необходимо
            pass

    # ИСПРАВЛЕНО: Проверяем возможность последовательного размещения для любых конфликтующих ресурсов
    # Убираем ограничение только на общие группы - теперь обрабатываем любой общий ресурс
    if c_i.teacher == c_j.teacher and c_i.teacher:
        print(f"  Classes share teacher: {c_i.teacher}")
        
        # НОВОЕ: Всегда используем sequential_constraints для общего учителя
        # независимо от наличия общих групп
        add_sequential_constraints(optimizer, i, j, c_i, c_j)
        return
        
    # Дополнительная проверка для общих ресурсов (группы, кабинеты)
    shared_groups = set(c_i.get_groups()) & set(c_j.get_groups())
    if shared_groups:
        print(f"  Classes share groups: {shared_groups}")
        add_sequential_constraints(optimizer, i, j, c_i, c_j)
        return
        
    # Проверяем общие комнаты - тоже требуют последовательного размещения
    if shared_rooms:
        print(f"  Classes share rooms: {shared_rooms}")
        add_sequential_constraints(optimizer, i, j, c_i, c_j)
        return

    # Если нет общих ресурсов, ограничения не нужны
    print(f"  No shared resources detected - no constraints needed")
    return

def times_overlap(class1, class2, optimizer=None, idx1=None, idx2=None):
    """
    Проверяет, пересекаются ли занятия по времени.
    Использует effective_bounds для точного определения временных границ.
    """
    # Если занятия в разные дни — не могут пересекаться
    if class1.day != class2.day:
        return False
    
    # Пытаемся использовать effective_bounds если доступны optimizer и индексы
    if optimizer and idx1 is not None and idx2 is not None:
        try:
            bounds1 = get_effective_bounds(optimizer, idx1, class1)
            bounds2 = get_effective_bounds(optimizer, idx2, class2)
            
            # Если у занятия нет определенных временных границ, считаем пересекающимся
            if not bounds1.min_time or not bounds2.min_time:
                return True
                
            type1 = classify_bounds(bounds1)
            type2 = classify_bounds(bounds2)
            
            # Конвертируем в минуты для расчетов
            if type1 == 'fixed' and type2 == 'fixed':
                # Оба фиксированы
                start1 = time_to_minutes(bounds1.min_time)
                end1 = start1 + class1.duration
                start2 = time_to_minutes(bounds2.min_time)
                end2 = start2 + class2.duration
                return (start1 < end2) and (start2 < end1)
                
            elif type1 == 'window' and type2 == 'window':
                # Оба с временными окнами
                window1_start = time_to_minutes(bounds1.min_time)
                window1_end = time_to_minutes(bounds1.max_time)
                window2_start = time_to_minutes(bounds2.min_time)
                window2_end = time_to_minutes(bounds2.max_time)
                
                # Находим общее окно
                common_start = max(window1_start, window2_start)
                common_end = min(window1_end, window2_end)
                
                if common_end <= common_start:
                    # Нет общего времени вообще
                    return False
                    
                # Если есть общее окно, может быть конфликт
                return True
                
            elif type1 == 'fixed' and type2 == 'window':
                # Первое фиксировано, второе с окном
                fixed_start = time_to_minutes(bounds1.min_time)
                fixed_end = fixed_start + class1.duration
                window_start = time_to_minutes(bounds2.min_time)
                window_end = time_to_minutes(bounds2.max_time)
                
                return (fixed_start < window_end) and (window_start < fixed_end)
                
            elif type1 == 'window' and type2 == 'fixed':
                # Первое с окном, второе фиксировано
                window_start = time_to_minutes(bounds1.min_time)
                window_end = time_to_minutes(bounds1.max_time)
                fixed_start = time_to_minutes(bounds2.min_time)
                fixed_end = fixed_start + class2.duration
                
                return (fixed_start < window_end) and (window_start < fixed_end)
                
        except Exception as e:
            print(f"Warning: Could not use effective bounds in times_overlap: {e}")
            # Fallback к оригинальной логике
            pass
    
    # Fallback к оригинальной логике когда effective_bounds недоступны
    # Если у занятия нет времени начала, считаем пересекающимся
    if not class1.start_time or not class2.start_time:
        return True
        
    # Обрабатываем случай временных окон (когда есть end_time)
    if class1.start_time and class1.end_time and class2.start_time and class2.end_time:
        # Оба занятия с временными окнами
        window1_start = time_to_minutes(class1.start_time)
        window1_end = time_to_minutes(class1.end_time)
        window2_start = time_to_minutes(class2.start_time)
        window2_end = time_to_minutes(class2.end_time)
        
        # Находим общее окно
        common_start = max(window1_start, window2_start)
        common_end = min(window1_end, window2_end)
        
        if common_end <= common_start:
            # Нет общего времени вообще
            return False
            
        # Если есть общее окно, может быть конфликт
        return True
        
    # Случай, когда первое занятие имеет фиксированное время, а второе - временное окно
    elif class1.start_time and not class1.end_time and class2.start_time and class2.end_time:
        fixed_start = time_to_minutes(class1.start_time)
        fixed_end = fixed_start + class1.duration
        window_start = time_to_minutes(class2.start_time)
        window_end = time_to_minutes(class2.end_time)
        
        return (fixed_start < window_end) and (window_start < fixed_end)
        
    # Случай, когда второе занятие имеет фиксированное время, а первое - временное окно
    elif class2.start_time and not class2.end_time and class1.start_time and class1.end_time:
        fixed_start = time_to_minutes(class2.start_time)
        fixed_end = fixed_start + class2.duration
        window_start = time_to_minutes(class1.start_time)
        window_end = time_to_minutes(class1.end_time)
        
        return (fixed_start < window_end) and (window_start < fixed_end)
    
    # Оба занятия имеют фиксированное время
    else:
        start1 = time_to_minutes(class1.start_time)
        end1 = start1 + class1.duration
        start2 = time_to_minutes(class2.start_time)
        end2 = start2 + class2.duration
        return (start1 < end2) and (start2 < end1)