"""
Модуль для анализа возможности последовательного планирования занятий.
Предоставляет функции для определения, могут ли занятия быть размещены последовательно
в одной аудитории или с одним преподавателем.
"""

from time_utils import time_to_minutes, minutes_to_time
from linked_chain_utils import collect_full_chain
from chain_scheduler import schedule_chain, chain_busy_intervals
from effective_bounds_utils import get_effective_bounds, classify_bounds

# Глобальный кеш для результатов анализа пар
_analysis_cache = {}

def clear_analysis_cache():
    """Очистить кеш анализа для новой оптимизации."""
    global _analysis_cache
    _analysis_cache = {}
    print("Analysis cache cleared for new optimization")

def is_class_in_linked_chain(schedule_class):
    """
    Проверяет, является ли класс частью цепочки связанных занятий.
    Класс является частью цепочки, если:
    1. У него есть linked_classes (он - начало цепочки)
    2. У него есть previous_class (он - продолжение цепочки)
    
    Args:
        schedule_class: Экземпляр ScheduleClass
        
    Returns:
        bool: True, если класс является частью цепочки
    """
    # Проверяем, есть ли у класса связанные занятия (он - начало цепочки)
    if hasattr(schedule_class, 'linked_classes') and schedule_class.linked_classes:
        return True
    
    # Проверяем, есть ли у класса предыдущее занятие (он - продолжение цепочки)
    if hasattr(schedule_class, 'previous_class') and schedule_class.previous_class:
        return True
    
    return False

def collect_full_chain_from_any_member(schedule_class):
    """
    Собирает полную цепочку занятий, начиная с любого элемента цепочки.
    Сначала находит начало цепочки, затем собирает всю цепочку.
    
    Args:
        schedule_class: Любой элемент цепочки
        
    Returns:
        list: Полная цепочка занятий в правильном порядке
    """
    # Находим начало цепочки (элемент без previous_class)
    root_class = schedule_class
    while hasattr(root_class, 'previous_class') and root_class.previous_class:
        # Находим объект предыдущего класса по его subject
        # Это упрощенная версия - в реальной системе может потребоваться более сложный поиск
        found_previous = False
        if hasattr(schedule_class, '__dict__'):
            for attr_name, attr_value in schedule_class.__dict__.items():
                if (hasattr(attr_value, 'subject') and 
                    attr_value.subject == root_class.previous_class):
                    root_class = attr_value
                    found_previous = True
                    break
        
        if not found_previous:
            break  # Не можем найти предыдущий класс, останавливаемся
    
    # Теперь собираем цепочку от корня используя linked_classes
    return collect_full_chain(root_class)

