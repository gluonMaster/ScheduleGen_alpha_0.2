"""
Вспомогательные утилиты для работы с цепочками занятий.

Этот модуль содержит улучшенные функции для сборки полных цепочек
из любого звена и управления кешем окон цепочек.
"""

__all__ = ['collect_full_chain_from_any_member', 'invalidate_chain_window', 'find_chain_root']


def find_chain_root(schedule_class):
    """
    Находит корневой элемент цепочки, поднимаясь по previous_class.
    
    Args:
        schedule_class: Любой элемент цепочки
        
    Returns:
        ScheduleClass: Корневой элемент цепочки (у которого нет previous_class)
    """
    current = schedule_class
    visited = set()
    
    # Поднимаемся по цепочке до корня
    while hasattr(current, 'previous_class') and current.previous_class:
        # Защита от циклических ссылок
        if id(current) in visited:
            print(f"Warning: Circular reference detected in chain at {current.subject}")
            break
        
        visited.add(id(current))
        current = current.previous_class
    
    return current


def _collect_full_chain_internal(root):
    """
    Внутренняя функция для сборки полной цепочки без циклических импортов.
    """
    result = []
    visited = set()
    
    def dfs(current_class, parent=None):
        """Рекурсивный обход в глубину"""
        if id(current_class) in visited:
            return  # Избегаем циклических ссылок
        
        visited.add(id(current_class))
        result.append(current_class)
        
        # Устанавливаем связь с родителем
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


def collect_full_chain_from_any_member(schedule_class):
    """
    Собирает полную цепочку занятий, начиная с любого элемента цепочки.
    
    Сначала поднимается до корня через previous_class,
    затем использует стандартную функцию collect_full_chain для полного обхода.
    
    Args:
        schedule_class: Любой элемент цепочки
        
    Returns:
        list: Полная цепочка занятий в правильном порядке от корня до листьев
    """
    # Находим корень цепочки
    root = find_chain_root(schedule_class)
    
    # Используем внутреннюю функцию для сборки полной цепочки от корня
    # Сначала пытаемся использовать функцию из linked_chain_utils
    try:
        from linked_chain_utils import collect_full_chain
        return collect_full_chain(root)
    except ImportError:
        # Fallback к внутренней реализации
        return _collect_full_chain_internal(root)


def invalidate_chain_window(schedule_class):
    """
    Инвалидирует кеш окна цепочки для цепочки, содержащей данное занятие.
    
    Args:
        schedule_class: Любой элемент цепочки, окно которой нужно пересчитать
    """
    # Импортируем функции для работы с кешем окон
    try:
        from linked_chain_utils import _chain_windows_cache
        
        # Получаем полную цепочку для определения всех индексов
        try:
            full_chain = collect_full_chain_from_any_member(schedule_class)
            
            # Если удается найти optimizer, то инвалидируем только конкретную цепочку
            # Пока что используем простую стратегию - попробуем найти глобальный optimizer
            import sys
            optimizer = None
            for name, obj in sys.modules.items():
                if hasattr(obj, '__dict__'):
                    for attr_name, attr_value in obj.__dict__.items():
                        if hasattr(attr_value, 'classes') and hasattr(attr_value, '_chain_windows_cache'):
                            # Нашли optimizer-подобный объект
                            optimizer = attr_value
                            break
                    if optimizer:
                        break
            
            if optimizer:
                # Пытаемся найти индексы для точечной инвалидации
                try:
                    chain_indices = []
                    for class_obj in full_chain:
                        idx = optimizer.classes.index(class_obj)
                        chain_indices.append(idx)
                    
                    # Инвалидируем только этот ключ кеша
                    cache_key = tuple(sorted(chain_indices))
                    if cache_key in _chain_windows_cache:
                        del _chain_windows_cache[cache_key]
                        print(f"Invalidated specific chain window cache for {len(chain_indices)} classes: {[c.subject for c in full_chain]}")
                        return
                        
                except (ValueError, AttributeError):
                    pass  # Fallback к полной очистке
        
        except Exception:
            pass  # Fallback к полной очистке
        
        # Fallback: полная очистка кеша
        from linked_chain_utils import clear_chain_windows_cache
        clear_chain_windows_cache()
        print(f"Chain window cache invalidated for class: {schedule_class.subject} (full cache clear)")
        
    except ImportError:
        print("Warning: Could not import chain window cache functions")


