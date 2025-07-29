"""
Утилиты для работы с эффективными границами временных окон занятий.

Этот модуль предоставляет централизованную систему хранения и извлечения
актуальных границ начала занятий после применения всех ограничений.
"""

from time_utils import time_to_minutes, minutes_to_time
from typing import Dict, Optional, Tuple, Any


class EffectiveBounds:
    """
    Класс для хранения эффективных границ временного окна занятия.
    """
    
    def __init__(self, min_slot: int, max_slot: int, min_time: str, max_time: str,
                 source: str = "unknown", confidence: str = "high"):
        """
        Инициализирует эффективные границы.
        
        Args:
            min_slot: Минимальный слот времени
            max_slot: Максимальный слот времени  
            min_time: Минимальное время в формате HH:MM
            max_time: Максимальное время в формате HH:MM
            source: Источник определения границ
            confidence: Уровень уверенности в границах
        """
        self.min_slot = min_slot
        self.max_slot = max_slot
        self.min_time = min_time
        self.max_time = max_time
        self.source = source
        self.confidence = confidence
        self.applied_constraints = []  # Список примененных ограничений
        
    def add_constraint_info(self, constraint_type: str, description: str):
        """Добавляет информацию о примененном ограничении."""
        self.applied_constraints.append({
            'type': constraint_type,
            'description': description
        })
    
    def to_dict(self) -> Dict[str, Any]:
        """Возвращает словарное представление границ."""
        return {
            'min_slot': self.min_slot,
            'max_slot': self.max_slot,
            'min_time': self.min_time,
            'max_time': self.max_time,
            'source': self.source,
            'confidence': self.confidence,
            'applied_constraints': self.applied_constraints
        }
    
    def __repr__(self):
        return f"EffectiveBounds(slot: {self.min_slot}-{self.max_slot}, time: {self.min_time}-{self.max_time}, source: {self.source})"


def initialize_effective_bounds(optimizer):
    """
    Инициализирует систему эффективных границ в оптимизаторе.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
    """
    if not hasattr(optimizer, 'effective_bounds'):
        optimizer.effective_bounds = {}
        print("Initialized effective_bounds system")
    
    if not hasattr(optimizer, 'bounds_metadata'):
        optimizer.bounds_metadata = {
            'last_updated': None,
            'update_count': 0,
            'sources': set()
        }


def set_effective_bounds(optimizer, class_idx: int, min_slot: int, max_slot: int,
                        source: str = "constraint", description: str = ""):
    """
    Устанавливает эффективные границы для класса.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        class_idx: Индекс класса
        min_slot: Минимальный слот времени
        max_slot: Максимальный слот времени
        source: Источник определения границ
        description: Описание ограничения
    """
    initialize_effective_bounds(optimizer)
    
    # Конвертируем слоты в время
    min_time = slot_to_time(optimizer, min_slot)
    max_time = slot_to_time(optimizer, max_slot)
    
    # Создаем или обновляем границы
    if class_idx in optimizer.effective_bounds:
        bounds = optimizer.effective_bounds[class_idx]
        # Сужаем границы, если новые более строгие
        bounds.min_slot = max(bounds.min_slot, min_slot)
        bounds.max_slot = min(bounds.max_slot, max_slot)
        bounds.min_time = slot_to_time(optimizer, bounds.min_slot)
        bounds.max_time = slot_to_time(optimizer, bounds.max_slot)
        bounds.add_constraint_info(source, description)
        print(f"  Updated effective bounds for class {class_idx}: {bounds}")
    else:
        bounds = EffectiveBounds(min_slot, max_slot, min_time, max_time, source)
        if description:
            bounds.add_constraint_info(source, description)
        optimizer.effective_bounds[class_idx] = bounds
        print(f"  Set effective bounds for class {class_idx}: {bounds}")
    
    # Обновляем метаданные
    optimizer.bounds_metadata['update_count'] += 1
    optimizer.bounds_metadata['sources'].add(source)
    from datetime import datetime
    optimizer.bounds_metadata['last_updated'] = datetime.now()