def can_schedule_sequentially(c1, c2, idx1=None, idx2=None, verbose=True, optimizer=None):
    """
    Проверяет, могут ли два занятия быть запланированы последовательно с учетом их временных ограничений.
    
    Args:
        c1: Первое занятие (ScheduleClass)
        c2: Второе занятие (ScheduleClass)
        idx1: Индекс первого занятия (для правильного логгирования)
        idx2: Индекс второго занятия (для правильного логгирования)
        verbose: Включить детальное логгирование (по умолчанию True)
        optimizer: Экземпляр ScheduleOptimizer (для получения эффективных границ)
        
    Returns:
        tuple: (bool, dict) - возможно ли последовательное размещение и дополнительная информация
    """
    global _analysis_cache
    
    # Определяем метки классов сразу для использования везде
    class1_label = f"Class {idx1}" if idx1 is not None else "Class 1"
    class2_label = f"Class {idx2}" if idx2 is not None else "Class 2"
    
    # Создаем ключ для кеширования на основе индексов (более надежно чем id объектов)
    if idx1 is not None and idx2 is not None:
        cache_key = (idx1, idx2)  # Сохраняем порядок, так как функция не симметрична
    else:
        cache_key = (id(c1), id(c2))  # Fallback для старых вызовов
    
    # Вспомогательная функция для кеширования результата
    def cache_and_return(can_schedule, info):
        result = (can_schedule, info)
        _analysis_cache[cache_key] = result
        return result
    
    # Проверяем кеш
    if cache_key in _analysis_cache:
        result = _analysis_cache[cache_key]
        if verbose:
            print(f"[CACHED] {class1_label}: {c1.subject}({c1.group}) + {class2_label}: {c2.subject}({c2.group}) -> {result[1].get('reason', 'unknown')}")
        return result
    
    if verbose:
        print(f"\n=== ANALYZING SEQUENTIAL SCHEDULING ===")
        print(f"{class1_label}: {c1.subject} ({c1.group}) - Teacher: {c1.teacher}")
        print(f"{class2_label}: {c2.subject} ({c2.group}) - Teacher: {c2.teacher}")
    
    info = {
        'reason': '',
        'c1_start': None,
        'c1_end': None,
        'c2_start': None,
        'c2_end': None,
        'common_window': None,
        'required_time': None,
        'available_time': None
    }
    
    # Проверка наличия общего дня
    if c1.day != c2.day:
        info['reason'] = 'different_days'
        if verbose:
            print(f"RESULT: Cannot schedule sequentially - {info['reason']}")
            print(f"  {class1_label} day: {c1.day}, {class2_label} day: {c2.day}")
        return cache_and_return(False, info)
    
    # НОВОЕ: Используем эффективные границы, если доступен оптимизатор
    if optimizer and idx1 is not None and idx2 is not None:
        try:
            bounds1 = get_effective_bounds(optimizer, idx1, c1)
            bounds2 = get_effective_bounds(optimizer, idx2, c2)
            
            if verbose:
                print(f"EFFECTIVE BOUNDS ANALYSIS:")
                print(f"  {class1_label}: {bounds1}")
                print(f"  {class2_label}: {bounds2}")
            
            # Используем эффективные границы для более точного анализа
            window1_start = time_to_minutes(bounds1.min_time)
            window1_end = time_to_minutes(bounds1.max_time) + c1.duration
            window2_start = time_to_minutes(bounds2.min_time)
            window2_end = time_to_minutes(bounds2.max_time) + c2.duration
            
            info['c1_start'] = bounds1.min_time
            info['c1_end'] = minutes_to_time(window1_end)
            info['c2_start'] = bounds2.min_time
            info['c2_end'] = minutes_to_time(window2_end)
            
            # Проверяем пересечение эффективных границ
            if window1_end <= window2_start:
                info['reason'] = 'non_overlapping_effective_bounds_c1_before_c2'
                if verbose:
                    print(f"RESULT: Can schedule sequentially - {info['reason']}")
                    print(f"  {class1_label} ends before {class2_label} starts (effective bounds)")
                return cache_and_return(True, info)
                    
            elif window2_end <= window1_start:
                info['reason'] = 'non_overlapping_effective_bounds_c2_before_c1'
                if verbose:
                    print(f"RESULT: Can schedule sequentially - {info['reason']}")
                    print(f"  {class2_label} ends before {class1_label} starts (effective bounds)")
                return cache_and_return(True, info)
            
            # Анализируем возможность размещения в пересекающихся эффективных границах
            overlap_start = max(window1_start, window2_start)
            overlap_end = min(window1_end, window2_end)
            overlap_duration = max(0, overlap_end - overlap_start)
            
            # Рассчитываем необходимое время для размещения обоих занятий
            total_duration = c1.duration + c2.duration
            min_gap = max(getattr(c1, 'pause_after', 0), getattr(c2, 'pause_before', 0))
            required_time = total_duration + min_gap
            
            if verbose:
                print(f"  OVERLAP ANALYSIS:")
                print(f"    Overlap: {minutes_to_time(overlap_start)}-{minutes_to_time(overlap_end)} ({overlap_duration} min)")
                print(f"    Required time: {required_time} min (c1: {c1.duration}, gap: {min_gap}, c2: {c2.duration})")
                print(f"    Available time: {overlap_duration} min")
            
            info['common_window'] = f"{minutes_to_time(overlap_start)}-{minutes_to_time(overlap_end)}"
            info['required_time'] = required_time
            info['available_time'] = overlap_duration
            
            if overlap_duration >= required_time:
                info['reason'] = 'sufficient_time_in_effective_overlap'
                if verbose:
                    print(f"RESULT: Can schedule sequentially - {info['reason']}")
                return cache_and_return(True, info)
            else:
                info['reason'] = 'insufficient_time_in_effective_overlap'
                if verbose:
                    print(f"RESULT: Cannot schedule sequentially - {info['reason']}")
                return cache_and_return(False, info)
        except Exception as e:
            if verbose:
                print(f"  Warning: Could not use effective bounds ({e}), falling back to original logic")
    
    # Fallback к исходной логике для обратной совместимости
    # Проверка наличия эффективных границ через effective_bounds
    if optimizer is not None and idx1 is not None and idx2 is not None:
        try:
            bounds1 = get_effective_bounds(optimizer, idx1, c1)
            bounds2 = get_effective_bounds(optimizer, idx2, c2)
            
            # Проверяем, есть ли у классов временные ограничения
            has_time_constraints = (bounds1.min_time is not None and 
                                  bounds2.min_time is not None)
            
            if not has_time_constraints:
                info['reason'] = 'no_time_constraints_in_bounds'
                if verbose:
                    print(f"RESULT: Can schedule sequentially - {info['reason']}")
                    print(f"  {class1_label} bounds: {bounds1}")
                    print(f"  {class2_label} bounds: {bounds2}")
                return cache_and_return(True, info)
        except Exception as e:
            if verbose:
                print(f"  Warning: Could not get effective bounds ({e}), checking original start_time")
            
            # Fallback к проверке оригинальных полей
            if not c1.start_time or not c2.start_time:
                info['reason'] = 'missing_time_info'
                if verbose:
                    print(f"RESULT: Can schedule sequentially - {info['reason']}")
                    print(f"  {class1_label} start_time: {c1.start_time}, {class2_label} start_time: {c2.start_time}")
                return cache_and_return(True, info)
    else:
        # Старая логика когда нет optimizer или индексов
        if not c1.start_time or not c2.start_time:
            info['reason'] = 'missing_time_info'
            if verbose:
                print(f"RESULT: Can schedule sequentially - {info['reason']}")
                print(f"  {class1_label} start_time: {c1.start_time}, {class2_label} start_time: {c2.start_time}")
            return cache_and_return(True, info)
    
    # НОВОЕ: Логгирование статуса цепочек
    c1_has_linked = is_class_in_linked_chain(c1)
    c2_has_linked = is_class_in_linked_chain(c2)
    
    if verbose:
        print(f"CHAIN ANALYSIS:")
        print(f"  {class1_label} in chain: {c1_has_linked}")
        if c1_has_linked:
            try:
                c1_chain = collect_full_chain_from_any_member(c1)
                chain_subjects = [cls.subject for cls in c1_chain]
                print(f"    Chain composition: {chain_subjects}")
            except Exception as e:
                print(f"    Failed to collect chain: {e}")
        
        print(f"  {class2_label} in chain: {c2_has_linked}")
        if c2_has_linked:
            try:
                c2_chain = collect_full_chain_from_any_member(c2)
                chain_subjects = [cls.subject for cls in c2_chain]
                print(f"    Chain composition: {chain_subjects}")
            except Exception as e:
                print(f"    Failed to collect chain: {e}")

    # Используем effective_bounds для проверки случаев с фиксированным временем и временным окном
    if optimizer is not None and idx1 is not None and idx2 is not None:
        try:
            bounds1 = get_effective_bounds(optimizer, idx1, c1)
            bounds2 = get_effective_bounds(optimizer, idx2, c2)
            
            type1 = classify_bounds(bounds1)
            type2 = classify_bounds(bounds2)
            
            if type1 == 'fixed' and type2 == 'window':
                # c1 фиксировано, c2 с окном
                fixed_start = time_to_minutes(bounds1.min_time)
                fixed_end = fixed_start + c1.duration + getattr(c1, 'pause_after', 0)
                window_start = time_to_minutes(bounds2.min_time)
                window_end = time_to_minutes(bounds2.max_time)
                
                if verbose:
                    print(f"FIXED vs WINDOW ANALYSIS (using effective bounds):")
                    print(f"  {class1_label} (fixed): {bounds1.min_time} duration {c1.duration} min + pause_after {getattr(c1, 'pause_after', 0)} min = ends at {minutes_to_time(fixed_end)}")
                    print(f"  {class2_label} (window): {bounds2.min_time}-{bounds2.max_time} duration {c2.duration} min + pause_after {getattr(c2, 'pause_after', 0)} min")
                    
                return _analyze_fixed_vs_window(fixed_start, fixed_end, window_start, window_end, 
                                              c2.duration, getattr(c2, 'pause_after', 0),
                                              class1_label, class2_label, verbose, info, cache_and_return)
            
            elif type2 == 'fixed' and type1 == 'window':
                # c2 фиксировано, c1 с окном
                fixed_start = time_to_minutes(bounds2.min_time) 
                fixed_end = fixed_start + c2.duration + getattr(c2, 'pause_after', 0)
                window_start = time_to_minutes(bounds1.min_time)
                window_end = time_to_minutes(bounds1.max_time)
                
                if verbose:
                    print(f"WINDOW vs FIXED ANALYSIS (using effective bounds):")
                    print(f"  {class1_label} (window): {bounds1.min_time}-{bounds1.max_time} duration {c1.duration} min + pause_after {getattr(c1, 'pause_after', 0)} min")
                    print(f"  {class2_label} (fixed): {bounds2.min_time} duration {c2.duration} min + pause_after {getattr(c2, 'pause_after', 0)} min = ends at {minutes_to_time(fixed_end)}")
                    
                return _analyze_window_vs_fixed(window_start, window_end, fixed_start, fixed_end,
                                              c1.duration, getattr(c1, 'pause_after', 0),
                                              class1_label, class2_label, verbose, info, cache_and_return)
            
            elif type1 == 'window' and type2 == 'window':
                # Оба с временными окнами
                window1_start = time_to_minutes(bounds1.min_time)
                window1_end = time_to_minutes(bounds1.max_time)
                window2_start = time_to_minutes(bounds2.min_time)
                window2_end = time_to_minutes(bounds2.max_time)
                
                if verbose:
                    print(f"WINDOW vs WINDOW ANALYSIS (using effective bounds):")
                    print(f"  {class1_label}: {bounds1.min_time} - {bounds1.max_time} ({window1_start}-{window1_end} min)")
                    print(f"  {class2_label}: {bounds2.min_time} - {bounds2.max_time} ({window2_start}-{window2_end} min)")
                    
                # Используем новую логику для анализа двух окон
                return _analyze_window_vs_window_bounds(bounds1, bounds2, c1, c2, 
                                                      class1_label, class2_label, verbose, info, cache_and_return)
            
            elif type1 == 'fixed' and type2 == 'fixed':
                # Оба фиксированы
                start1 = time_to_minutes(bounds1.min_time)
                end1 = start1 + c1.duration + getattr(c1, 'pause_after', 0)
                start2 = time_to_minutes(bounds2.min_time)
                end2 = start2 + c2.duration + getattr(c2, 'pause_after', 0)
                
                if verbose:
                    print(f"FIXED vs FIXED ANALYSIS (using effective bounds):")
                    print(f"  {class1_label}: {bounds1.min_time} ({start1} min) duration {c1.duration} min + pause_after {getattr(c1, 'pause_after', 0)} min = ends at {minutes_to_time(end1)}")
                    print(f"  {class2_label}: {bounds2.min_time} ({start2} min) duration {c2.duration} min + pause_after {getattr(c2, 'pause_after', 0)} min = ends at {minutes_to_time(end2)}")
                    
                return _analyze_fixed_vs_fixed(start1, end1, start2, end2, 
                                             class1_label, class2_label, verbose, info, cache_and_return)
                
        except Exception as e:
            if verbose:
                print(f"  Warning: Could not use effective bounds for analysis ({e}), falling back to original logic")
        
    # Fallback к оригинальной логике на основе start_time/end_time для обратной совместимости
    if c1.start_time and not c1.end_time and c2.start_time and c2.end_time:
        # c1 фиксировано, c2 с окном
        fixed_start   = time_to_minutes(c1.start_time)
        fixed_end     = fixed_start + c1.duration + getattr(c1, 'pause_after', 0)
        window_start  = time_to_minutes(c2.start_time)
        window_end    = time_to_minutes(c2.end_time)
        
        if verbose:
            print(f"FIXED vs WINDOW ANALYSIS (fallback):")
            print(f"  {class1_label} (fixed): {c1.start_time} duration {c1.duration} min + pause_after {getattr(c1, 'pause_after', 0)} min = ends at {minutes_to_time(fixed_end)}")
            print(f"  {class2_label} (window): {c2.start_time}-{c2.end_time} duration {c2.duration} min + pause_after {getattr(c2, 'pause_after', 0)} min")
        print(f"                    needs pause_before {getattr(c2, 'pause_before', 0)} min")
    
        # Проверяем оба направления
        required_before_fixed = c2.duration + getattr(c2, 'pause_after', 0)
        available_before_fixed = fixed_start - getattr(c1, 'pause_before', 0) - window_start
        can_fit_before = available_before_fixed >= required_before_fixed
        
        required_after_fixed = c2.duration + getattr(c2, 'pause_before', 0)
        available_after_fixed = window_end - fixed_end
        can_fit_after = available_after_fixed >= required_after_fixed
        
        print(f"  CAN FIT BEFORE FIXED:")
        print(f"    Available: {available_before_fixed} min (window_start to fixed_start - pause_before)")
        print(f"    Required: {required_before_fixed} min (c2_duration + pause_after)")
        print(f"    Result: {'✓' if can_fit_before else '✗'}")
        print(f"  CAN FIT AFTER FIXED:")
        print(f"    Available: {available_after_fixed} min (fixed_end to window_end)")
        print(f"    Required: {required_after_fixed} min (c2_duration + pause_before)")
        print(f"    Result: {'✓' if can_fit_after else '✗'}")
    
        if can_fit_before and can_fit_after:
            info['reason'] = 'both_orders_possible'
            info['available_time'] = f"before: {available_before_fixed} min, after: {available_after_fixed} min"
            info['required_time'] = f"before: {required_before_fixed} min, after: {required_after_fixed} min"
            print(f"RESULT: Can schedule sequentially - {info['reason']}")
            return cache_and_return(True, info)
        elif can_fit_before:
            info['reason'] = 'fits_before_fixed'
            info['available_time'] = f"before fixed: {available_before_fixed} min"
            info['required_time'] = required_before_fixed
            print(f"RESULT: Can schedule sequentially - {info['reason']}")
            return cache_and_return(True, info)
        elif can_fit_after:
            info['reason'] = 'fits_after_fixed'
            info['available_time'] = f"after fixed: {available_after_fixed} min"
            info['required_time'] = required_after_fixed
            print(f"RESULT: Can schedule sequentially - {info['reason']}")
            return cache_and_return(True, info)
        else:
            info['reason'] = 'not_enough_time_around_fixed'
            info['available_time'] = f"before: {available_before_fixed} min, after: {available_after_fixed} min"
            info['required_time'] = f"before: {required_before_fixed} min, after: {required_after_fixed} min"
        return _analyze_fixed_vs_window(fixed_start, fixed_end, window_start, window_end, 
                                       c2.duration, getattr(c2, 'pause_after', 0),
                                       class1_label, class2_label, verbose, info, cache_and_return)
            
    elif c2.start_time and not c2.end_time and c1.start_time and c1.end_time:
        # c2 фиксировано, c1 с окном (fallback)
        fixed_start = time_to_minutes(c2.start_time)
        fixed_end = fixed_start + c2.duration + getattr(c2, 'pause_after', 0)
        window_start = time_to_minutes(c1.start_time)
        window_end = time_to_minutes(c1.end_time)
        
        if verbose:
            print(f"WINDOW vs FIXED ANALYSIS (fallback):")
            print(f"  {class1_label} (window): {c1.start_time}-{c1.end_time} duration {c1.duration} min")
            print(f"  {class2_label} (fixed): {c2.start_time} duration {c2.duration} min")

        return _analyze_window_vs_fixed(window_start, window_end, fixed_start, fixed_end,
                                       c1.duration, getattr(c1, 'pause_after', 0),
                                       class1_label, class2_label, verbose, info, cache_and_return)
    
    elif c1.start_time and c1.end_time and c2.start_time and c2.end_time:
        # Оба занятия с временными окнами (fallback)
        if verbose:
            print(f"WINDOW vs WINDOW ANALYSIS (fallback):")
            print(f"  {class1_label}: {c1.start_time} - {c1.end_time}")
            print(f"  {class2_label}: {c2.start_time} - {c2.end_time}")
        
        # Используем упрощенную версию анализа окон
        window1_start = time_to_minutes(c1.start_time)
        window1_end = time_to_minutes(c1.end_time)
        window2_start = time_to_minutes(c2.start_time)
        window2_end = time_to_minutes(c2.end_time)
        
        # Проверяем перекрытие
        overlap_start = max(window1_start, window2_start)
        overlap_end = min(window1_end, window2_end)
        
        if overlap_start >= overlap_end:
            info['reason'] = 'no_time_overlap_fallback'
            return cache_and_return(True, info)
        
        overlap_duration = overlap_end - overlap_start
        total_required = c1.duration + c2.duration + getattr(c1, 'pause_after', 0) + getattr(c2, 'pause_before', 0)
        
        if overlap_duration >= total_required:
            info['reason'] = 'sufficient_overlap_time_fallback'
            return cache_and_return(True, info)
        else:
            info['reason'] = 'insufficient_overlap_time_fallback'
            return cache_and_return(False, info)
    
    elif c1.start_time and not c1.end_time and c2.start_time and not c2.end_time:
        # Оба занятия с фиксированным временем (fallback)
        start1 = time_to_minutes(c1.start_time)
        end1 = start1 + c1.duration + getattr(c1, 'pause_after', 0)
        start2 = time_to_minutes(c2.start_time)
        end2 = start2 + c2.duration + getattr(c2, 'pause_after', 0)
        
        if verbose:
            print(f"BOTH FIXED TIMES ANALYSIS (fallback):")
            print(f"  {class1_label}: {c1.start_time} duration {c1.duration} min")
            print(f"  {class2_label}: {c2.start_time} duration {c2.duration} min")
            
        return _analyze_fixed_vs_fixed(start1, end1, start2, end2, 
                                     class1_label, class2_label, verbose, info, cache_and_return)
    
    # Если достигли этой точки, значит не все случаи обработаны
    info['reason'] = 'unknown_time_configuration'
    if verbose:
        print(f"RESULT: Can schedule sequentially - {info['reason']} (default fallback)")
    return cache_and_return(True, info)  # По умолчанию разрешаем планирование

