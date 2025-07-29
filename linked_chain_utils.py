"""
Утилиты для работы со связанными цепочками занятий.

Этот модуль содержит функции для анализа связанных цепочек занятий,
определения порядка в цепочках и работы с транзитивными связями.
"""

from timewindow_utils import are_classes_transitively_linked
from time_utils import time_to_minutes, minutes_to_time

__all__ = ['is_in_linked_chain', 'get_linked_chain_order', 'collect_full_chain', 'build_linked_chains',
           'find_chain_containing_classes', 'get_chain_window', 'are_classes_in_same_chain', 'pick_best_anchor',
           'clear_chain_windows_cache']

# Кеш для окон цепочек
_chain_windows_cache = {}


def build_linked_chains(optimizer):
    """
    Формирует список связанных цепочек занятий (индексы классов).
    
    Перенесено из linked_constraints.py для централизации утилит работы с цепочками.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
    """
    chains = []
    seen = set()

    for idx, c in enumerate(optimizer.classes):
        if hasattr(c, 'linked_classes') and c.linked_classes:
            chain = [idx]
            current = c
            while hasattr(current, 'linked_classes') and current.linked_classes:
                next_class = current.linked_classes[0]
                try:
                    next_idx = optimizer._find_class_index(next_class)
                    if next_idx in chain:
                        break
                    chain.append(next_idx)
                    current = next_class
                except Exception:
                    break
            chain_tuple = tuple(chain)
            if chain_tuple not in seen:
                chains.append(chain)
                seen.add(chain_tuple)

    optimizer.linked_chains = chains


def is_in_linked_chain(optimizer, idx):
    """
    Проверяет, принадлежит ли занятие с индексом idx к какой-либо связанной цепочке.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        idx: Индекс проверяемого занятия
        
    Returns:
        bool: True, если занятие принадлежит связанной цепочке
    """
    for chain in getattr(optimizer, "linked_chains", []):
        if idx in chain:
            return True
    return False


def get_linked_chain_order(root):
    """
    Return the full transitive order of class objects
    starting at *root*, following .linked_classes depth-first.
    
    Args:
        root: Корневой класс для обхода цепочки
        
    Returns:
        list: Список объектов классов в порядке от root до листовых потомков
    """
    # Используем внутреннюю функцию collect_full_chain вместо внешнего импорта
    return collect_full_chain(root)


def collect_full_chain(root):
    """
    Depth-first traversal of linked_classes, возвращает список
    занятий в порядке от root до самых «листовых» потомков.
    При этом у каждого класса устанавливаются:
      .previous = родитель (или None для root)
      .next_list = список прямых детей
    
    Args:
        root: Корневой класс для обхода цепочки
        
    Returns:
        list: Список классов в порядке от root до листовых потомков
    """
    result = []
    visited = set()
    
    def dfs(current_class, parent=None):
        """Рекурсивный обход в глубину"""
        if id(current_class) in visited:
            return  # Избегаем циклических ссылок
        
        visited.add(id(current_class))
        result.append(current_class)
        
        # Устанавливаем связь с родителем - это модификация структуры цепочки
        current_class.previous = parent
        
        # Инициализируем список детей
        current_class.next_list = []
        
        # Обходим всех связанных детей
        if hasattr(current_class, 'linked_classes') and current_class.linked_classes:
            for linked_class in current_class.linked_classes:
                current_class.next_list.append(linked_class)
                dfs(linked_class, current_class)
    
    # Начинаем обход с корневого класса
    dfs(root)
    
    return result


def find_chain_containing_classes(optimizer, idx1, idx2):
    """
    Проверяет, принадлежат ли два занятия одной цепочке.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        idx1, idx2: Индексы занятий
        
    Returns:
        list or None: Список индексов цепочки, если оба занятия в одной цепочке, иначе None
    """
    if not hasattr(optimizer, 'linked_chains'):
        return None
        
    for chain in optimizer.linked_chains:
        if idx1 in chain and idx2 in chain:
            return chain
    
    return None


def are_classes_in_same_chain(optimizer, idx1, idx2):
    """
    Проверяет, принадлежат ли два занятия одной цепочке.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        idx1, idx2: Индексы занятий
        
    Returns:
        bool: True, если занятия в одной цепочке
    """
    return find_chain_containing_classes(optimizer, idx1, idx2) is not None


def get_original_time_bounds(schedule_class):
    """
    Получает оригинальные временные границы занятия до применения chain constraints.
    
    Args:
        schedule_class: Экземпляр ScheduleClass
        
    Returns:
        tuple: (min_time_str, max_time_str) или (None, None) если нет временного окна
    """
    # Для фиксированного времени возвращаем только start_time
    if schedule_class.start_time and not schedule_class.end_time:
        return (schedule_class.start_time, schedule_class.start_time)
    
    # Для временного окна возвращаем start_time и end_time
    if schedule_class.start_time and schedule_class.end_time:
        return (schedule_class.start_time, schedule_class.end_time)
    
    # Нет временных ограничений
    return (None, None)


