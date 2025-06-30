"""
Модуль для добавления ограничений по времени и предотвращения конфликтов.
"""
from time_utils import time_to_minutes, minutes_to_time
from time_constraint_utils import create_conflict_variables, add_time_overlap_constraints
from sequential_scheduling_checker import _check_sequential_scheduling, check_two_window_classes
#from timewindow_adapter import find_slot_for_time
from sequential_scheduling import can_schedule_sequentially

def add_sequential_constraints(optimizer, i, j, c_i, c_j):
    """
    Добавляет строгие ограничения для последовательного размещения занятий
    """
    # Создаем булеву переменную для определения порядка занятий
    i_before_j = optimizer.model.NewBoolVar(f"seq_strict_{i}_{j}")
    
    # Расчет длительности в слотах времени
    duration_i_slots = c_i.duration // optimizer.time_interval
    duration_j_slots = c_j.duration // optimizer.time_interval
    
    # Переменные для конца занятий
    end_i = optimizer.model.NewIntVar(0, len(optimizer.time_slots), f"seq_end_{i}")
    end_j = optimizer.model.NewIntVar(0, len(optimizer.time_slots), f"seq_end_{j}")
    
    # Устанавливаем значения концов занятий
    optimizer.model.Add(end_i == optimizer.start_vars[i] + duration_i_slots)
    optimizer.model.Add(end_j == optimizer.start_vars[j] + duration_j_slots)
    
    # Минимальный интервал между занятиями - с исправленным округлением вверх
    min_pause = (c_i.pause_after + c_j.pause_before + optimizer.time_interval - 1) // optimizer.time_interval
    
    # Строгое ограничение: i перед j или j перед i, без перекрытия
    optimizer.model.Add(end_i + min_pause <= optimizer.start_vars[j]).OnlyEnforceIf(i_before_j)
    optimizer.model.Add(end_j + min_pause <= optimizer.start_vars[i]).OnlyEnforceIf(i_before_j.Not())
    
    print(f"  Added STRICT sequential constraints between classes {i} and {j} with min pause {min_pause} slots")

