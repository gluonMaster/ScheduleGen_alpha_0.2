"""
Модуль для анализа и группировки занятий по различным критериям.

Этот модуль предоставляет функциональность для группировки занятий по 
преподавателям, группам студентов и аудиториям, а также для разделения
на независимые группы по пересечению временных окон.
КРИТИЧЕСКОЕ РЕШЕНИЕ "ПРОБЛЕМЫ АННЫ" - разделение занятий преподавателя
на независимые группы вместо поиска общего временного окна.
"""

from time_utils import time_to_minutes, minutes_to_time
from timewindow_utils import build_transitive_links


class ClassGroup:
    """Класс для представления группы связанных занятий."""
    
    def __init__(self, group_type, group_key, day, classes_list):
        """
        Инициализирует группу занятий.
        
        Args:
            group_type: Тип группировки ('student_group', 'teacher', 'room')
            group_key: Ключ группы (имя группы, преподавателя или аудитории)
            day: День недели
            classes_list: Список кортежей (idx, class_obj)
        """
        self.group_type = group_type
        self.group_key = group_key
        self.day = day
        self.classes = classes_list
        
        # Разделение на фиксированные и оконные занятия
        self.fixed_classes = [(idx, c) for idx, c in classes_list if c.start_time and not c.end_time]
        self.window_classes = [(idx, c) for idx, c in classes_list if c.start_time and c.end_time]
        
        # Вычисляем общее временное окно для оконных занятий
        self.common_window_start = None
        self.common_window_end = None
        self._calculate_common_window()
    
    def _calculate_common_window(self):
        """Вычисляет общее временное окно для всех оконных занятий."""
        if not self.window_classes:
            return
        
        window_starts = [time_to_minutes(c.start_time) for _, c in self.window_classes]
        window_ends = [time_to_minutes(c.end_time) for _, c in self.window_classes]
        
        self.common_window_start = max(window_starts)
        self.common_window_end = min(window_ends)
    
    def has_valid_common_window(self):
        """Проверяет, является ли общее временное окно валидным."""
        if self.common_window_start is None or self.common_window_end is None:
            return False
        return self.common_window_end > self.common_window_start
    
    def get_total_required_time(self):
        """Возвращает общее требуемое время для всех занятий включая паузы."""
        if not self.window_classes:
            return 0
        
        total_duration = sum(c.duration for _, c in self.window_classes)
        # Учитываем паузы между занятиями
        if len(self.window_classes) > 1:
            total_pauses = sum(c.pause_after for _, c in self.window_classes[:-1]) + \
                          sum(c.pause_before for _, c in self.window_classes[1:])
        else:
            total_pauses = 0
        
        return total_duration + total_pauses
    
    def can_fit_in_common_window(self):
        """Проверяет, помещаются ли все занятия в общее временное окно."""
        if not self.has_valid_common_window():
            return False
        
        available_time = self.common_window_end - self.common_window_start
        required_time = self.get_total_required_time()
        
        return available_time >= required_time
    
    def get_debug_info(self):
        """Возвращает отладочную информацию о группе."""
        info = {
            'type': self.group_type,
            'key': self.group_key,
            'day': self.day,
            'total_classes': len(self.classes),
            'fixed_classes': len(self.fixed_classes),
            'window_classes': len(self.window_classes),
            'common_window': None,
            'can_fit': False,
            'classes_info': []
        }
        
        if self.has_valid_common_window():
            info['common_window'] = f"{minutes_to_time(self.common_window_start)}-{minutes_to_time(self.common_window_end)}"
            info['can_fit'] = self.can_fit_in_common_window()
        
        for idx, c in self.classes:
            class_info = {
                'idx': idx,
                'subject': getattr(c, 'subject', 'Unknown'),
                'type': 'fixed' if (c.start_time and not c.end_time) else 'window' if (c.start_time and c.end_time) else 'flexible'
            }
            
            if c.start_time:
                if c.end_time:
                    class_info['time'] = f"{c.start_time}-{c.end_time}"
                else:
                    class_info['time'] = c.start_time
            
            info['classes_info'].append(class_info)
        
        return info