def check_sequential_for_same_teacher(optimizer, teacher_name):
    """
    Проверяет возможность последовательного планирования для занятий с одним преподавателем.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        teacher_name: Имя преподавателя для проверки
        
    Returns:
        list: Список пар занятий, которые можно запланировать последовательно
    """
    sequential_pairs = []
    
    # Находим все занятия указанного преподавателя
    teacher_class_indices = []
    for idx, c in enumerate(optimizer.classes):
        if c.teacher == teacher_name:
            teacher_class_indices.append(idx)
    
    # Для каждой пары занятий проверяем возможность последовательного планирования
    for i, idx_i in enumerate(teacher_class_indices):
        c_i = optimizer.classes[idx_i]
        
        for j, idx_j in enumerate(teacher_class_indices[i+1:], i+1):
            c_j = optimizer.classes[idx_j]
            
            # Проверяем наличие общего дня
            if c_i.day and c_j.day and c_i.day != c_j.day:
                continue
                
            # Проверяем наличие общих групп
            shared_groups = set(c_i.get_groups()) & set(c_j.get_groups())
            if shared_groups:
                continue  # Пропускаем, если есть общие группы
                
            # Проверяем наличие общих аудиторий
            shared_rooms = set(c_i.possible_rooms) & set(c_j.possible_rooms)
            if not shared_rooms:
                continue  # Пропускаем, если нет общих аудиторий
                
            # Проверяем возможность последовательного планирования
            can_schedule, info = can_schedule_sequentially(c_i, c_j, idx_i, idx_j, verbose=False)
            
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
                sequential_pairs.append({
                    'class1_idx': idx_i,
                    'class2_idx': idx_j,
                    'class1': c_i,
                    'class2': c_j,
                    'info': info
                })
    
    return sequential_pairs


