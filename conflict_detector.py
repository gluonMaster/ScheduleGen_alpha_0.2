"""
Модуль для обнаружения потенциальных конфликтов в расписании.
"""

from time_utils import time_to_minutes, minutes_to_time
from sequential_scheduling import can_schedule_sequentially

def check_potential_conflicts(optimizer):
    """Check for obvious conflicts before building the model."""
    print("\nChecking for potential scheduling conflicts...")
    
    # Для каждого преподавателя проверяем конфликты в одно и то же время
    teachers_classes = {}
    for idx, c in enumerate(optimizer.classes):
        if c.teacher:
            if c.teacher not in teachers_classes:
                teachers_classes[c.teacher] = []
            teachers_classes[c.teacher].append((idx, c))
    
    # Проверка конфликтов у преподавателей
    for teacher, classes in teachers_classes.items():
        # Группируем занятия по дням
        day_classes = {}
        for idx, c in classes:
            if c.day:
                if c.day not in day_classes:
                    day_classes[c.day] = []
                day_classes[c.day].append((idx, c))
        
        # Проверяем конфликты в каждый день
        for day, day_classes_list in day_classes.items():
            if len(day_classes_list) > 1:  # Если больше одного занятия в день
                # Проверяем пересечения по времени
                for i, (idx_i, c_i) in enumerate(day_classes_list):
                    # Для занятий с фиксированным временем начала
                    if c_i.start_time and not c_i.end_time:
                        start_i = time_to_minutes(c_i.start_time)
                        end_i = start_i + c_i.duration + c_i.pause_after
                        
                        for j, (idx_j, c_j) in enumerate(day_classes_list):
                            if i != j:  # Не сравниваем занятие с самим собой
                                # Если второе занятие тоже с фиксированным временем
                                if c_j.start_time and not c_j.end_time:
                                    start_j = time_to_minutes(c_j.start_time)
                                    end_j = start_j + c_j.duration + c_j.pause_after
                                    
                                    # Проверяем пересечение
                                    if (start_i < end_j and start_j < end_i):
                                        # Проверяем, не разные ли группы у этих занятий
                                        shared_groups = set(c_i.get_groups()) & set(c_j.get_groups())
                                        
                                        if shared_groups:
                                            print(f"\nCONFLICT DETECTED: Teacher {teacher} has overlapping classes with shared groups:")
                                            print(f"  Class {idx_i}: {c_i.subject} - {c_i.group} - {c_i.teacher} for groups {c_i.get_groups()} at {c_i.start_time} ({c_i.duration} min)")
                                            print(f"  Class {idx_j}: {c_j.subject} - {c_j.group} - {c_j.teacher} for groups {c_j.get_groups()} at {c_j.start_time} ({c_j.duration} min)")
                                            print(f"  Time ranges: {minutes_to_time(start_i)}-{minutes_to_time(end_i)} and {minutes_to_time(start_j)}-{minutes_to_time(end_j)}")
                                            print(f"  Shared groups: {shared_groups}")
                                            print(f"  These classes cannot be scheduled together with current constraints.")
                                        else:
                                            # Если группы разные, проверяем аудитории
                                            shared_rooms = set(c_i.possible_rooms) & set(c_j.possible_rooms)
                                            
                                            if shared_rooms and len(c_i.possible_rooms) == 1 and len(c_j.possible_rooms) == 1:
                                                print(f"\nCONFLICT DETECTED: Teacher {teacher} has overlapping classes in the same fixed room:")
                                                print(f"  Class {idx_i}: {c_i.subject} - {c_i.group} - {c_i.teacher} for groups {c_i.get_groups()} at {c_i.start_time} ({c_i.duration} min)")
                                                print(f"  Class {idx_j}: {c_j.subject} - {c_j.group} - {c_j.teacher} for groups {c_j.get_groups()} at {c_j.start_time} ({c_j.duration} min)")
                                                print(f"  Both classes are fixed to room(s): {shared_rooms}")
                                                print(f"  Time ranges: {minutes_to_time(start_i)}-{minutes_to_time(end_i)} and {minutes_to_time(start_j)}-{minutes_to_time(end_j)}")
                                            else:
                                                print(f"\nNOTE: Teacher {teacher} has overlapping classes but with different groups and different rooms possible:")
                                                print(f"  Class {idx_i}: {c_i.subject} - {c_i.group} - {c_i.teacher} for groups {c_i.get_groups()} at {c_i.start_time} ({c_i.duration} min)")
                                                print(f"  Class {idx_j}: {c_j.subject} - {c_j.group} - {c_j.teacher} for groups {c_j.get_groups()} at {c_j.start_time} ({c_j.duration} min)")
                                                print(f"  Class {idx_i} rooms: {c_i.possible_rooms}")
                                                print(f"  Class {idx_j} rooms: {c_j.possible_rooms}")
                                                print(f"  This may be intentional (teacher teaching multiple groups in different rooms).")
                                
                                # Если второе занятие с временным окном
                                elif c_j.start_time and c_j.end_time:
                                    # Проверяем, можно ли разместить оба занятия без конфликта
                                    shared_groups = set(c_i.get_groups()) & set(c_j.get_groups())
                                    
                                    if shared_groups:
                                        print(f"\nWARNING: Teacher {teacher} has fixed class and window class with shared groups:")
                                        print(f"  Fixed class {idx_i}: {c_i.subject} - {c_i.group} - {c_i.teacher} for groups {c_i.get_groups()} at {c_i.start_time} ({c_i.duration} min)")
                                        print(f"  Window class {idx_j}: {c_j.subject} - {c_j.group} - {c_j.teacher} for groups {c_j.get_groups()} with window {c_j.start_time}-{c_j.end_time} ({c_j.duration} min)")
                                        print(f"  Shared groups: {shared_groups}")
                                        print(f"  These classes must not overlap due to shared groups: {shared_groups}")
                                    else:
                                        # Используем функцию can_schedule_sequentially для правильной проверки
                                        can_schedule, info = can_schedule_sequentially(c_i, c_j, idx_i, idx_j, verbose=True)
                                        
                                        # New logging for chain & resource gap
                                        if info.get("reason") == "chain_and_resource_gap":
                                            start1, end1 = info["c1_interval"]
                                            start2, end2 = info["c2_interval"]
                                            gap = info["gap"]
                                            print(f"SEQUENTIAL via chain & resource-gap: "
                                                  f"{c_i.subject} {start1//60:02d}:{start1%60:02d}-{end1//60:02d}:{end1%60:02d}, "
                                                  f"{c_j.subject} {start2//60:02d}:{start2%60:02d}-{end2//60:02d}:{end2%60:02d} "
                                                  f"(gap {gap} min)")
                                        
                                        shared_rooms = set(c_i.possible_rooms) & set(c_j.possible_rooms)
                                        
                                        if shared_rooms and len(c_i.possible_rooms) == 1 and len(c_j.possible_rooms) == 1:
                                            if can_schedule:
                                                print(f"\nSEQUENTIAL SCHEDULING: Teacher {teacher} can schedule both classes in shared room:")
                                                print(f"  Fixed class {idx_i}: {c_i.subject} - {c_i.group} - {c_i.teacher} at {c_i.start_time} ({c_i.duration} min)")
                                                print(f"  Window class {idx_j}: {c_j.subject} - {c_j.group} - {c_j.teacher} with window {c_j.start_time}-{c_j.end_time} ({c_j.duration} min)")
                                                print(f"  Shared room: {shared_rooms}")
                                                print(f"  Scheduling reason: {info['reason']}")
                                            else:
                                                print(f"\nPOTENTIAL CONFLICT: Teacher {teacher} may not have enough time for both classes in the same fixed room:")
                                                print(f"  Fixed class {idx_i}: {c_i.subject} - {c_i.group} - {c_i.teacher} at {c_i.start_time} ({c_i.duration} min)")
                                                print(f"  Window class {idx_j}: {c_j.subject} - {c_j.group} - {c_j.teacher} with window {c_j.start_time}-{c_j.end_time} ({c_j.duration} min)")
                                                print(f"  Shared room: {shared_rooms}")
                                                print(f"  Conflict reason: {info['reason']}")
                                                if info.get('available_time') is not None and info.get('required_time') is not None:
                                                    print(f"  Available time: {info['available_time']}")
                                                    print(f"  Required time: {info['required_time']}")
                                                print(f"  WARNING: There is not enough time to schedule both classes!")
                                        else:
                                            print(f"\nINFO: Teacher {teacher} has fixed class and window class with different groups and room options:")
                                            print(f"  Fixed class {idx_i}: {c_i.subject} - {c_i.group} - {c_i.teacher} at {c_i.start_time} ({c_i.duration} min)")
                                            print(f"  Window class {idx_j}: {c_j.subject} - {c_j.group} - {c_j.teacher} with window {c_j.start_time}-{c_j.end_time} ({c_j.duration} min)")
                                            print(f"  Class {idx_i} rooms: {c_i.possible_rooms}")
                                            print(f"  Class {idx_j} rooms: {c_j.possible_rooms}")
                                            print(f"  These can be scheduled in parallel with different rooms.")
    
    # Проверка конфликтов аудиторий
    print("\nChecking for room conflicts...")
    room_classes = {}
    for idx, c in enumerate(optimizer.classes):
        for room in c.possible_rooms:
            if room not in room_classes:
                room_classes[room] = []
            room_classes[room].append((idx, c))

    # Проверка конфликтов для каждой аудитории
    for room, classes in room_classes.items():
        # Группировка занятий по дням
        day_classes = {}
        for idx, c in classes:
            if c.day:
                if c.day not in day_classes:
                    day_classes[c.day] = []
                day_classes[c.day].append((idx, c))
        
        # Проверяем конфликты в каждый день
        for day, day_classes_list in day_classes.items():
            if len(day_classes_list) > 1:  # Если больше одного занятия в день в этой аудитории
                # Сортируем по фиксированному времени начала
                fixed_classes = [(idx, c) for idx, c in day_classes_list if c.start_time and not c.end_time]
                window_classes = [(idx, c) for idx, c in day_classes_list if c.start_time and c.end_time]
                
                # Проверяем конфликты между фиксированными занятиями
                for i, (idx_i, c_i) in enumerate(fixed_classes):
                    start_i = time_to_minutes(c_i.start_time)
                    end_i = start_i + c_i.duration + c_i.pause_after
                    
                    for j, (idx_j, c_j) in enumerate(fixed_classes[i+1:], i+1):
                        start_j = time_to_minutes(c_j.start_time)
                        end_j = start_j + c_j.duration + c_j.pause_after
                        
                        # Проверяем пересечение
                        if (start_i < end_j and start_j < end_i):
                            print(f"\nCONFLICT DETECTED: Room {room} has overlapping fixed classes:")
                            print(f"  Class {idx_i}: {c_i.subject} - {c_i.group} - {c_i.teacher} at {c_i.start_time} ({c_i.duration} min)")
                            print(f"  Class {idx_j}: {c_j.subject} - {c_j.group} - {c_j.teacher} at {c_j.start_time} ({c_j.duration} min)")
                            print(f"  Time ranges: {minutes_to_time(start_i)}-{minutes_to_time(end_i)} and {minutes_to_time(start_j)}-{minutes_to_time(end_j)}")
                            print(f"  These classes cannot be scheduled together in the same room.")
                
                # Проверяем совместимость фиксированных занятий с занятиями с временным окном
                for idx_i, c_i in fixed_classes:
                    for idx_j, c_j in window_classes:
                        # Используем функцию can_schedule_sequentially для правильной проверки
                        can_schedule, info = can_schedule_sequentially(c_i, c_j, idx_i, idx_j, verbose=True)
                        
                        # New logging for chain & resource gap
                        if info.get("reason") == "chain_and_resource_gap":
                            start1, end1 = info["c1_interval"]
                            start2, end2 = info["c2_interval"]
                            gap = info["gap"]
                            print(f"SEQUENTIAL via chain & resource-gap: "
                                  f"{c_i.subject} {start1//60:02d}:{start1%60:02d}-{end1//60:02d}:{end1%60:02d}, "
                                  f"{c_j.subject} {start2//60:02d}:{start2%60:02d}-{end2//60:02d}:{end2%60:02d} "
                                  f"(gap {gap} min)")
                        
                        if can_schedule:
                            print(f"\nSEQUENTIAL SCHEDULING: Room {room} can fit window class with fixed class:")
                            print(f"  Fixed class {idx_i}: {c_i.subject} - {c_i.group} - {c_i.teacher} at {c_i.start_time} ({c_i.duration} min)")
                            print(f"  Window class {idx_j}: {c_j.subject} - {c_j.group} - {c_j.teacher} with window {c_j.start_time}-{c_j.end_time} ({c_j.duration} min)")
                            print(f"  Scheduling reason: {info['reason']}")
                            if info.get('available_time') is not None and info.get('required_time') is not None:
                                print(f"  Available time: {info['available_time']}")
                                print(f"  Required time: {info['required_time']}")
                        else:
                            # Проверяем обратный порядок (window -> fixed)
                            can_schedule_rev, info_rev = can_schedule_sequentially(c_j, c_i, idx_j, idx_i, verbose=True)
                            
                            # New logging for chain & resource gap (reverse order)
                            if info_rev.get("reason") == "chain_and_resource_gap":
                                start1, end1 = info_rev["c1_interval"]
                                start2, end2 = info_rev["c2_interval"]
                                gap = info_rev["gap"]
                                print(f"SEQUENTIAL via chain & resource-gap (reverse): "
                                      f"{c_j.subject} {start1//60:02d}:{start1%60:02d}-{end1//60:02d}:{end1%60:02d}, "
                                      f"{c_i.subject} {start2//60:02d}:{start2%60:02d}-{end2//60:02d}:{end2%60:02d} "
                                      f"(gap {gap} min)")
                            
                            if can_schedule_rev:
                                print(f"\nSEQUENTIAL SCHEDULING (REVERSE ORDER): Room {room} can fit window before fixed class:")
                                print(f"  Window class {idx_j}: {c_j.subject} - {c_j.group} - {c_j.teacher} with window {c_j.start_time}-{c_j.end_time} ({c_j.duration} min)")
                                print(f"  Fixed class {idx_i}: {c_i.subject} - {c_i.group} - {c_i.teacher} at {c_i.start_time} ({c_i.duration} min)")
                                print(f"  Scheduling reason: {info_rev['reason']}")
                                if info_rev.get('available_time') is not None and info_rev.get('required_time') is not None:
                                    print(f"  Available time: {info_rev['available_time']} min, Required time: {info_rev['required_time']} min")
                            else:
                                print(f"\nPOTENTIAL CONFLICT: Room {room} - cannot fit window class around fixed class in either order:")
                                print(f"  Fixed class {idx_i}: {c_i.subject} - {c_i.group} - {c_i.teacher} at {c_i.start_time} ({c_i.duration} min)")
                                print(f"  Window class {idx_j}: {c_j.subject} - {c_j.group} - {c_j.teacher} with window {c_j.start_time}-{c_j.end_time} ({c_j.duration} min)")
                                print(f"  Fixed->Window conflict: {info['reason']}")
                                if info.get('available_time') is not None and info.get('required_time') is not None:
                                    print(f"  Available time (fixed->window): {info['available_time']}")
                                    print(f"  Required time: {info['required_time']}")
                                print(f"  Window->Fixed conflict: {info_rev['reason']}")
                                if info_rev.get('available_time') is not None and info_rev.get('required_time') is not None:
                                    print(f"  Available time (window->fixed): {info_rev['available_time']}")
                                    print(f"  Required time: {info_rev['required_time']}")
                                print(f"  No sufficient time slot found for sequential scheduling")
                
                # Проверяем совместимость занятий с временным окном между собой
                for i, (idx_i, c_i) in enumerate(window_classes):
                    for j, (idx_j, c_j) in enumerate(window_classes[i+1:], i+1):
                        # Используем функцию can_schedule_sequentially для правильной проверки
                        can_schedule, info = can_schedule_sequentially(c_i, c_j, idx_i, idx_j, verbose=True)
                        
                        if can_schedule:
                            print(f"\nSEQUENTIAL SCHEDULING: Room {room} can fit both window classes sequentially:")
                            print(f"  Class {idx_i}: {c_i.subject} - {c_i.group} - {c_i.teacher} with window {c_i.start_time}-{c_i.end_time} ({c_i.duration} min)")
                            print(f"  Class {idx_j}: {c_j.subject} - {c_j.group} - {c_j.teacher} with window {c_j.start_time}-{c_j.end_time} ({c_j.duration} min)")
                            print(f"  Scheduling reason: {info['reason']}")
                            if info.get('common_window'):
                                print(f"  Common window: {info['common_window']}")
                            if info.get('available_time') is not None and info.get('required_time') is not None:
                                print(f"  Available time: {info['available_time']}")
                                print(f"  Required time: {info['required_time']}")
                        else:
                            # Проверяем, нужно ли попробовать обратный порядок для неперекрывающихся окон
                            if info.get('reason') == 'windows_separate_wrong_order':
                                print(f"\nCHECKING REVERSE ORDER: Trying {c_j.subject} before {c_i.subject}...")
                                can_schedule_rev, info_rev = can_schedule_sequentially(c_j, c_i, idx_j, idx_i, verbose=True)
                                
                                if can_schedule_rev:
                                    print(f"\nSEQUENTIAL SCHEDULING (REVERSE ORDER): Room {room} can fit both window classes:")
                                    print(f"  Class {idx_j}: {c_j.subject} - {c_j.group} - {c_j.teacher} with window {c_j.start_time}-{c_j.end_time} ({c_j.duration} min)")
                                    print(f"  Class {idx_i}: {c_i.subject} - {c_i.group} - {c_i.teacher} with window {c_i.start_time}-{c_i.end_time} ({c_i.duration} min)")
                                    print(f"  Scheduling reason: {info_rev['reason']}")
                                    if info_rev.get('available_time') is not None and info_rev.get('required_time') is not None:
                                        print(f"  Available time: {info_rev['available_time']}")
                                        print(f"  Required time: {info_rev['required_time']}")
                                else:
                                    print(f"\nPOTENTIAL CONFLICT: Room {room} - classes cannot be scheduled sequentially in either order:")
                                    print(f"  Class {idx_i}: {c_i.subject} - {c_i.group} - {c_i.teacher} with window {c_i.start_time}-{c_i.end_time} ({c_i.duration} min)")
                                    print(f"  Class {idx_j}: {c_j.subject} - {c_j.group} - {c_j.teacher} with window {c_j.start_time}-{c_j.end_time} ({c_j.duration} min)")
                                    print(f"  Forward order conflict: {info['reason']}")
                                    if info.get('available_time') is not None:
                                        print(f"  Available time: {info['available_time']}")
                                        print(f"  Required time: {info.get('required_time', 'N/A')}")
                                    print(f"  Reverse order conflict: {info_rev['reason']}")
                                    if info_rev.get('available_time') is not None:
                                        print(f"  Available time (reverse): {info_rev['available_time']}")
                                        print(f"  Required time: {info_rev.get('required_time', 'N/A')}")
                                    print(f"  WARNING: These classes cannot be scheduled together in this room!")
                            else:
                                print(f"\nPOTENTIAL CONFLICT: Room {room} - classes cannot be scheduled sequentially:")
                                print(f"  Class {idx_i}: {c_i.subject} - {c_i.group} - {c_i.teacher} with window {c_i.start_time}-{c_i.end_time} ({c_i.duration} min)")
                                print(f"  Class {idx_j}: {c_j.subject} - {c_j.group} - {c_j.teacher} with window {c_j.start_time}-{c_j.end_time} ({c_j.duration} min)")
                                print(f"  Conflict reason: {info['reason']}")
                                if info.get('common_window'):
                                    print(f"  Common window: {info['common_window']}")
                                if info.get('available_time') is not None and info.get('required_time') is not None:
                                    print(f"  Available time: {info['available_time']}")
                                    print(f"  Required time: {info['required_time']}")
                                print(f"  WARNING: These classes cannot be scheduled together in this room!")
    
    print("\nConflict check completed.")