def _add_time_conflict_constraints(optimizer, i, j, c_i, c_j):
    """
    Добавляет ограничения для предотвращения конфликтов времени между занятиями.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        i, j: Индексы классов
        c_i, c_j: Экземпляры ScheduleClass
    """
    # Проверка: если занятия в разные дни — не анализируем конфликт
    if c_i.day != c_j.day:
        return
    
    # Проверяем наличие общих аудиторий и групп
    shared_rooms = set(c_i.possible_rooms) & set(c_j.possible_rooms)
    shared_groups = set(c_i.get_groups()) & set(c_j.get_groups())

    # Флаг для обязательного добавления ограничений при общих группах
    must_add_constraints = (shared_groups and c_i.day == c_j.day) or (shared_rooms and c_i.day == c_j.day)
    
    # Если оба занятия имеют фиксированное время начала
    if c_i.fixed_start_time and c_j.fixed_start_time:
        # Оба занятия фиксированные - проверяем реальное пересечение
        conflict, same_day, time_overlap = create_conflict_variables(optimizer, i, j, c_i, c_j)
        add_time_overlap_constraints(optimizer, i, j, c_i, c_j, time_overlap)
        
        # Правильная логика определения конфликта
        optimizer.model.AddBoolAnd([same_day, time_overlap]).OnlyEnforceIf(conflict)
        optimizer.model.AddBoolOr([same_day.Not(), time_overlap.Not()]).OnlyEnforceIf(conflict.Not())
        
        # Запрещаем конфликты
        optimizer.model.Add(conflict == False)
        
        # Проверяем конфликты аудиторий, даже для фиксированного времени
        if shared_rooms:
            # Добавляем проверку конфликтов с общими аудиториями
            same_room = optimizer.model.NewBoolVar(f"same_room_{i}_{j}")
            if isinstance(optimizer.room_vars[i], int) and isinstance(optimizer.room_vars[j], int):
                if optimizer.room_vars[i] == optimizer.room_vars[j]:
                    optimizer.model.Add(same_room == 1)
                else:
                    optimizer.model.Add(same_room == 0)
            elif isinstance(optimizer.room_vars[i], int):
                optimizer.model.Add(optimizer.room_vars[j] == optimizer.room_vars[i]).OnlyEnforceIf(same_room)
                optimizer.model.Add(optimizer.room_vars[j] != optimizer.room_vars[i]).OnlyEnforceIf(same_room.Not())
            elif isinstance(optimizer.room_vars[j], int):
                optimizer.model.Add(optimizer.room_vars[i] == optimizer.room_vars[j]).OnlyEnforceIf(same_room)
                optimizer.model.Add(optimizer.room_vars[i] != optimizer.room_vars[j]).OnlyEnforceIf(same_room.Not())
            else:
                optimizer.model.Add(optimizer.room_vars[i] == optimizer.room_vars[j]).OnlyEnforceIf(same_room)
                optimizer.model.Add(optimizer.room_vars[i] != optimizer.room_vars[j]).OnlyEnforceIf(same_room.Not())
            
            # Если одна и та же аудитория, проверяем конфликты
            room_conflict = optimizer.model.NewBoolVar(f"room_conflict_{i}_{j}")
            optimizer.model.AddBoolAnd([same_room, conflict]).OnlyEnforceIf(room_conflict)
            optimizer.model.Add(room_conflict == False)
        
        return  # Только после добавления всех проверок для общих аудиторий

    # Изменение логики проверки временного перекрытия
    # Проверяем наличие пересечения времени или общих аудиторий
    time_overlaps = times_overlap(c_i, c_j)
    if not time_overlaps and not shared_rooms:
        # Нет пересечения времени и нет общих аудиторий - можно пропустить проверку
        return
    
    # 0) Спец.-случай: оба занятия имеют временные окна → проверяем check_two_window_classes
    if c_i.start_time and c_i.end_time and c_j.start_time and c_j.end_time and not must_add_constraints:
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
    # Проверяем возможность последовательного размещения для занятий одного преподавателя
    if c_i.teacher == c_j.teacher and c_i.teacher:
        # Проверяем наличие общих групп
        shared_groups = set(c_i.get_groups()) & set(c_j.get_groups())
        
        # Для занятий с общими группами проверяем ОБА варианта размещения
        if shared_groups:
            # Прямой порядок (c_i, затем c_j)
            can_seq_i_j, info_i_j = can_schedule_sequentially(c_i, c_j)
            
            # Обратный порядок (c_j, затем c_i)
            can_seq_j_i, info_j_i = can_schedule_sequentially(c_j, c_i)
            
            # Проверяем случай, когда одно занятие фиксированное, а другое оконное
            # Если фиксированное c_i и оконное c_j
            if c_i.start_time and not c_i.end_time and c_j.start_time and c_j.end_time:
                if can_seq_i_j and info_i_j['reason'] == 'fits_before_fixed':
                    # c_j можно разместить ДО c_i - предпочитаем этот вариант
                    fixed_start = time_to_minutes(c_i.start_time)
                    latest_end = fixed_start - c_i.pause_before
                    latest_start = latest_end - c_j.duration
                    latest_slot_idx = optimizer._get_time_slot_index(minutes_to_time(latest_start))
                    
                    print(f"  [shared_groups] PRIORITIZING window class {j} BEFORE fixed class {i}")
                    optimizer.model.Add(optimizer.start_vars[j] <= latest_slot_idx)
                    return
                elif can_seq_i_j and info_i_j['reason'] == 'fits_after_fixed':
                    # c_j можно разместить ПОСЛЕ c_i
                    fixed_start = time_to_minutes(c_i.start_time)
                    fixed_end = fixed_start + c_i.duration + c_i.pause_after
                    
                    earliest_start = fixed_end + c_j.pause_before
                    earliest_slot = optimizer._get_time_slot_index(minutes_to_time(earliest_start))
                    
                    # Проверяем, хватает ли времени для размещения ПОСЛЕ
                    window_end = time_to_minutes(c_j.end_time)
                    if (window_end - earliest_slot * optimizer.time_interval) >= c_j.duration:
                        print(f"  [shared_groups] Applying AFTER-fixed for class {j}")
                        optimizer.model.Add(optimizer.start_vars[j] >= earliest_slot)
                    else:
                        print(f"  [WARNING] Not enough time to schedule {j} after {i}, but forcing BEFORE-fixed")
                        # Принудительно размещаем ДО, даже если первоначально это не было обнаружено
                        latest_end = fixed_start - c_i.pause_before
                        latest_start = latest_end - c_j.duration
                        latest_slot_idx = optimizer._get_time_slot_index(minutes_to_time(latest_start))
                        optimizer.model.Add(optimizer.start_vars[j] <= latest_slot_idx)
                    return
                
            # Если фиксированное c_j и оконное c_i
            elif c_j.start_time and not c_j.end_time and c_i.start_time and c_i.end_time:
                if can_seq_j_i and info_j_i['reason'] == 'fits_before_fixed':
                    # c_i можно разместить ДО c_j - предпочитаем этот вариант
                    fixed_start = time_to_minutes(c_j.start_time)
                    latest_end = fixed_start - c_j.pause_before
                    latest_start = latest_end - c_i.duration
                    latest_slot_idx = optimizer._get_time_slot_index(minutes_to_time(latest_start))
                    
                    print(f"  [shared_groups] PRIORITIZING window class {i} BEFORE fixed class {j}")
                    optimizer.model.Add(optimizer.start_vars[i] <= latest_slot_idx)
                    return
                elif can_seq_j_i and info_j_i['reason'] == 'fits_after_fixed':
                    # c_i можно разместить ПОСЛЕ c_j
                    fixed_start = time_to_minutes(c_j.start_time)
                    fixed_end = fixed_start + c_j.duration + c_j.pause_after
                    
                    earliest_start = fixed_end + c_i.pause_before
                    earliest_slot = optimizer._get_time_slot_index(minutes_to_time(earliest_start))
                    
                    # Проверяем, хватает ли времени для размещения ПОСЛЕ
                    window_end = time_to_minutes(c_i.end_time)
                    if (window_end - earliest_slot * optimizer.time_interval) >= c_i.duration:
                        print(f"  [shared_groups] Applying AFTER-fixed for class {i}")
                        optimizer.model.Add(optimizer.start_vars[i] >= earliest_slot)
                    else:
                        print(f"  [WARNING] Not enough time to schedule {i} after {j}, but forcing BEFORE-fixed")
                        # Принудительно размещаем ДО, даже если первоначально это не было обнаружено
                        latest_end = fixed_start - c_j.pause_before
                        latest_start = latest_end - c_i.duration
                        latest_slot_idx = optimizer._get_time_slot_index(minutes_to_time(latest_start))
                        optimizer.model.Add(optimizer.start_vars[i] <= latest_slot_idx)
                    return
                
            # Оба занятия с временными окнами или оба фиксированные
            # Стандартная обработка
        
        # Продолжаем с существующей логикой для случаев без общих групп
        # или если не удалось применить особую обработку выше
        can_seq, info = can_schedule_sequentially(c_i, c_j)

        # Если can_seq==False, fall through к стандартному конфликтному блоку
        
        # now re-run scheduling check in reverse order
        can_seq_rev, info_rev = can_schedule_sequentially(c_j, c_i)
        if can_seq_rev:
            # fits_before_fixed для reversed: значит c_i нужно «до»
            if info_rev['reason'] == 'fits_before_fixed':
                fixed_start = time_to_minutes(c_j.start_time)
                latest_end  = fixed_start - c_i.pause_before
                latest_start = latest_end - c_i.duration
                slot_idx = optimizer._get_time_slot_index(minutes_to_time(latest_start))

                print(f"  [shared_groups] Applying BEFORE-fixed (reversed) for class {i}")
                optimizer.model.Add(optimizer.start_vars[i] <= slot_idx)
                return

            # fits_after_fixed для reversed: c_i «после»
            elif info_rev['reason'] == 'fits_after_fixed':
                fixed_start = time_to_minutes(c_j.start_time)
                fixed_end   = fixed_start + c_j.duration + c_j.pause_after

                earliest_start = fixed_end + c_i.pause_before
                slot_idx = optimizer._get_time_slot_index(minutes_to_time(earliest_start))

                print(f"  [shared_groups] Applying AFTER-fixed (reversed) for class {i}")
                optimizer.model.Add(optimizer.start_vars[i] >= slot_idx)
                return

            else:  # both_orders_possible — НИЧЕГО
                print(f"  [shared_groups] both_orders_possible (reversed) — leaving free")
                return
    
    # 0-2) Оба занятия в одной комнате и оба с окнами → проверяем альтернативы
    if set(c_i.possible_rooms) & set(c_j.possible_rooms):
        if c_i.start_time and c_i.end_time and c_j.start_time and c_j.end_time:
            if check_two_window_classes(optimizer, i, j, c_i, c_j):
                # Проверяем, есть ли альтернативные аудитории
                has_alternatives_i = len(c_i.possible_rooms) > 1
                has_alternatives_j = len(c_j.possible_rooms) > 1
                
                if has_alternatives_i or has_alternatives_j:
                    print(f"  [window-window room] Classes {i},{j} have room alternatives - adding room conflict constraints")
                    from resource_constraints import _add_room_conflict_constraints
                    _add_room_conflict_constraints(optimizer, i, j, c_i, c_j)
                    return
                else:
                    print(f"  [window-window room] Adding sequential constraints for shared room classes {i},{j}")
                    add_sequential_constraints(optimizer, i, j, c_i, c_j)
                    return
    # Если ни один вариант не возможен
    print(f"  Sequential scheduling not possible for these time windows")
    
    # Стандартная обработка конфликтов (для случаев, когда последовательное размещение невозможно)
    print(f"Adding standard conflict constraints between classes {i} and {j}")
    
    # Создаем переменные для конфликта
    conflict, same_day, time_overlap = create_conflict_variables(optimizer, i, j, c_i, c_j)
    
    # Добавляем ограничения для определения перекрытия времени
    add_time_overlap_constraints(optimizer, i, j, c_i, c_j, time_overlap)
    
    # Conflict if same day and time overlap
    optimizer.model.AddBoolAnd([same_day, time_overlap]).OnlyEnforceIf(conflict)
    optimizer.model.AddBoolOr([same_day.Not(), time_overlap.Not()]).OnlyEnforceIf(conflict.Not())
    
    # Prevent conflicts
    optimizer.model.Add(conflict == False)
    
    # Check for room conflicts (only for classes with variable room assignment)
    shared_rooms = set(c_i.possible_rooms) & set(c_j.possible_rooms)
    if shared_rooms:
        # Add constraints to ensure different rooms if conflict potential exists
        same_room = optimizer.model.NewBoolVar(f"same_room_{i}_{j}")
        if isinstance(optimizer.room_vars[i], int) and isinstance(optimizer.room_vars[j], int):
            # Проверяем равенство комнат и устанавливаем значение переменной same_room
            if optimizer.room_vars[i] == optimizer.room_vars[j]:
                optimizer.model.Add(same_room == 1)
            else:
                optimizer.model.Add(same_room == 0)
        elif isinstance(optimizer.room_vars[i], int):
            optimizer.model.Add(optimizer.room_vars[j] == optimizer.room_vars[i]).OnlyEnforceIf(same_room)
            optimizer.model.Add(optimizer.room_vars[j] != optimizer.room_vars[i]).OnlyEnforceIf(same_room.Not())
        elif isinstance(optimizer.room_vars[j], int):
            optimizer.model.Add(optimizer.room_vars[i] == optimizer.room_vars[j]).OnlyEnforceIf(same_room)
            optimizer.model.Add(optimizer.room_vars[i] != optimizer.room_vars[j]).OnlyEnforceIf(same_room.Not())
        else:
            optimizer.model.Add(optimizer.room_vars[i] == optimizer.room_vars[j]).OnlyEnforceIf(same_room)
            optimizer.model.Add(optimizer.room_vars[i] != optimizer.room_vars[j]).OnlyEnforceIf(same_room.Not())
        
        # If same room, check for conflicts
        room_conflict = optimizer.model.NewBoolVar(f"room_conflict_{i}_{j}")
        optimizer.model.AddBoolAnd([same_room, conflict]).OnlyEnforceIf(room_conflict)
        optimizer.model.Add(room_conflict == False)