def subtract_intervals(window_start, window_end, busy):
    """
    Given window [window_start,window_end) and sorted non-overlapping busy intervals,
    returns list of maximal free intervals inside.

    Args:
        window_start (int): Start of the outer window (in minutes)
        window_end (int): End of the outer window (in minutes)
        busy (list): Sorted list of (start, end) tuples representing busy intervals

    Returns:
        list: List of (start, end) tuples representing free intervals

    Example:
        >>> subtract_intervals(60, 180, [(90,120),(130,140)])
        [(60,90),(120,130),(140,180)]
    """
    if not busy:
        # Если нет занятых интервалов, возвращаем всё окно
        return [(window_start, window_end)]
    
    free_intervals = []
    current_pos = window_start
    
    for busy_start, busy_end in busy:
        # Обрезаем занятый интервал границами окна
        busy_start = max(busy_start, window_start)
        busy_end = min(busy_end, window_end)
        
        # Если занятый интервал за пределами окна, пропускаем
        if busy_start >= window_end or busy_end <= window_start:
            continue
        
        # Если есть свободное место перед занятым интервалом
        if current_pos < busy_start:
            free_intervals.append((current_pos, busy_start))
        
        # Переходим к концу занятого интервала
        current_pos = max(current_pos, busy_end)
    
    # Если остается свободное место после последнего занятого интервала
    if current_pos < window_end:
        free_intervals.append((current_pos, window_end))
    
    return free_intervals

