"""
Модуль для добавления ограничений ресурсов (преподаватели, аудитории, группы).
"""

from conflict_detector import check_potential_conflicts
from time_conflict_constraints import _add_time_conflict_constraints
from time_utils import time_to_minutes, minutes_to_time 

def times_overlap(c1, c2):
    """Проверяет пересечение по времени двух занятий."""
    if not c1.start_time or not c2.start_time:
        # Одно из занятий не имеет фиксированного времени — считаем пересекающимся
        return True
    start1 = time_to_minutes(c1.start_time)
    end1 = start1 + c1.duration
    start2 = time_to_minutes(c2.start_time)
    end2 = start2 + c2.duration
    return (start1 < end2) and (start2 < end1)


def can_schedule_sequentially(c_i, c_j):
    """
    Проверяет, могут ли два занятия быть запланированы последовательно.
    
    Args:
        c_i: Первое занятие (ScheduleClass)
        c_j: Второе занятие (ScheduleClass)
        
    Returns:
        bool: True, если занятия могут быть запланированы последовательно, иначе False
    """
    # Проверка наличия общего дня
    if c_i.day != c_j.day:
        return False
    
    # Проверка временных окон
    if c_i.start_time and not c_i.end_time and c_j.start_time and c_j.end_time:
        # c_i фиксировано, c_j с окном
        fixed_start = time_to_minutes(c_i.start_time)
        fixed_end = fixed_start + c_i.duration + c_i.pause_after
        window_start = time_to_minutes(c_j.start_time)
        window_end = time_to_minutes(c_j.end_time)
        
        # Вариант: Окно после фиксированного времени
        if window_end - fixed_end >= c_j.duration + c_j.pause_before:
            return True
            
        # Вариант: Окно перед фиксированным временем
        window_class_end = window_start + c_j.duration + c_j.pause_after
        if fixed_start - window_class_end >= c_i.pause_before:
            return True
            
        return False
        
    elif c_j.start_time and not c_j.end_time and c_i.start_time and c_i.end_time:
        # c_j фиксировано, c_i с окном
        fixed_start = time_to_minutes(c_j.start_time)
        fixed_end = fixed_start + c_j.duration + c_j.pause_after
        window_start = time_to_minutes(c_i.start_time)
        window_end = time_to_minutes(c_i.end_time)
        
        # Вариант: Окно после фиксированного времени
        if window_end - fixed_end >= c_i.duration + c_i.pause_before:
            return True
            
        # Вариант: Окно перед фиксированным временем
        window_class_end = window_start + c_i.duration + c_i.pause_after
        if fixed_start - window_class_end >= c_j.pause_before:
            return True
            
        return False
        
    elif c_i.start_time and c_i.end_time and c_j.start_time and c_j.end_time:
        # Оба занятия с временными окнами
        window_i_start = time_to_minutes(c_i.start_time)
        window_i_end = time_to_minutes(c_i.end_time)
        window_j_start = time_to_minutes(c_j.start_time)
        window_j_end = time_to_minutes(c_j.end_time)
        
        # Проверяем общее временное окно
        common_start = max(window_i_start, window_j_start)
        common_end = min(window_i_end, window_j_end)
        common_duration = common_end - common_start
        
        # Суммарное время, нужное для обоих занятий
        total_duration = c_i.duration + c_i.pause_after + c_j.pause_before + c_j.duration
        
        return common_duration >= total_duration
        
    elif c_i.start_time and not c_i.end_time and c_j.start_time and not c_j.end_time:
        # Оба занятия с фиксированным временем
        start_i = time_to_minutes(c_i.start_time)
        end_i = start_i + c_i.duration + c_i.pause_after
        start_j = time_to_minutes(c_j.start_time)
        end_j = start_j + c_j.duration + c_j.pause_after
        
        # Проверяем перекрытие времени
        return not (start_i < end_j and start_j < end_i)
    
    # По умолчанию, если нет временных ограничений
    return True

def add_resource_conflict_constraints(optimizer):
    """Add constraints to prevent conflicts in resources (teachers, rooms, groups)."""
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
    for i in range(num_classes):
        c_i = optimizer.classes[i]
        
        for j in range(i + 1, num_classes):
            c_j = optimizer.classes[j]

            # Пропускаем сравнение, если занятия в разные дни
            if c_i.day != c_j.day:
                continue

            # ВАЖНОЕ ИЗМЕНЕНИЕ: Всегда проверяем возможные конфликты по комнатам,
            # даже если у классов разные учителя и группы
            shared_rooms = set(c_i.possible_rooms) & set(c_j.possible_rooms)
            if shared_rooms:
                print(f"Checking room conflict between classes {i} and {j} in rooms {shared_rooms}")
                # Добавляем ограничения, чтобы предотвратить конфликты по времени в одной комнате
                _add_time_conflict_constraints(optimizer, i, j, c_i, c_j)
                continue  # Продолжаем со следующей парой классов

            # Пропускаем сравнение, если занятия не пересекаются по времени
            if not times_overlap(c_i, c_j):
                continue
            
            # Skip if classes are linked (already handled)
            if hasattr(c_i, 'linked_classes') and c_j in c_i.linked_classes:
                continue
            if hasattr(c_j, 'linked_classes') and c_i in c_j.linked_classes:
                continue
            
            # Skip if one class is the previous_class of the other
            if (hasattr(c_i, 'previous_class') and hasattr(c_j, 'subject') and c_i.previous_class == c_j.subject) or \
            (hasattr(c_j, 'previous_class') and hasattr(c_i, 'subject') and c_j.previous_class == c_i.subject):
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
                    if not can_schedule_sequentially(c_i, c_j):
                        # Если последовательное планирование невозможно, отмечаем конфликт
                        resource_conflict = True
                        conflict_description.append(f"teacher '{c_i.teacher}' with different groups (cannot schedule sequentially)")
            
            # Проверка конфликта аудитории
            shared_rooms = set(c_i.possible_rooms) & set(c_j.possible_rooms)
            if shared_rooms:
                # Проверяем возможность последовательного размещения
                if not can_schedule_sequentially(c_i, c_j):
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
            optimizer.model.Add(same_room == 1)
        else:
            optimizer.model.Add(same_room == 0)
    elif isinstance(optimizer.room_vars[i], int):
        # Только занятие i имеет фиксированную аудиторию
        optimizer.model.Add(optimizer.room_vars[j] == optimizer.room_vars[i]).OnlyEnforceIf(same_room)
        optimizer.model.Add(optimizer.room_vars[j] != optimizer.room_vars[i]).OnlyEnforceIf(same_room.Not())
    elif isinstance(optimizer.room_vars[j], int):
        # Только занятие j имеет фиксированную аудиторию
        optimizer.model.Add(optimizer.room_vars[i] == optimizer.room_vars[j]).OnlyEnforceIf(same_room)
        optimizer.model.Add(optimizer.room_vars[i] != optimizer.room_vars[j]).OnlyEnforceIf(same_room.Not())
    else:
        # Оба занятия имеют переменные аудитории
        optimizer.model.Add(optimizer.room_vars[i] == optimizer.room_vars[j]).OnlyEnforceIf(same_room)
        optimizer.model.Add(optimizer.room_vars[i] != optimizer.room_vars[j]).OnlyEnforceIf(same_room.Not())
    
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
    optimizer.model.Add(room_conflict == False)
    
    print(f"  Added room conflict constraints between classes {i} and {j}")