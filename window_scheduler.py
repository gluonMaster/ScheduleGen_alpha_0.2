"""
Модуль для планирования размещения занятий в временных окнах.

Этот модуль предоставляет функциональность для расчета последовательного
размещения занятий с учетом временных окон, связанных цепочек и пауз.
"""

from time_utils import time_to_minutes, minutes_to_time
from timewindow_utils import find_slot_for_time
from timeline_manager import Timeline


class PlacementPlan:
    """Класс для представления плана размещения занятий."""
    
    def __init__(self, plan_type, class_group, timeline=None):
        """
        Инициализирует план размещения.
        
        Args:
            plan_type: Тип плана ('sequential', 'anchored', 'flexible', 'linked_chain')
            class_group: Объект ClassGroup для планирования
            timeline: Объект Timeline (опционально)
        """
        self.plan_type = plan_type
        self.class_group = class_group
        self.timeline = timeline
        self.placements = []  # Список размещений занятий
        self.constraints = []  # Список ограничений для добавления
        self.is_valid = False
        self.validation_errors = []
    
    def add_placement(self, class_idx, placement_info):
        """
        Добавляет информацию о размещении занятия.
        
        Args:
            class_idx: Индекс занятия
            placement_info: Словарь с информацией о размещении
        """
        self.placements.append({
            'class_idx': class_idx,
            'info': placement_info
        })
    
    def add_constraint(self, constraint_type, constraint_data):
        """
        Добавляет ограничение в план.
        
        Args:
            constraint_type: Тип ограничения ('sequential', 'fixed_slot', 'window_bounds')
            constraint_data: Данные ограничения
        """
        self.constraints.append({
            'type': constraint_type,
            'data': constraint_data
        })
    
    def get_debug_info(self):
        """Возвращает отладочную информацию о плане."""
        return {
            'plan_type': self.plan_type,
            'group_key': self.class_group.group_key,
            'day': self.class_group.day,
            'is_valid': self.is_valid,
            'placements_count': len(self.placements),
            'constraints_count': len(self.constraints),
            'validation_errors': self.validation_errors,
            'placements': self.placements,
            'constraints': [c['type'] for c in self.constraints]
        }


def calculate_sequential_placement(class_list, common_window):
    """
    Рассчитывает последовательное размещение занятий в общем временном окне.
    
    Args:
        class_list: Список кортежей (idx, class_obj) для размещения
        common_window: Кортеж (start_minutes, end_minutes) общего временного окна
        
    Returns:
        dict: Информация о последовательном размещении
    """
    print(f"Calculating sequential placement for {len(class_list)} classes")
    
    if not class_list:
        return {'success': False, 'reason': 'No classes to place'}
    
    window_start, window_end = common_window
    available_time = window_end - window_start
    
    # Рассчитываем общую требуемую длительность
    total_duration = sum(c.duration for _, c in class_list)
    
    # Рассчитываем общие паузы
    total_pauses = 0
    if len(class_list) > 1:
        # Паузы после занятий (кроме последнего)
        total_pauses += sum(c.pause_after for _, c in class_list[:-1])
        # Паузы перед занятиями (кроме первого)
        total_pauses += sum(c.pause_before for _, c in class_list[1:])
    
    total_required_time = total_duration + total_pauses
    
    print(f"  Available time: {available_time} min")
    print(f"  Required time: {total_required_time} min (classes: {total_duration}, pauses: {total_pauses})")
    
    if total_required_time > available_time:
        return {
            'success': False,
            'reason': 'Not enough time in window',
            'required_time': total_required_time,
            'available_time': available_time,
            'deficit': total_required_time - available_time
        }
    
    # Рассчитываем размещения
    placements = []
    current_time = window_start
    
    for i, (idx, c) in enumerate(class_list):
        placement = {
            'class_idx': idx,
            'start_time_minutes': current_time,
            'end_time_minutes': current_time + c.duration,
            'start_time_str': minutes_to_time(current_time),
            'end_time_str': minutes_to_time(current_time + c.duration),
            'position_in_sequence': i
        }
        placements.append(placement)
        
        print(f"    Class {idx}: {placement['start_time_str']}-{placement['end_time_str']}")
        
        # Обновляем текущее время для следующего занятия
        current_time += c.duration
        if i < len(class_list) - 1:
            current_time += c.pause_after + class_list[i + 1][1].pause_before
    
    return {
        'success': True,
        'placements': placements,
        'total_time_used': current_time - window_start,
        'remaining_time': available_time - (current_time - window_start),
        'window_start': window_start,
        'window_end': window_end
    }