def _cache_and_return(cache_key, result, verbose=True):
    """Helper function to cache result and return it with optional logging."""
    global _analysis_cache
    _analysis_cache[cache_key] = result
    
    if verbose and result[1].get('reason'):
        can_schedule = result[0]
        reason = result[1]['reason']
        status = "Can" if can_schedule else "Cannot"
        print(f"RESULT: {status} schedule sequentially - {reason}")
    
    return result


def _analyze_fixed_vs_window(fixed_start, fixed_end, window_start, window_end, 
                           window_duration, window_pause_after, class1_label, class2_label, 
                           verbose, info, cache_and_return):
    """Анализирует случай: первое занятие фиксировано, второе с временным окном."""
    # Проверяем оба направления
    required_before_fixed = window_duration + window_pause_after
    available_before_fixed = fixed_start - window_start
    can_fit_before = available_before_fixed >= required_before_fixed
    
    required_after_fixed = window_duration
    available_after_fixed = window_end - fixed_end
    can_fit_after = available_after_fixed >= required_after_fixed
    
    if verbose:
        print(f"  CAN FIT BEFORE FIXED:")
        print(f"    Available: {available_before_fixed} min (window_start to fixed_start)")
        print(f"    Required: {required_before_fixed} min (window_duration + pause_after)")
        print(f"    Result: {'✓' if can_fit_before else '✗'}")
        print(f"  CAN FIT AFTER FIXED:")
        print(f"    Available: {available_after_fixed} min (fixed_end to window_end)")
        print(f"    Required: {required_after_fixed} min (window_duration)")
        print(f"    Result: {'✓' if can_fit_after else '✗'}")

    if can_fit_before and can_fit_after:
        info['reason'] = 'both_orders_possible'
        info['available_time'] = f"before: {available_before_fixed} min, after: {available_after_fixed} min"
        info['required_time'] = f"before: {required_before_fixed} min, after: {required_after_fixed} min"
        return cache_and_return(True, info)
    elif can_fit_before:
        info['reason'] = 'fits_before_fixed'
        info['available_time'] = f"before fixed: {available_before_fixed} min"
        info['required_time'] = required_before_fixed
        return cache_and_return(True, info)
    elif can_fit_after:
        info['reason'] = 'fits_after_fixed'
        info['available_time'] = f"after fixed: {available_after_fixed} min"
        info['required_time'] = required_after_fixed
        return cache_and_return(True, info)
    else:
        info['reason'] = 'not_enough_time_around_fixed'
        info['available_time'] = f"before: {available_before_fixed} min, after: {available_after_fixed} min"
        info['required_time'] = f"before: {required_before_fixed} min, after: {required_after_fixed} min"
        return cache_and_return(False, info)