def get_effective_bounds(optimizer, class_idx: int, class_obj=None) -> EffectiveBounds:
    """
    Получает эффективные границы для класса с fallback механизмом.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        class_idx: Индекс класса
        class_obj: Объект класса (для fallback)
        
    Returns:
        EffectiveBounds: Эффективные границы класса
    """
    initialize_effective_bounds(optimizer)
    
    # Приоритет 1: Используем сохраненные эффективные границы
    if class_idx in optimizer.effective_bounds:
        return optimizer.effective_bounds[class_idx]
    
    # Приоритет 2: Извлекаем из исходных данных класса
    if class_obj is None:
        class_obj = optimizer.classes[class_idx]
    
    bounds = extract_bounds_from_original_data(optimizer, class_obj, class_idx)
    
    # Сохраняем извлеченные границы для будущего использования
    optimizer.effective_bounds[class_idx] = bounds
    
    return bounds


def extract_bounds_from_original_data(optimizer, class_obj, class_idx: int) -> EffectiveBounds:
    """
    Извлекает границы из исходных данных класса (fallback механизм).
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        class_obj: Объект класса
        class_idx: Индекс класса
        
    Returns:
        EffectiveBounds: Границы, извлеченные из исходных данных
    """
    print(f"  Extracting bounds from original data for class {class_idx}")
    
    # Случай 1: Фиксированное время (только start_time)
    if class_obj.start_time and not class_obj.end_time:
        slot = time_to_slot(optimizer, class_obj.start_time)
        return EffectiveBounds(
            min_slot=slot,
            max_slot=slot,
            min_time=class_obj.start_time,
            max_time=class_obj.start_time,
            source="fixed_time",
            confidence="high"
        )
    
    # Случай 2: Временное окно (start_time и end_time)
    elif class_obj.start_time and class_obj.end_time:
        min_slot = time_to_slot(optimizer, class_obj.start_time)
        
        # Рассчитываем максимальный слот с учетом длительности
        duration_slots = class_obj.duration // optimizer.time_interval
        end_slot = time_to_slot(optimizer, class_obj.end_time)
        max_slot = max(min_slot, end_slot - duration_slots)
        
        return EffectiveBounds(
            min_slot=min_slot,
            max_slot=max_slot,
            min_time=class_obj.start_time,
            max_time=slot_to_time(optimizer, max_slot),
            source="time_window",
            confidence="high"
        )
    
    # Случай 3: Нет временных ограничений - используем полный диапазон дня
    else:
        return EffectiveBounds(
            min_slot=0,
            max_slot=len(optimizer.time_slots) - 1,
            min_time=optimizer.time_slots[0] if optimizer.time_slots else "08:00",
            max_time=optimizer.time_slots[-1] if optimizer.time_slots else "18:00",
            source="no_constraints",
            confidence="low"
        )


def time_to_slot(optimizer, time_str: str) -> int:
    """
    Конвертирует время в слот.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        time_str: Время в формате HH:MM
        
    Returns:
        int: Индекс слота времени
    """
    time_minutes = time_to_minutes(time_str)
    
    for slot_idx, slot_time in enumerate(optimizer.time_slots):
        slot_minutes = time_to_minutes(slot_time)
        if slot_minutes >= time_minutes:
            return slot_idx
    
    # Если время превышает последний слот, возвращаем последний
    return len(optimizer.time_slots) - 1


def slot_to_time(optimizer, slot_idx: int) -> str:
    """
    Конвертирует слот в время.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        slot_idx: Индекс слота времени
        
    Returns:
        str: Время в формате HH:MM
    """
    if 0 <= slot_idx < len(optimizer.time_slots):
        return optimizer.time_slots[slot_idx]
    elif slot_idx < 0:
        return optimizer.time_slots[0]
    else:
        return optimizer.time_slots[-1]