def place_linked_chain_in_window(optimizer, chain_classes, window_bounds):
    """
    Специальная обработка связанных цепочек с правильным порядком.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        chain_classes: Список кортежей (idx, class_obj) связанной цепочки
        window_bounds: Кортеж (start_minutes, end_minutes) временного окна
        
    Returns:
        dict: Информация о размещении цепочки
    """
    print(f"Placing linked chain of {len(chain_classes)} classes")
    
    # Проверяем, что все классы действительно связаны в цепочку
    chain_indices = [idx for idx, _ in chain_classes]
    
    # Находим правильный порядок цепочки
    ordered_chain = []
    if hasattr(optimizer, "linked_chains"):
        for chain in optimizer.linked_chains:
            chain_intersection = [idx for idx in chain if idx in chain_indices]
            if len(chain_intersection) > len(ordered_chain):
                ordered_chain = chain_intersection
    
    if not ordered_chain:
        print("  WARNING: No linked chain found, using original order")
        ordered_chain = chain_indices
    
    # Упорядочиваем классы согласно цепочке
    ordered_classes = []
    for chain_idx in ordered_chain:
        for idx, c in chain_classes:
            if idx == chain_idx:
                ordered_classes.append((idx, c))
                break
    
    # Добавляем классы, которые не нашлись в формальной цепочке
    for idx, c in chain_classes:
        if idx not in ordered_chain:
            ordered_classes.append((idx, c))
    
    print(f"  Chain order: {[idx for idx, _ in ordered_classes]}")
    
    # Рассчитываем последовательное размещение
    sequential_result = calculate_sequential_placement(ordered_classes, window_bounds)
    
    if not sequential_result['success']:
        return {
            'success': False,
            'reason': f"Chain placement failed: {sequential_result['reason']}",
            'chain_order': ordered_chain,
            'details': sequential_result
        }
    
    return {
        'success': True,
        'placement_type': 'linked_chain',
        'chain_order': ordered_chain,
        'placements': sequential_result['placements'],
        'strict_sequence': True,  # Цепочки требуют строгой последовательности
        'window_bounds': window_bounds,
        'details': sequential_result
    }


def place_classes_with_anchors(optimizer, window_classes, timeline):
    """
    Размещает оконные классы с учетом фиксированных "якорных" занятий.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        window_classes: Список кортежей (idx, class_obj) оконных занятий
        timeline: Объект Timeline с фиксированными якорями
        
    Returns:
        dict: Информация о размещении с якорями
    """
    print(f"Placing {len(window_classes)} window classes with {len(timeline.anchors)} anchors")
    
    placements = []
    used_slots = []
    
    for idx, c in window_classes:
        print(f"  Placing class {idx} ({c.duration} min)")
        
        # Проверяем, связан ли класс с фиксированными занятиями
        linked_to_anchor = _find_linked_anchor(optimizer, idx, timeline.anchors)
        
        if linked_to_anchor:
            placement = _place_relative_to_anchor(optimizer, idx, c, linked_to_anchor, timeline)
        else:
            placement = _place_in_best_free_slot(optimizer, idx, c, timeline)
        
        if placement:
            placements.append(placement)
            if 'reserved_slot' in placement:
                timeline.reserve_slot(placement['reserved_slot'], c)
        else:
            print(f"    WARNING: Could not place class {idx}")
    
    return {
        'success': len(placements) == len(window_classes),
        'placement_type': 'anchored',
        'placements': placements,
        'anchors_used': len(timeline.anchors),
        'timeline_debug': timeline.get_debug_info()
    }


def _find_linked_anchor(optimizer, class_idx, anchors):
    """Находит якорное занятие, связанное с данным классом."""
    c = optimizer.classes[class_idx]
    
    if not hasattr(c, 'linked_classes') or not c.linked_classes:
        return None
    
    for linked_class in c.linked_classes:
        try:
            linked_idx = optimizer._find_class_index(linked_class)
            
            # Проверяем, является ли связанный класс якорем
            for anchor in anchors:
                if anchor['idx'] == linked_idx:
                    return anchor
        except:
            continue
    
    return None


def _place_relative_to_anchor(optimizer, class_idx, class_obj, anchor, timeline):
    """Размещает класс относительно якорного занятия."""
    anchor_start = anchor['start_min']
    anchor_end = anchor['end_min']
    
    print(f"    Placing relative to anchor {anchor['idx']} at {minutes_to_time(anchor_start)}")
    
    # Класс должен предшествовать якорному
    adjusted_end = anchor_start - anchor['class'].pause_before
    
    # Ищем подходящий слот до якорного занятия
    best_slot = None
    for slot_start, slot_end in timeline.free_slots:
        if slot_start < adjusted_end and slot_end > slot_start:
            real_end = min(slot_end, adjusted_end)
            if real_end - slot_start >= class_obj.duration:
                best_slot = {
                    'slot_start': slot_start,
                    'slot_end': slot_end,
                    'placement_start': real_end - class_obj.duration,  # Размещаем ближе к якорю
                    'placement_end': real_end
                }
                break
    
    if not best_slot:
        return None
    
    placement_start_slot = find_slot_for_time(
        optimizer.time_slots, 
        minutes_to_time(best_slot['placement_start'])
    )
    placement_end_slot = find_slot_for_time(
        optimizer.time_slots,
        minutes_to_time(best_slot['placement_end'])
    )
    
    return {
        'class_idx': class_idx,
        'placement_type': 'relative_to_anchor',
        'anchor_idx': anchor['idx'],
        'start_slot': placement_start_slot,
        'end_slot': placement_end_slot,
        'start_time': minutes_to_time(best_slot['placement_start']),
        'end_time': minutes_to_time(best_slot['placement_end']),
        'reserved_slot': best_slot
    }