def _analyze_window_vs_fixed(window_start, window_end, fixed_start, fixed_end,
                           window_duration, window_pause_after, class1_label, class2_label, 
                           verbose, info, cache_and_return):
    """Анализирует случай: первое занятие с временным окном, второе фиксировано."""
    # Проверяем оба направления
    required_before_fixed = window_duration + window_pause_after
    available_before_fixed = fixed_start - window_start
    can_fit_before = available_before_fixed >= required_before_fixed
    
    required_after_fixed = window_duration
    available_after_fixed = window_end - fixed_end
    can_fit_after = available_after_fixed >= required_after_fixed
    
    if verbose:
        print(f"  CAN FIT BEFORE FIXED:")
        print(f"    Available: {available_before_fixed} min (window_start to fixed_start)")
        print(f"    Required: {required_before_fixed} min (window_duration + pause_after)")
        print(f"    Result: {'✓' if can_fit_before else '✗'}")
        print(f"  CAN FIT AFTER FIXED:")
        print(f"    Available: {available_after_fixed} min (fixed_end to window_end)")
        print(f"    Required: {required_after_fixed} min (window_duration)")
        print(f"    Result: {'✓' if can_fit_after else '✗'}")

    if can_fit_before and can_fit_after:
        info['reason'] = 'both_orders_possible_window_first'
        return cache_and_return(True, info)
    elif can_fit_before:
        info['reason'] = 'window_fits_before_fixed'
        return cache_and_return(True, info)
    elif can_fit_after:
        info['reason'] = 'window_fits_after_fixed'
        return cache_and_return(True, info)
    else:
        info['reason'] = 'window_no_fit_around_fixed'
        return cache_and_return(False, info)


