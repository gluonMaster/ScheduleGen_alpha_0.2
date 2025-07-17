"""
Модуль для анализа возможности последовательного планирования занятий.
Предоставляет функции для определения, могут ли занятия быть размещены последовательно
в одной аудитории или с одним преподавателем.
"""

from time_utils import time_to_minutes, minutes_to_time
from linked_chain_utils import collect_full_chain
from chain_scheduler import schedule_chain, chain_busy_intervals

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

def can_schedule_sequentially(c1, c2, idx1=None, idx2=None, verbose=True):
    """
    Проверяет, могут ли два занятия быть запланированы последовательно с учетом их временных ограничений.
    
    Args:
        c1: Первое занятие (ScheduleClass)
        c2: Второе занятие (ScheduleClass)
        idx1: Индекс первого занятия (для правильного логгирования)
        idx2: Индекс второго занятия (для правильного логгирования)
        verbose: Включить детальное логгирование (по умолчанию True)
        
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
    
    # Проверка наличия временных ограничений
    if not c1.start_time or not c2.start_time:
        info['reason'] = 'missing_time_info'
        if verbose:
            print(f"RESULT: Can schedule sequentially - {info['reason']}")
            print(f"  {class1_label} start_time: {c1.start_time}, {class2_label} start_time: {c2.start_time}")
        return cache_and_return(True, info)  # Если нет ограничений по времени, планирование возможно
    
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

    # Проверка случаев с фиксированным временем и временным окном
    if c1.start_time and not c1.end_time and c2.start_time and c2.end_time:
        # c1 фиксировано, c2 с окном
        fixed_start   = time_to_minutes(c1.start_time)
        fixed_end     = fixed_start + c1.duration + getattr(c1, 'pause_after', 0)
        window_start  = time_to_minutes(c2.start_time)
        window_end    = time_to_minutes(c2.end_time)
        
        print(f"FIXED vs WINDOW ANALYSIS:")
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
            print(f"RESULT: Cannot schedule sequentially - {info['reason']}")
            return cache_and_return(False, info)
            
    elif c2.start_time and not c2.end_time and c1.start_time and c1.end_time:
        # c2 фиксировано, c1 с окном
        fixed_start   = time_to_minutes(c2.start_time)
        fixed_end     = fixed_start + c2.duration + getattr(c2, 'pause_after', 0)
        window_start  = time_to_minutes(c1.start_time)
        window_end    = time_to_minutes(c1.end_time)
        
        print(f"WINDOW vs FIXED ANALYSIS:")
        print(f"  {class1_label} (window): {c1.start_time}-{c1.end_time} duration {c1.duration} min + pause_after {getattr(c1, 'pause_after', 0)} min")
        print(f"                    needs pause_before {getattr(c1, 'pause_before', 0)} min")
        print(f"  {class2_label} (fixed): {c2.start_time} duration {c2.duration} min + pause_after {getattr(c2, 'pause_after', 0)} min = ends at {minutes_to_time(fixed_end)}")
    
        # Проверяем оба направления
        required_before_fixed = c1.duration + getattr(c1, 'pause_after', 0)
        available_before_fixed = fixed_start - getattr(c2, 'pause_before', 0) - window_start
        can_fit_before = available_before_fixed >= required_before_fixed
        
        required_after_fixed = c1.duration + getattr(c1, 'pause_before', 0)
        available_after_fixed = window_end - fixed_end
        can_fit_after = available_after_fixed >= required_after_fixed
        
        print(f"  CAN FIT BEFORE FIXED:")
        print(f"    Available: {available_before_fixed} min (window_start to fixed_start - pause_before)")
        print(f"    Required: {required_before_fixed} min (c1_duration + pause_after)")
        print(f"    Result: {'✓' if can_fit_before else '✗'}")
        print(f"  CAN FIT AFTER FIXED:")
        print(f"    Available: {available_after_fixed} min (fixed_end to window_end)")
        print(f"    Required: {required_after_fixed} min (c1_duration + pause_before)")
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
            print(f"RESULT: Cannot schedule sequentially - {info['reason']}")
            return cache_and_return(False, info)
    
    elif c1.start_time and c1.end_time and c2.start_time and c2.end_time:
        # Оба занятия с временными окнами
        window1_start = time_to_minutes(c1.start_time)
        window1_end = time_to_minutes(c1.end_time)
        window2_start = time_to_minutes(c2.start_time)
        window2_end = time_to_minutes(c2.end_time)
        
        print(f"TIME WINDOWS:")
        print(f"  {class1_label}: {c1.start_time} - {c1.end_time} ({window1_start}-{window1_end} min)")
        print(f"  {class2_label}: {c2.start_time} - {c2.end_time} ({window2_start}-{window2_end} min)")
        
        info['c1_start'] = c1.start_time
        info['c1_end'] = c1.end_time
        info['c2_start'] = c2.start_time
        info['c2_end'] = c2.end_time
        
        # ИСПРАВЛЕНИЕ: Сначала проверяем неперекрывающиеся окна
        if window1_end <= window2_start:
            # Окно c1 полностью перед окном c2
            gap_time = window2_start - window1_end
            print(f"NON-OVERLAPPING WINDOWS: c1 before c2 (gap: {gap_time} min)")
            
            window1_available = window1_end - window1_start
            window2_available = window2_end - window2_start
            c1_needs_in_window = c1.duration + c1.pause_after
            c2_needs_in_window = c2.pause_before + c2.duration
            
            print(f"  Window 1 available: {window1_available} min, needs: {c1_needs_in_window} min")
            print(f"  Window 2 available: {window2_available} min, needs: {c2_needs_in_window} min")
            
            if window1_available >= c1_needs_in_window and window2_available >= c2_needs_in_window:
                info['reason'] = 'windows_separate_c1_before_c2'
                info['available_time'] = f"window1: {window1_available} min, window2: {window2_available} min, gap: {gap_time} min"
                info['required_time'] = f"window1: {c1_needs_in_window} min, window2: {c2_needs_in_window} min"
                info['gap_sufficient'] = True
                if verbose:
                    print(f"RESULT: Can schedule sequentially - {info['reason']}")
                return cache_and_return(True, info)
            else:
                info['reason'] = 'windows_separate_insufficient_space_in_windows'
                info['available_time'] = f"window1: {window1_available} min, window2: {window2_available} min"
                info['required_time'] = f"window1: {c1_needs_in_window} min, window2: {c2_needs_in_window} min"
                print(f"RESULT: Cannot schedule sequentially - {info['reason']}")
                return cache_and_return(False, info)
                
        elif window2_end <= window1_start:
            # Окно c2 полностью перед окном c1
            gap_time = window1_start - window2_end
            print(f"NON-OVERLAPPING WINDOWS: c2 before c1 (gap: {gap_time} min)")
            
            window1_available = window1_end - window1_start
            window2_available = window2_end - window2_start
            c2_needs_in_window = c2.duration + c2.pause_after
            c1_needs_in_window = c1.pause_before + c1.duration
            
            print(f"  Window 2 available: {window2_available} min, needs: {c2_needs_in_window} min")
            print(f"  Window 1 available: {window1_available} min, needs: {c1_needs_in_window} min")
            
            info['reason'] = 'windows_separate_wrong_order'
            info['available_time'] = f"window2: {window2_available} min, window1: {window1_available} min, gap: {gap_time} min"
            info['required_time'] = f"window2: {c2_needs_in_window} min, window1: {c1_needs_in_window} min"
            info['gap_between_windows'] = gap_time
            info['reverse_order_possible'] = (window2_available >= c2_needs_in_window and 
                                            window1_available >= c1_needs_in_window)
            if verbose:
                print(f"RESULT: Cannot schedule sequentially - {info['reason']} (reverse order possible: {info['reverse_order_possible']})")
            return cache_and_return(False, info)
        
        print(f"OVERLAPPING WINDOWS: analyzing constraints")
        
        # Детальное логгирование окон
        window1_duration = window1_end - window1_start
        window2_duration = window2_end - window2_start
        
        # Рассчитываем пересечение окон
        overlap_start = max(window1_start, window2_start)
        overlap_end = min(window1_end, window2_end)
        overlap_duration = max(0, overlap_end - overlap_start)
        
        # Рассчитываем общий span (от начала раннего до конца позднего окна)
        combined_start = min(window1_start, window2_start)
        combined_end = max(window1_end, window2_end)
        combined_span = combined_end - combined_start
        
        print(f"  WINDOW DETAILS:")
        print(f"    {class1_label}: window duration {window1_duration} min, lesson duration {c1.duration} min")
        print(f"             pause_after: {getattr(c1, 'pause_after', 0)} min, pause_before: {getattr(c1, 'pause_before', 0)} min")
        print(f"    {class2_label}: window duration {window2_duration} min, lesson duration {c2.duration} min")
        print(f"             pause_after: {getattr(c2, 'pause_after', 0)} min, pause_before: {getattr(c2, 'pause_before', 0)} min")
        print(f"    Window overlap: {overlap_duration} min ({minutes_to_time(overlap_start)}-{minutes_to_time(overlap_end)})")
        print(f"    Total span: {combined_span} min (from {minutes_to_time(combined_start)} to {minutes_to_time(combined_end)})")
        
        total_required_time = c1.duration + c2.duration + c1.pause_after + c2.pause_before
        print(f"    Sequential requirement: {total_required_time} min (both lessons + pauses)")
        
        # Сохраняем реалистичные значения для info
        info['available_time'] = f"overlap: {overlap_duration} min, span: {combined_span} min"
        info['required_time'] = total_required_time
        info['window_overlap'] = overlap_duration
        
        # Сценарий: Временные окна пересекаются - анализируем ограничения связанных занятий
        
        if c1_has_linked and not c2_has_linked:
            # c1 связанное (менее гибкое), c2 независимое (более гибкое)
            print(f"CONSTRAINT ANALYSIS: c1 linked, c2 flexible")
            
            c2_can_fit_before_c1 = (window2_start + c2.duration + c2.pause_after <= window1_start)
            c2_can_fit_after_c1 = (window1_end >= window2_start + c2.duration and 
                                   window1_end - c1.duration - c1.pause_after >= c2.duration + c2.pause_before)
            
            print(f"  c2 can fit before c1: {c2_can_fit_before_c1}")
            print(f"  c2 can fit after c1: {c2_can_fit_after_c1}")
            
            if c2_can_fit_before_c1:
                info['reason'] = 'flexible_c2_before_linked_c1'
                print(f"RESULT: Can schedule sequentially - {info['reason']}")
                return cache_and_return(True, info)
            elif c2_can_fit_after_c1:
                info['reason'] = 'flexible_c2_after_linked_c1'
                print(f"RESULT: Can schedule sequentially - {info['reason']}")
                return cache_and_return(True, info)
            else:
                info['reason'] = 'linked_c1_blocks_flexible_c2'
                print(f"RESULT: Cannot schedule sequentially - {info['reason']}")
                return cache_and_return(False, info)
                
        elif c2_has_linked and not c1_has_linked:
            # c2 связанное (менее гибкое), c1 независимое (более гибкое)
            print(f"CONSTRAINT ANALYSIS: c2 linked, c1 flexible")
            
            c1_can_fit_before_c2 = (window1_start + c1.duration + c1.pause_after <= window2_start)
            c1_can_fit_after_c2 = (window2_end >= window1_start + c1.duration and 
                                   window2_end - c2.duration - c2.pause_after >= c1.duration + c1.pause_before)
            
            print(f"  c1 can fit before c2: {c1_can_fit_before_c2}")
            print(f"  c1 can fit after c2: {c1_can_fit_after_c2}")
            
            if c1_can_fit_before_c2:
                info['reason'] = 'flexible_c1_before_linked_c2'
                print(f"RESULT: Can schedule sequentially - {info['reason']}")
                return cache_and_return(True, info)
            elif c1_can_fit_after_c2:
                info['reason'] = 'flexible_c1_after_linked_c2'
                print(f"RESULT: Can schedule sequentially - {info['reason']}")
                return cache_and_return(True, info)
            else:
                info['reason'] = 'linked_c2_blocks_flexible_c1'
                print(f"RESULT: Cannot schedule sequentially - {info['reason']}")
                return cache_and_return(False, info)
        
        elif c1_has_linked and c2_has_linked:
            # Оба занятия связанные - очень ограниченная гибкость
            print(f"CONSTRAINT ANALYSIS: both classes linked - limited flexibility")
            
            info['reason'] = 'both_linked_limited_flexibility'
            overlap_start = max(window1_start, window2_start)
            overlap_end = min(window1_end, window2_end)
            
            print(f"  Overlap window: {overlap_start}-{overlap_end} ({overlap_end - overlap_start} min)")
            print(f"  Required time: {total_required_time} min")
            
            if overlap_end > overlap_start and overlap_end - overlap_start >= total_required_time:
                print(f"RESULT: Can schedule sequentially - {info['reason']} (sufficient overlap)")
                return cache_and_return(True, info)
            else:
                print(f"RESULT: Cannot schedule sequentially - {info['reason']} (insufficient overlap)")
                return cache_and_return(False, info)
        
        else:
            # Оба занятия независимые - максимальная гибкость
            print(f"CONSTRAINT ANALYSIS: both classes independent - analyzing chain scheduling")
            
            try:
                # Собираем полную цепочку для c1, если он является частью цепочки
                if c1_has_linked:
                    chain = collect_full_chain_from_any_member(c1)
                    print(f"  Using c1 chain: {[cls.subject for cls in chain]}")
                else:
                    chain = [c1]  # Если c1 не в цепочке, цепочка состоит только из него
                    print(f"  Using single c1: {c1.subject}")
                
                # Создаем объект окна для c1
                class TimeWindow:
                    def __init__(self, start_min, end_min):
                        self.start = start_min
                        self.end = end_min
                
                c1_window = TimeWindow(
                    time_to_minutes(c1.start_time),
                    time_to_minutes(c1.end_time)
                )
                
                sched = schedule_chain(chain, c1_window)
                print(f"  Chain scheduled successfully: {[(cls.subject, sched[cls]) for cls in chain]}")
                
            except ValueError as e:
                info['reason'] = 'chain_overflows_window'
                print(f"RESULT: Cannot schedule sequentially - {info['reason']} ({e})")
                return cache_and_return(False, info)

            # построить busy для общего ресурса (teacher или room)
            busy = []
            if c1.teacher == c2.teacher:
                busy = chain_busy_intervals(sched)
                print(f"  Common teacher busy intervals: {busy}")

            # вычесть занятое время из окна c2
            ws = time_to_minutes(c2.start_time)
            we = time_to_minutes(c2.end_time)
            free = subtract_intervals(ws, we, busy)
            
            print(f"  RESOURCE GAP ANALYSIS (chain_and_resource_gap logic):")
            print(f"    c1 chain scheduled in: {[(cls.subject, f'{sched[cls][0]}-{sched[cls][1]}') for cls in chain]}")
            print(f"    c2 window: {ws}-{we} min ({minutes_to_time(ws)}-{minutes_to_time(we)})")
            print(f"    Free intervals in c2 window after subtracting busy: {free}")
            print(f"    c2 needs: {c2.duration} min + pause_after: {getattr(c2, 'pause_after', 0)} min = {c2.duration + getattr(c2, 'pause_after', 0)} min total")
            
            for fs, fe in free:
                available_in_slot = fe - fs
                required_for_c2 = c2.duration + getattr(c2, 'pause_after', 0)
                
                print(f"    Checking free slot {fs}-{fe} ({available_in_slot} min available vs {required_for_c2} min required)")
                
                if available_in_slot >= required_for_c2:
                    info['reason'] = 'chain_and_resource_gap'
                    info['c1_interval'] = sched[c1]
                    info['c2_interval'] = (fs, fs + c2.duration)
                    info['gap'] = fs - sched[c1][1]
                    
                    print(f"RESULT: Can schedule sequentially - {info['reason']}")
                    print(f"  ✓ c1 scheduled: {info['c1_interval']} ({minutes_to_time(info['c1_interval'][0])}-{minutes_to_time(info['c1_interval'][1])})")
                    print(f"  ✓ c2 can fit: {info['c2_interval']} ({minutes_to_time(info['c2_interval'][0])}-{minutes_to_time(info['c2_interval'][1])})")
                    print(f"  ✓ Gap between: {info['gap']} min")
                    print(f"  ✓ Available in slot: {available_in_slot} min, required: {required_for_c2} min")
                    return cache_and_return(True, info)
                else:
                    print(f"    ✗ Insufficient space in this slot")
            
            info['reason'] = 'no_free_slot'
            print(f"RESULT: Cannot schedule sequentially - {info['reason']}")
            print(f"  No free slot found that can accommodate c2 ({c2.duration} + {getattr(c2, 'pause_after', 0)} = {required_for_c2} min)")
            return cache_and_return(False, info)
            
    elif c1.start_time and not c1.end_time and c2.start_time and not c2.end_time:
        # Оба занятия с фиксированным временем
        start1 = time_to_minutes(c1.start_time)
        end1 = start1 + c1.duration + getattr(c1, 'pause_after', 0)
        start2 = time_to_minutes(c2.start_time)
        end2 = start2 + c2.duration + getattr(c2, 'pause_after', 0)
        
        print(f"BOTH FIXED TIMES ANALYSIS:")
        print(f"  {class1_label}: {c1.start_time} ({start1} min) duration {c1.duration} min + pause_after {getattr(c1, 'pause_after', 0)} min = ends at {minutes_to_time(end1)}")
        print(f"  {class2_label}: {c2.start_time} ({start2} min) duration {c2.duration} min + pause_after {getattr(c2, 'pause_after', 0)} min = ends at {minutes_to_time(end2)}")
        
        info['c1_start'] = c1.start_time
        info['c1_end'] = minutes_to_time(end1)
        info['c2_start'] = c2.start_time
        info['c2_end'] = minutes_to_time(end2)
        
        # Проверяем, пересекаются ли занятия
        overlap = start1 < end2 and start2 < end1
        if overlap:
            overlap_start = max(start1, start2)
            overlap_end = min(end1, end2)
            overlap_duration = overlap_end - overlap_start
            print(f"  OVERLAP DETECTED: {overlap_duration} min overlap ({minutes_to_time(overlap_start)}-{minutes_to_time(overlap_end)})")
            
            info['reason'] = 'fixed_times_overlap'
            info['overlap_duration'] = overlap_duration
            print(f"RESULT: Cannot schedule sequentially - {info['reason']}")
            return cache_and_return(False, info)
        else:
            gap_time = min(start2 - end1, start1 - end2) if start2 >= end1 or start1 >= end2 else 0
            print(f"  NO OVERLAP: Gap between classes: {gap_time} min")
            
            info['reason'] = 'fixed_times_no_overlap'
            info['gap_time'] = gap_time
            print(f"RESULT: Can schedule sequentially - {info['reason']}")
            return cache_and_return(True, info)
    
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