def _place_in_best_free_slot(optimizer, class_idx, class_obj, timeline):
    """Размещает класс в лучшем доступном свободном слоте."""
    window_start = time_to_minutes(class_obj.start_time)
    window_end = time_to_minutes(class_obj.end_time)
    
    best_slot = timeline.find_best_slot(class_obj, prefer_early=True)
    
    if not best_slot:
        return None
    
    placement_start_slot = find_slot_for_time(
        optimizer.time_slots,
        minutes_to_time(best_slot['placement_start'])
    )
    placement_end_slot = find_slot_for_time(
        optimizer.time_slots,
        minutes_to_time(best_slot['placement_end'])
    )
    
    return {
        'class_idx': class_idx,
        'placement_type': 'free_slot',
        'start_slot': placement_start_slot,
        'end_slot': placement_end_slot,
        'start_time': minutes_to_time(best_slot['placement_start']),
        'end_time': minutes_to_time(best_slot['placement_end']),
        'reserved_slot': best_slot
    }


def validate_placement(optimizer, placement_plan):
    """
    Валидирует план размещения на выполнимость.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        placement_plan: Словарь с информацией о размещении
        
    Returns:
        bool: True, если план валиден
    """
    if not placement_plan.get('success', False):
        return False
    
    placements = placement_plan.get('placements', [])
    if not placements:
        return False
    
    # Проверяем пересечения по времени
    for i, placement1 in enumerate(placements):
        for j, placement2 in enumerate(placements):
            if i >= j:
                continue
            
            start1 = placement1.get('start_time_minutes', 0)
            end1 = placement1.get('end_time_minutes', 0)
            start2 = placement2.get('start_time_minutes', 0)
            end2 = placement2.get('end_time_minutes', 0)
            
            # Проверяем пересечение
            if start1 < end2 and start2 < end1:
                print(f"Validation error: Time conflict between classes {placement1.get('class_idx')} and {placement2.get('class_idx')}")
                return False
    
    # Проверяем соответствие временным окнам
    for placement in placements:
        class_idx = placement.get('class_idx')
        if class_idx is not None and class_idx < len(optimizer.classes):
            c = optimizer.classes[class_idx]
            
            if c.start_time and c.end_time:
                window_start = time_to_minutes(c.start_time)
                window_end = time_to_minutes(c.end_time)
                placement_start = placement.get('start_time_minutes', 0)
                placement_end = placement.get('end_time_minutes', 0)
                
                if placement_start < window_start or placement_end > window_end:
                    print(f"Validation error: Class {class_idx} placed outside its time window")
                    return False
    
    return True


def create_placement_plan(optimizer, class_group, timeline=None):
    """
    Создает план размещения для группы занятий.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        class_group: Объект ClassGroup
        timeline: Объект Timeline (опционально)
        
    Returns:
        PlacementPlan: Объект плана размещения
    """
    print(f"Creating placement plan for {class_group.group_key} on {class_group.day}")
    
    # Определяем тип плана размещения
    if class_group.fixed_classes and class_group.window_classes:
        plan_type = 'anchored'
    elif class_group.can_fit_in_common_window() and len(class_group.window_classes) > 1:
        plan_type = 'sequential'
    else:
        plan_type = 'flexible'
    
    # Проверяем наличие связанных цепочек
    has_linked_chain = False
    if hasattr(optimizer, "linked_chains"):
        class_indices = {idx for idx, _ in class_group.classes}
        for chain in optimizer.linked_chains:
            if len(set(chain) & class_indices) > 1:
                plan_type = 'linked_chain'
                has_linked_chain = True
                break
    
    plan = PlacementPlan(plan_type, class_group, timeline)
    
    print(f"  Plan type: {plan_type}")
    
    # Выполняем размещение в зависимости от типа плана
    if plan_type == 'sequential':
        result = calculate_sequential_placement(
            class_group.window_classes,
            (class_group.common_window_start, class_group.common_window_end)
        )
        plan.is_valid = result['success']
        if result['success']:
            for placement in result['placements']:
                plan.add_placement(placement['class_idx'], placement)
    
    elif plan_type == 'linked_chain':
        result = place_linked_chain_in_window(
            optimizer,
            class_group.window_classes,
            (class_group.common_window_start, class_group.common_window_end)
        )
        plan.is_valid = result['success']
        if result['success']:
            # Сохраняем chain_order в плане
            if 'chain_order' in result:
                plan.chain_order = result['chain_order']
            for placement in result['placements']:
                plan.add_placement(placement['class_idx'], placement)
    
    elif plan_type == 'anchored' and timeline:
        result = place_classes_with_anchors(optimizer, class_group.window_classes, timeline)
        plan.is_valid = result['success']
        if result['success']:
            for placement in result['placements']:
                plan.add_placement(placement['class_idx'], placement)
    
    else:
        # Flexible plan - только разделительные ограничения
        plan.is_valid = True
        plan.add_constraint('separation_only', {'classes': class_group.classes})
    
    return plan