def detect_constraint_cycles(optimizer):
    """
    Обнаруживает циклические зависимости между ограничениями цепочек и преподавателей.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        
    Returns:
        list: Список обнаруженных циклов
    """
    print("\nDetecting constraint cycles...")
    
    # Строим граф зависимостей между классами
    dependency_graph = {}
    
    # Добавляем зависимости от цепочек
    for idx, c in enumerate(optimizer.classes):
        dependency_graph[idx] = set()
        
        # Проверяем связанные классы (цепочки)
        if hasattr(c, 'linked_to') and c.linked_to:
            for linked_info in c.linked_to:
                if isinstance(linked_info, dict) and 'class' in linked_info:
                    linked_class = linked_info['class']
                    # Найдем индекс связанного класса
                    for j, other_c in enumerate(optimizer.classes):
                        if other_c == linked_class:
                            dependency_graph[idx].add(j)
                            break
    
    # Добавляем зависимости от преподавателей (для классов одного преподавателя в один день)
    teacher_classes = {}
    for idx, c in enumerate(optimizer.classes):
        if c.teacher and c.day:
            key = (c.teacher, c.day)
            if key not in teacher_classes:
                teacher_classes[key] = []
            teacher_classes[key].append(idx)
    
    # Для каждого преподавателя в каждый день добавляем взаимные зависимости
    for teacher_day, class_indices in teacher_classes.items():
        if len(class_indices) > 1:
            for i in class_indices:
                for j in class_indices:
                    if i != j:
                        dependency_graph[i].add(j)
    
    # Обнаруживаем циклы с помощью DFS
    visited = set()
    rec_stack = set()
    cycles = []
    
    def dfs(node, path):
        if node in rec_stack:
            # Найден цикл
            cycle_start = path.index(node)
            cycle = path[cycle_start:] + [node]
            cycles.append(cycle)
            return True
        
        if node in visited:
            return False
        
        visited.add(node)
        rec_stack.add(node)
        path.append(node)
        
        for neighbor in dependency_graph[node]:
            if dfs(neighbor, path):
                pass  # Цикл уже найден и добавлен
        
        rec_stack.remove(node)
        path.pop()
        return False
    
    # Запускаем DFS для всех узлов
    for idx in range(len(optimizer.classes)):
        if idx not in visited:
            dfs(idx, [])
    
    # Логируем результаты
    if cycles:
        print(f"WARNING: Detected {len(cycles)} constraint cycles:")
        for i, cycle in enumerate(cycles):
            print(f"  Cycle {i+1}: {' -> '.join(map(str, cycle))}")
            
            # Детальная информация о цикле
            for j in range(len(cycle) - 1):
                idx1, idx2 = cycle[j], cycle[j+1]
                c1, c2 = optimizer.classes[idx1], optimizer.classes[idx2]
                
                # Проверяем тип связи
                if hasattr(c1, 'linked_to') and c1.linked_to:
                    for linked_info in c1.linked_to:
                        if isinstance(linked_info, dict) and 'class' in linked_info:
                            if linked_info['class'] == c2:
                                print(f"    {idx1} -> {idx2}: Chain constraint ({c1.subject} -> {c2.subject})")
                                break
                elif c1.teacher == c2.teacher and c1.day == c2.day:
                    print(f"    {idx1} -> {idx2}: Teacher constraint (same teacher {c1.teacher} on {c1.day})")
    else:
        print("No constraint cycles detected.")
    
    return cycles


