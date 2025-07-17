"""
Утилиты для работы со связанными цепочками занятий.

Этот модуль содержит функции для анализа связанных цепочек занятий,
определения порядка в цепочках и работы с транзитивными связями.
"""

from timewindow_utils import are_classes_transitively_linked

__all__ = ['is_in_linked_chain', 'get_linked_chain_order', 'collect_full_chain']


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