def get_chain_window(optimizer, chain_indices):
    """
    Вычисляет общее временное окно для цепочки занятий.
    Окно цепочки = пересечение оригинальных окон всех членов цепи.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        chain_indices: Список индексов занятий в цепочке
        
    Returns:
        dict: {'min_time': str, 'max_time': str, 'min_minutes': int, 'max_minutes': int} 
              или None если нет пересечения
    """
    global _chain_windows_cache
    
    # Создаем ключ для кеширования
    cache_key = tuple(sorted(chain_indices))
    if cache_key in _chain_windows_cache:
        return _chain_windows_cache[cache_key]
    
    min_times = []
    max_times = []
    
    for idx in chain_indices:
        schedule_class = optimizer.classes[idx]
        orig_min, orig_max = get_original_time_bounds(schedule_class)
        
        if orig_min is None or orig_max is None:
            # Если хотя бы одно занятие не имеет временного окна,
            # окно цепочки не может быть определено
            _chain_windows_cache[cache_key] = None
            return None
        
        min_times.append(time_to_minutes(orig_min))
        max_times.append(time_to_minutes(orig_max))
    
    # Окно цепочки = пересечение всех окон
    # min_chain = max(всех orig_min_time)
    # max_chain = min(всех orig_max_time)
    chain_min_minutes = max(min_times)
    chain_max_minutes = min(max_times)
    
    # Проверяем, что пересечение существует
    if chain_min_minutes >= chain_max_minutes:
        _chain_windows_cache[cache_key] = None
        return None
    
    result = {
        'min_time': minutes_to_time(chain_min_minutes),
        'max_time': minutes_to_time(chain_max_minutes),
        'min_minutes': chain_min_minutes,
        'max_minutes': chain_max_minutes
    }
    
    _chain_windows_cache[cache_key] = result
    return result


def pick_best_anchor(flex_class, chain_classes, direction="before", optimizer=None):
    """
    Выбирает лучший якорный урок в цепочке для размещения flex_class.
    
    Args:
        flex_class: Гибкое занятие, которое нужно разместить
        chain_classes: Список занятий в цепочке (объекты ScheduleClass)
        direction: Направление размещения ("before" или "after")
        optimizer: Экземпляр ScheduleOptimizer для получения эффективных границ
        
    Returns:
        ScheduleClass: Лучший якорный урок в цепочке
    """
    if not chain_classes:
        return None
    
    # Веса для оценки кандидатов
    w_T = 5    # Общий учитель
    w_G = 3    # Общие группы
    w_R = 1    # Общие кабинеты
    w_D = 0.1  # Время ожидания (1 балл штрафа за каждые 10 мин)
    
    best_anchor = None
    best_score = float('inf')
    
    print(f"\n=== SELECTING BEST ANCHOR ===")
    print(f"Flex class: {flex_class.subject} (teacher: {flex_class.teacher})")
    print(f"Chain has {len(chain_classes)} classes")
    print(f"Direction: {direction}")
    
    for anchor in chain_classes:
        # Вычисляем компоненты оценки
        
        # T: общий учитель (0 если есть, 1 если нет)
        T = 0 if (flex_class.teacher and anchor.teacher and 
                  flex_class.teacher == anchor.teacher) else 1
        
        # G: общие группы (0 если есть пересечение, 1 если нет)
        flex_groups = set(flex_class.get_groups()) if hasattr(flex_class, 'get_groups') else set()
        anchor_groups = set(anchor.get_groups()) if hasattr(anchor, 'get_groups') else set()
        shared_groups = flex_groups & anchor_groups
        G = 0 if shared_groups else 1
        
        # R: общие кабинеты (0 если есть пересечение, 1 если нет)
        flex_rooms = set(flex_class.possible_rooms) if flex_class.possible_rooms else set()
        anchor_rooms = set(anchor.possible_rooms) if anchor.possible_rooms else set()
        shared_rooms = flex_rooms & anchor_rooms
        R = 0 if shared_rooms else 1
        
        # D: время ожидания
        idle = 0
        if optimizer:
            try:
                from effective_bounds_utils import get_effective_bounds
                
                # Находим индексы занятий
                flex_idx = optimizer.classes.index(flex_class)
                anchor_idx = optimizer.classes.index(anchor)
                
                # Получаем эффективные границы
                flex_bounds = get_effective_bounds(optimizer, flex_idx, flex_class)
                anchor_bounds = get_effective_bounds(optimizer, anchor_idx, anchor)
                
                # Конвертируем в минуты
                if direction == "before":
                    # flex_class должен закончиться до начала anchor
                    flex_end = time_to_minutes(flex_bounds.max_time) + flex_class.duration
                    anchor_start = time_to_minutes(anchor_bounds.min_time)
                    pause_after_flex = getattr(flex_class, 'pause_after', 0)
                    idle = max(0, anchor_start - (flex_end + pause_after_flex))
                else:  # direction == "after"
                    # anchor должен закончиться до начала flex_class
                    anchor_end = time_to_minutes(anchor_bounds.max_time) + anchor.duration
                    flex_start = time_to_minutes(flex_bounds.min_time)
                    pause_after_anchor = getattr(anchor, 'pause_after', 0)
                    idle = max(0, flex_start - (anchor_end + pause_after_anchor))
                    
            except Exception as e:
                print(f"    Warning: Could not calculate idle time for anchor {anchor.subject}: {e}")
                idle = 0
        
        # Общая оценка (чем меньше, тем лучше)
        score = w_T * T + w_G * G + w_R * R + w_D * idle
        
        print(f"  Candidate: {anchor.subject}")
        print(f"    T={T} (teacher: {anchor.teacher}), G={G} (groups: {len(shared_groups)}), R={R} (rooms: {len(shared_rooms)}), idle={idle:.1f}min")
        print(f"    Score: {w_T}*{T} + {w_G}*{G} + {w_R}*{R} + {w_D:.1f}*{idle:.1f} = {score:.2f}")
        
        if score < best_score:
            best_score = score
            best_anchor = anchor
    
    print(f"  ✓ Best anchor: {best_anchor.subject if best_anchor else 'None'} (score: {best_score:.2f})")
    print("=" * 35)
    
    return best_anchor


def clear_chain_windows_cache():
    """Очищает кеш окон цепочек."""
    global _chain_windows_cache
    _chain_windows_cache = {}
    print("Chain windows cache cleared")