def group_classes_by_criteria(optimizer):
    """
    Группирует занятия по различным критериям: группы студентов, преподаватели, аудитории.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        
    Returns:
        dict: Словарь с группами по критериям
            {
                'student_groups': {group_name: {day: ClassGroup}},
                'teachers': {teacher_name: {day: ClassGroup}},
                'rooms': {room_name: {day: ClassGroup}}
            }
    """
    print("Grouping classes by criteria...")
    
    # Словари для группировки
    student_groups = {}
    teachers = {}
    rooms = {}
    
    # Группировка по группам студентов
    for idx, c in enumerate(optimizer.classes):
        for group_name in c.get_groups():
            if group_name not in student_groups:
                student_groups[group_name] = {}
            
            if c.day not in student_groups[group_name]:
                student_groups[group_name][c.day] = []
            
            student_groups[group_name][c.day].append((idx, c))
    
    # Группировка по преподавателям
    for idx, c in enumerate(optimizer.classes):
        if c.teacher:
            if c.teacher not in teachers:
                teachers[c.teacher] = {}
            
            if c.day not in teachers[c.teacher]:
                teachers[c.teacher][c.day] = []
            
            teachers[c.teacher][c.day].append((idx, c))
    
    # Группировка по аудиториям
    for idx, c in enumerate(optimizer.classes):
        for room in c.possible_rooms:
            if room not in rooms:
                rooms[room] = {}
            
            if c.day not in rooms[room]:
                rooms[room][c.day] = []
            
            rooms[room][c.day].append((idx, c))
    
    # Создаем объекты ClassGroup
    result = {
        'student_groups': {},
        'teachers': {},
        'rooms': {}
    }
    
    for group_name, days_dict in student_groups.items():
        result['student_groups'][group_name] = {}
        for day, classes_list in days_dict.items():
            if len(classes_list) > 1:  # Только группы с несколькими занятиями
                result['student_groups'][group_name][day] = ClassGroup('student_group', group_name, day, classes_list)
    
    for teacher_name, days_dict in teachers.items():
        result['teachers'][teacher_name] = {}
        for day, classes_list in days_dict.items():
            if len(classes_list) > 1:  # Только группы с несколькими занятиями
                result['teachers'][teacher_name][day] = ClassGroup('teacher', teacher_name, day, classes_list)
    
    for room_name, days_dict in rooms.items():
        result['rooms'][room_name] = {}
        for day, classes_list in days_dict.items():
            if len(classes_list) > 1:  # Только группы с несколькими занятиями
                result['rooms'][room_name][day] = ClassGroup('room', room_name, day, classes_list)
    
    print(f"Found {len(result['student_groups'])} student groups, {len(result['teachers'])} teachers, {len(result['rooms'])} rooms with multiple classes")
    
    return result


def time_windows_overlap(c1, c2):
    """
    Проверяет, пересекаются ли временные окна двух занятий.
    
    Для фиксированных занятий проверяет пересечение времени выполнения.
    Для занятий с временными окнами проверяет пересечение окон.
    
    Args:
        c1, c2: Объекты занятий
        
    Returns:
        bool: True, если временные окна пересекаются
    """
    # Если у занятий нет времени, считаем их пересекающимися (они могут быть размещены в любое время)
    if not c1.start_time or not c2.start_time:
        return True
    
    # Определяем временные интервалы для каждого занятия
    start1 = time_to_minutes(c1.start_time)
    if c1.end_time:
        # Занятие с временным окном
        end1 = time_to_minutes(c1.end_time)
    else:
        # Фиксированное занятие - считаем время выполнения включая паузы
        pause_after_1 = getattr(c1, 'pause_after', 0)
        end1 = start1 + c1.duration + pause_after_1
    
    start2 = time_to_minutes(c2.start_time)
    if c2.end_time:
        # Занятие с временным окном
        end2 = time_to_minutes(c2.end_time)
    else:
        # Фиксированное занятие - считаем время выполнения включая паузы
        pause_after_2 = getattr(c2, 'pause_after', 0)
        end2 = start2 + c2.duration + pause_after_2
    
    # Проверяем пересечение интервалов
    overlap = start1 < end2 and start2 < end1
    
    # Отладочная информация
    if hasattr(c1, 'subject') and hasattr(c2, 'subject'):
        print(f"    Time overlap check: {c1.subject} [{minutes_to_time(start1)}-{minutes_to_time(end1)}] vs {c2.subject} [{minutes_to_time(start2)}-{minutes_to_time(end2)}] = {overlap}")
    
    return overlap


def find_independent_groups(class_group):
    """
    КЛЮЧЕВАЯ ФУНКЦИЯ для решения "проблемы Анны".
    Разделяет занятия на независимые группы по пересечению временных окон.
    
    Эта функция решает проблему, когда у преподавателя есть занятия в
    НЕПЕРЕСЕКАЮЩИХСЯ временных окнах (например, урок 15:00-15:55 и 
    цепочка уроков 16:00-19:45), которые должны обрабатываться отдельно.
    
    Args:
        class_group: Объект ClassGroup для анализа
        
    Returns:
        list: Список независимых ClassGroup объектов
    """
    print(f"Finding independent groups for {class_group.group_type} '{class_group.group_key}' on {class_group.day}")
    
    if class_group.group_type == 'student_group':
        # Для групп студентов включаем транзитивно связанные классы
        extended_classes = _include_transitive_links(class_group)
        print(f"  Extended from {len(class_group.classes)} to {len(extended_classes)} classes including transitive links")
    else:
        extended_classes = class_group.classes
        
        # Для преподавателей исключаем классы с общими группами студентов (уже обработаны)
        if class_group.group_type == 'teacher':
            extended_classes = _filter_shared_student_groups(extended_classes)
            print(f"  Filtered to {len(extended_classes)} classes without shared student groups")
    
    if len(extended_classes) < 2:
        print(f"  Not enough classes ({len(extended_classes)}) for independent grouping")
        return []
    
    # Алгоритм разделения на независимые группы по пересечению временных окон
    independent_groups = []
    
    for idx, c in extended_classes:
        # Ищем группу, с которой это занятие пересекается по времени
        found_group = False
        
        for group in independent_groups:
            for group_idx, group_c in group:
                if time_windows_overlap(c, group_c):
                    group.append((idx, c))
                    found_group = True
                    break
            if found_group:
                break
        
        # Если не нашли пересекающуюся группу, создаем новую
        if not found_group:
            independent_groups.append([(idx, c)])
    
    print(f"  Split into {len(independent_groups)} independent time groups:")
    
    # Создаем ClassGroup объекты для каждой независимой группы
    result_groups = []
    for group_idx, group_classes in enumerate(independent_groups):
        if len(group_classes) >= 2:  # Только группы с несколькими занятиями
            group_key = f"{class_group.group_key}_independent_{group_idx + 1}"
            independent_group = ClassGroup(class_group.group_type, group_key, class_group.day, group_classes)
            result_groups.append(independent_group)
            
            print(f"    Group {group_idx + 1}: {len(group_classes)} classes")
            for idx, c in group_classes:
                time_info = f"{c.start_time}"
                if c.end_time:
                    time_info += f"-{c.end_time}"
                print(f"      Class {idx}: {getattr(c, 'subject', 'Unknown')} {time_info}")
        else:
            print(f"    Group {group_idx + 1}: Only 1 class, skipping")
    
    return result_groups