def times_overlap(class1, class2):
    """
    Проверяет, пересекаются ли занятия по времени.
    Учитывает фиксированное время и временные окна.
    """
    # Если занятия в разные дни — не могут пересекаться
    if class1.day != class2.day:
        return False
    
    # Если у занятия нет времени начала, считаем пересекающимся
    if not class1.start_time or not class2.start_time:
        return True
        
    # Обрабатываем случай временных окон (когда есть end_time)
    if class1.start_time and class1.end_time and class2.start_time and class2.end_time:
        # Оба занятия с временными окнами
        # Проверяем, может ли быть конфликт при неподходящем назначении времени
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
            
        # Если общее окно меньше суммы длительностей, возможен конфликт
        total_duration = class1.duration + class2.duration
        if common_end - common_start < total_duration:
            return True
            
        # Здесь важное отличие: даже если общее окно больше суммы длительностей,
        # мы всё равно возвращаем True, если нас интересует возможность конфликта
        # Но в этом случае конфликт может быть разрешен с помощью правильного планирования
        return True
        
    # Случай, когда первое занятие имеет фиксированное время, а второе - временное окно
    elif class1.start_time and not class1.end_time and class2.start_time and class2.end_time:
        fixed_start = time_to_minutes(class1.start_time)
        fixed_end = fixed_start + class1.duration
        window_start = time_to_minutes(class2.start_time)
        window_end = time_to_minutes(class2.end_time)
        
        # Проверяем, может ли быть конфликт
        return (fixed_start < window_end) and (window_start < fixed_end)
        
    # Случай, когда второе занятие имеет фиксированное время, а первое - временное окно
    elif class2.start_time and not class2.end_time and class1.start_time and class1.end_time:
        fixed_start = time_to_minutes(class2.start_time)
        fixed_end = fixed_start + class2.duration
        window_start = time_to_minutes(class1.start_time)
        window_end = time_to_minutes(class1.end_time)
        
        # Проверяем, может ли быть конфликт
        return (fixed_start < window_end) and (window_start < fixed_end)
    
    # Оба занятия имеют фиксированное время
    else:
        start1 = time_to_minutes(class1.start_time)
        end1 = start1 + class1.duration
        start2 = time_to_minutes(class2.start_time)
        end2 = start2 + class2.duration
        return (start1 < end2) and (start2 < end1)