def classify_bounds(bounds: EffectiveBounds) -> str:
    """
    Классифицирует границы как 'fixed' или 'window'.
    
    Args:
        bounds: Объект EffectiveBounds
        
    Returns:
        str: 'fixed' если занятие фиксировано по времени, 'window' если имеет временное окно
    """
    return 'fixed' if bounds.min_slot == bounds.max_slot else 'window'


def update_bounds_from_constraint(optimizer, class_idx: int, constraint_type: str,
                                 min_slot: Optional[int] = None, max_slot: Optional[int] = None,
                                 description: str = ""):
    """
    Обновляет границы на основе примененного ограничения.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        class_idx: Индекс класса
        constraint_type: Тип примененного ограничения
        min_slot: Новый минимальный слот (если применимо)
        max_slot: Новый максимальный слот (если применимо)
        description: Описание ограничения
    """
    current_bounds = get_effective_bounds(optimizer, class_idx)
    
    # Сужаем границы
    new_min_slot = current_bounds.min_slot if min_slot is None else max(current_bounds.min_slot, min_slot)
    new_max_slot = current_bounds.max_slot if max_slot is None else min(current_bounds.max_slot, max_slot)
    
    # Проверяем корректность границ
    if new_min_slot > new_max_slot:
        print(f"WARNING: Invalid bounds for class {class_idx}: min_slot {new_min_slot} > max_slot {new_max_slot}")
        return
    
    set_effective_bounds(optimizer, class_idx, new_min_slot, new_max_slot, 
                        constraint_type, description)


def get_bounds_summary(optimizer) -> Dict[str, Any]:
    """
    Возвращает сводку по всем эффективным границам.
    
    Args:
        optimizer: Экземпляр ScheduleOptимizer
        
    Returns:
        Dict: Сводка по границам
    """
    initialize_effective_bounds(optimizer)
    
    summary = {
        'total_classes': len(optimizer.classes),
        'classes_with_bounds': len(optimizer.effective_bounds),
        'bounds_by_source': {},
        'confidence_distribution': {},
        'metadata': optimizer.bounds_metadata
    }
    
    # Анализируем источники и уверенность
    for class_idx, bounds in optimizer.effective_bounds.items():
        source = bounds.source
        confidence = bounds.confidence
        
        summary['bounds_by_source'][source] = summary['bounds_by_source'].get(source, 0) + 1
        summary['confidence_distribution'][confidence] = summary['confidence_distribution'].get(confidence, 0) + 1
    
    return summary


def print_bounds_report(optimizer):
    """
    Выводит детальный отчет по эффективным границам.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
    """
    print("\n=== EFFECTIVE BOUNDS REPORT ===")
    
    summary = get_bounds_summary(optimizer)
    
    print(f"Total classes: {summary['total_classes']}")
    print(f"Classes with effective bounds: {summary['classes_with_bounds']}")
    print(f"Update count: {summary['metadata']['update_count']}")
    print(f"Last updated: {summary['metadata']['last_updated']}")
    
    print(f"\nBounds by source:")
    for source, count in summary['bounds_by_source'].items():
        print(f"  {source}: {count}")
    
    print(f"\nConfidence distribution:")
    for confidence, count in summary['confidence_distribution'].items():
        print(f"  {confidence}: {count}")
    
    # Детальная информация по каждому классу
    if hasattr(optimizer, 'effective_bounds') and optimizer.effective_bounds:
        print(f"\nDetailed bounds per class:")
        for class_idx in sorted(optimizer.effective_bounds.keys()):
            bounds = optimizer.effective_bounds[class_idx]
            class_obj = optimizer.classes[class_idx]
            
            print(f"  Class {class_idx} ({class_obj.subject}): {bounds}")
            if bounds.applied_constraints:
                for constraint in bounds.applied_constraints:
                    print(f"    - {constraint['type']}: {constraint['description']}")
    
    print("=" * 35)