def prevent_constraint_cycles(optimizer, cycles):
    """
    Предотвращает циклические зависимости путем модификации ограничений.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        cycles: Список обнаруженных циклов
    """
    if not cycles:
        return
    
    print(f"\nPreventing {len(cycles)} constraint cycles...")
    
    for i, cycle in enumerate(cycles):
        print(f"  Processing cycle {i+1}: {' -> '.join(map(str, cycle))}")
        
        # Стратегия: разорвать цикл, удалив наименее критичное ограничение
        # Приоритет: цепочки важнее ограничений преподавателя
        
        weakest_link = None
        weakest_score = float('inf')
        
        for j in range(len(cycle) - 1):
            idx1, idx2 = cycle[j], cycle[j+1]
            c1, c2 = optimizer.classes[idx1], optimizer.classes[idx2]
            
            # Оценка критичности связи
            score = 0
            
            # Проверяем, является ли это цепочечной связью
            is_chain_link = False
            if hasattr(c1, 'linked_to') and c1.linked_to:
                for linked_info in c1.linked_to:
                    if isinstance(linked_info, dict) and 'class' in linked_info:
                        if linked_info['class'] == c2:
                            is_chain_link = True
                            score += 10  # Цепочки более критичны
                            break
            
            # Проверяем, является ли это ограничением преподавателя
            if c1.teacher == c2.teacher and c1.day == c2.day:
                score += 5  # Ограничения преподавателя менее критичны
            
            # Учитываем фиксированное время
            if c1.start_time and not c1.end_time:
                score += 3  # Фиксированное время повышает критичность
            if c2.start_time and not c2.end_time:
                score += 3
            
            if score < weakest_score:
                weakest_score = score
                weakest_link = (idx1, idx2)
        
        if weakest_link:
            idx1, idx2 = weakest_link
            print(f"    Breaking weakest link: {idx1} -> {idx2} (score: {weakest_score})")
            
            # Помечаем эту связь как исключение
            if not hasattr(optimizer, 'constraint_exceptions'):
                optimizer.constraint_exceptions = set()
            optimizer.constraint_exceptions.add((idx1, idx2))
            optimizer.constraint_exceptions.add((idx2, idx1))  # Для симметрии
            
            print(f"    Added constraint exception for classes {idx1} and {idx2}")
    