def _analyze_window_vs_window_bounds(bounds1, bounds2, c1, c2, class1_label, class2_label, 
                                   verbose, info, cache_and_return):
    """Анализирует случай: оба занятия с временными окнами используя effective bounds."""
    window1_start = time_to_minutes(bounds1.min_time)
    window1_end = time_to_minutes(bounds1.max_time)
    window2_start = time_to_minutes(bounds2.min_time)
    window2_end = time_to_minutes(bounds2.max_time)
    
    info['c1_start'] = bounds1.min_time
    info['c1_end'] = bounds1.max_time
    info['c2_start'] = bounds2.min_time
    info['c2_end'] = bounds2.max_time
    
    # Анализируем пересечения окон
    overlap_start = max(window1_start, window2_start)
    overlap_end = min(window1_end, window2_end)
    
    if overlap_start >= overlap_end:
        info['reason'] = 'no_time_overlap'
        if verbose:
            print(f"    No time overlap between windows")
        return cache_and_return(True, info)  # Нет пересечения - можно планировать
    
    overlap_duration = overlap_end - overlap_start
    total_required = c1.duration + c2.duration + getattr(c1, 'pause_after', 0) + getattr(c2, 'pause_before', 0)
    
    if verbose:
        print(f"    Overlap: {overlap_start}-{overlap_end} min ({overlap_duration} min)")
        print(f"    Total required: {total_required} min")
        print(f"    Overlap sufficient: {'✓' if overlap_duration >= total_required else '✗'}")
    
    if overlap_duration >= total_required:
        info['reason'] = 'sufficient_overlap_time'
        info['overlap_duration'] = overlap_duration
        info['required_time'] = total_required
        return cache_and_return(True, info)
    else:
        info['reason'] = 'insufficient_overlap_time'
        info['overlap_duration'] = overlap_duration
        info['required_time'] = total_required
        return cache_and_return(False, info)