def _include_transitive_links(class_group):
    """
    Включает транзитивно связанные классы в группу студентов.
    
    Args:
        class_group: Объект ClassGroup для расширения
        
    Returns:
        list: Расширенный список классов с транзитивными связями
    """
    # Для реализации нужен доступ к optimizer через глобальную переменную или параметр
    # В текущей версии возвращаем исходные классы
    # TODO: Интегрировать с build_transitive_links когда будет доступен optimizer
    extended_classes = list(class_group.classes)
    return extended_classes


def _filter_shared_student_groups(classes_list):
    """
    Фильтрует классы, исключая те, которые имеют общие группы студентов.
    
    Args:
        classes_list: Список кортежей (idx, class_obj)
        
    Returns:
        list: Отфильтрованный список классов
    """
    filtered_classes = []
    
    for i, (idx_i, c_i) in enumerate(classes_list):
        has_shared_group = False
        
        for j, (idx_j, c_j) in enumerate(classes_list):
            if i != j:
                shared_groups = set(c_i.get_groups()) & set(c_j.get_groups())
                if shared_groups:
                    has_shared_group = True
                    break
        
        if not has_shared_group:
            filtered_classes.append((idx_i, c_i))
    
    return filtered_classes


def analyze_group_constraints(optimizer, class_group):
    """
    Анализирует временные ограничения для группы занятий.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        class_group: Объект ClassGroup для анализа
        
    Returns:
        dict: Информация об ограничениях группы
    """
    constraints_info = {
        'group_info': class_group.get_debug_info(),
        'can_schedule_sequentially': False,
        'requires_separation_only': False,
        'linked_classes': [],
        'recommendations': []
    }
    
    # Проверяем возможность последовательного размещения
    if class_group.can_fit_in_common_window():
        constraints_info['can_schedule_sequentially'] = True
        constraints_info['recommendations'].append('Schedule sequentially in common window')
    else:
        constraints_info['requires_separation_only'] = True
        constraints_info['recommendations'].append('Use separation constraints only')
    
    # Анализируем связанные классы
    for idx, c in class_group.classes:
        if hasattr(c, 'linked_classes') and c.linked_classes:
            constraints_info['linked_classes'].append(idx)
    
    # Добавляем специфичные рекомендации
    if class_group.fixed_classes:
        constraints_info['recommendations'].append('Use fixed classes as anchors')
    
    if len(class_group.window_classes) == 1:
        constraints_info['recommendations'].append('Single window class - minimal constraints needed')
    
    return constraints_info


def get_grouping_debug_info(grouped_classes):
    """
    Возвращает отладочную информацию о результатах группировки.
    
    Args:
        grouped_classes: Результат функции group_classes_by_criteria
        
    Returns:
        str: Форматированная отладочная информация
    """
    lines = ["Class grouping analysis:"]
    
    for criteria_type, criteria_dict in grouped_classes.items():
        lines.append(f"\n{criteria_type.upper()}:")
        
        for key, days_dict in criteria_dict.items():
            lines.append(f"  {key}:")
            
            for day, class_group in days_dict.items():
                debug_info = class_group.get_debug_info()
                lines.append(f"    {day}: {debug_info['total_classes']} classes")
                lines.append(f"      Fixed: {debug_info['fixed_classes']}, Window: {debug_info['window_classes']}")
                
                if debug_info['common_window']:
                    lines.append(f"      Common window: {debug_info['common_window']}")
                    lines.append(f"      Can fit sequentially: {debug_info['can_fit']}")
                
                for class_info in debug_info['classes_info']:
                    time_str = class_info.get('time', 'flexible')
                    lines.append(f"        Class {class_info['idx']}: {class_info['subject']} ({time_str})")
    
    return "\n".join(lines)