def invalidate_chain_windows_by_indices(optimizer, chain_indices):
    """
    Инвалидирует кеш окна для конкретной цепочки по индексам.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        chain_indices: Список индексов занятий в цепочке
    """
    try:
        from linked_chain_utils import _chain_windows_cache
        
        # Создаем ключ для кеширования
        cache_key = tuple(sorted(chain_indices))
        
        # Удаляем из кеша если присутствует
        if cache_key in _chain_windows_cache:
            del _chain_windows_cache[cache_key]
            print(f"Invalidated chain window cache for indices: {chain_indices}")
        
    except ImportError:
        print("Warning: Could not access chain window cache")


def get_chain_members_from_any(schedule_class):
    """
    Получает всех членов цепочки из любого элемента.
    
    Args:
        schedule_class: Любой элемент цепочки
        
    Returns:
        list: Список всех занятий в цепочке
    """
    return collect_full_chain_from_any_member(schedule_class)


def is_member_of_same_chain(class1, class2):
    """
    Проверяет, принадлежат ли два занятия одной цепочке.
    
    Args:
        class1, class2: Объекты занятий для проверки
        
    Returns:
        bool: True, если занятия принадлежат одной цепочке
    """
    # Получаем полные цепочки для обоих занятий
    chain1 = collect_full_chain_from_any_member(class1)
    chain2 = collect_full_chain_from_any_member(class2)
    
    # Проверяем, есть ли пересечение между цепочками
    chain1_ids = {id(c) for c in chain1}
    chain2_ids = {id(c) for c in chain2}
    
    return bool(chain1_ids & chain2_ids)


def validate_chain_integrity(schedule_class, verbose=False):
    """
    Проверяет целостность цепочки (отсутствие циклов, корректность связей).
    
    Args:
        schedule_class: Любой элемент цепочки для проверки
        verbose: Включить детальное логгирование
        
    Returns:
        dict: Результат проверки с деталями
    """
    result = {
        'is_valid': True,
        'errors': [],
        'warnings': [],
        'chain_length': 0,
        'root_class': None
    }
    
    try:
        # Собираем полную цепочку
        full_chain = collect_full_chain_from_any_member(schedule_class)
        result['chain_length'] = len(full_chain)
        
        if full_chain:
            result['root_class'] = full_chain[0]
            
            # Проверяем связи между элементами
            for i in range(len(full_chain) - 1):
                current = full_chain[i]
                next_class = full_chain[i + 1]
                
                # Проверяем прямую связь
                if not (hasattr(current, 'linked_classes') and 
                        current.linked_classes and 
                        next_class in current.linked_classes):
                    result['errors'].append(
                        f"Missing forward link: {current.subject} -> {next_class.subject}"
                    )
                    result['is_valid'] = False
                
                # Проверяем обратную связь
                if not (hasattr(next_class, 'previous_class') and 
                        next_class.previous_class == current):
                    result['errors'].append(
                        f"Missing backward link: {next_class.subject} <- {current.subject}"
                    )
                    result['is_valid'] = False
        
        if verbose:
            print(f"Chain validation for {schedule_class.subject}:")
            print(f"  Valid: {result['is_valid']}")
            print(f"  Length: {result['chain_length']}")
            if result['errors']:
                print(f"  Errors: {result['errors']}")
            if result['warnings']:
                print(f"  Warnings: {result['warnings']}")
                
    except Exception as e:
        result['is_valid'] = False
        result['errors'].append(f"Validation exception: {str(e)}")
        
        if verbose:
            print(f"Chain validation failed for {schedule_class.subject}: {e}")
    
    return result