def _analyze_fixed_vs_fixed(start1, end1, start2, end2, class1_label, class2_label, 
                          verbose, info, cache_and_return):
    """Анализирует случай: оба занятия фиксированы по времени."""
    if verbose:
        print(f"  Analyzing sequential placement:")
        print(f"    {class1_label} ends at {minutes_to_time(end1)}")
        print(f"    {class2_label} starts at {minutes_to_time(start2)}")
    
    # Проверяем порядок c1 -> c2
    gap_1_to_2 = start2 - end1
    can_c1_then_c2 = gap_1_to_2 >= 0
    
    # Проверяем порядок c2 -> c1  
    gap_2_to_1 = start1 - end2
    can_c2_then_c1 = gap_2_to_1 >= 0
    
    if verbose:
        print(f"    Gap {class1_label} -> {class2_label}: {gap_1_to_2} min ({'✓' if can_c1_then_c2 else '✗'})")
        print(f"    Gap {class2_label} -> {class1_label}: {gap_2_to_1} min ({'✓' if can_c2_then_c1 else '✗'})")
    
    if can_c1_then_c2 and can_c2_then_c1:
        info['reason'] = 'both_fixed_orders_possible'
        info['gap_1_to_2'] = gap_1_to_2
        info['gap_2_to_1'] = gap_2_to_1
        return cache_and_return(True, info)
    elif can_c1_then_c2:
        info['reason'] = 'fixed_order_c1_then_c2'
        info['gap'] = gap_1_to_2
        return cache_and_return(True, info)
    elif can_c2_then_c1:
        info['reason'] = 'fixed_order_c2_then_c1'
        info['gap'] = gap_2_to_1
        return cache_and_return(True, info)
    else:
        info['reason'] = 'fixed_times_conflict'
        info['overlap'] = max(end1 - start2, end2 - start1)
        return cache_and_return(False, info)
