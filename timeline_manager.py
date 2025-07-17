"""
Модуль для управления временной шкалой и размещения занятий.

Этот модуль предоставляет функциональность для создания временной шкалы дня,
работы с "якорными" фиксированными занятиями и поиска свободных слотов
для размещения занятий с временными окнами.
"""

from time_utils import time_to_minutes, minutes_to_time
from timewindow_utils import find_slot_for_time


class Timeline:
    """Класс для представления временной шкалы дня с фиксированными занятиями как "якорями"."""
    
    def __init__(self, day, common_window_start=None, common_window_end=None):
        """
        Инициализирует временную шкалу для дня.
        
        Args:
            day: День недели
            common_window_start: Начало общего временного окна в минутах (опционально)
            common_window_end: Конец общего временного окна в минутах (опционально)
        """
        self.day = day
        self.anchors = []  # Список фиксированных занятий как "якорей"
        self.free_slots = []  # Список свободных временных слотов
        self.common_window_start = common_window_start or 8 * 60  # 8:00 по умолчанию
        self.common_window_end = common_window_end or 20 * 60  # 20:00 по умолчанию
    
    def add_anchor(self, idx, class_obj):
        """
        Добавляет фиксированное занятие как "якорь" во временную шкалу.
        
        Args:
            idx: Индекс занятия
            class_obj: Объект занятия с фиксированным временем
        """
        if not class_obj.start_time or class_obj.end_time:
            raise ValueError(f"Class {idx} is not a fixed-time class")
        
        start_min = time_to_minutes(class_obj.start_time)
        end_min = start_min + class_obj.duration + class_obj.pause_after
        
        self.anchors.append({
            'idx': idx,
            'class': class_obj,
            'start_min': start_min,
            'end_min': end_min
        })
        
        # Сортируем якоря по времени начала
        self.anchors.sort(key=lambda x: x['start_min'])
    
    def calculate_free_slots(self):
        """
        Рассчитывает свободные временные слоты между фиксированными занятиями.
        
        Returns:
            list: Список кортежей (start_min, end_min) свободных слотов
        """
        self.free_slots = []
        
        if not self.anchors:
            # Если нет фиксированных занятий, весь общий временной диапазон свободен
            self.free_slots.append((self.common_window_start, self.common_window_end))
            return self.free_slots
        
        # Слот до первого фиксированного занятия
        first_start = self.anchors[0]['start_min']
        if self.common_window_start < first_start - 5:  # 5 минут буфер
            slot_start = self.common_window_start
            slot_end = first_start - 5
            
            # Ограничиваем слот пределами общего временного окна
            if slot_start < self.common_window_end and slot_end > self.common_window_start:
                actual_start = max(slot_start, self.common_window_start)
                actual_end = min(slot_end, self.common_window_end)
                if actual_end > actual_start:
                    self.free_slots.append((actual_start, actual_end))
        
        # Слоты между фиксированными занятиями
        for i in range(len(self.anchors) - 1):
            current_end = self.anchors[i]['end_min'] + 5  # 5 минут буфер
            next_start = self.anchors[i + 1]['start_min'] - 5  # 5 минут буфер
            
            # Ограничиваем слот пределами общего временного окна
            if current_end < self.common_window_end and next_start > self.common_window_start:
                actual_start = max(current_end, self.common_window_start)
                actual_end = min(next_start, self.common_window_end)
                if actual_end > actual_start:
                    self.free_slots.append((actual_start, actual_end))
        
        # Слот после последнего фиксированного занятия
        last_end = self.anchors[-1]['end_min'] + 5  # 5 минут буфер
        if last_end < self.common_window_end:
            actual_start = max(last_end, self.common_window_start)
            actual_end = self.common_window_end
            if actual_end > actual_start:
                self.free_slots.append((actual_start, actual_end))
        
        return self.free_slots
    
    def find_best_slot(self, class_obj, prefer_early=True):
        """
        Находит лучший свободный слот для размещения занятия с временным окном.
        
        Args:
            class_obj: Объект занятия с временным окном
            prefer_early: Предпочитать более раннее размещение
            
        Returns:
            dict или None: Информация о найденном слоте или None если не найден
        """
        if not class_obj.start_time or not class_obj.end_time:
            raise ValueError("Class must have a time window")
        
        window_start = time_to_minutes(class_obj.start_time)
        window_end = time_to_minutes(class_obj.end_time)
        
        best_slot = None
        best_fit = 0
        
        for slot_start, slot_end in self.free_slots:
            # Находим пересечение слота и временного окна
            overlap_start = max(slot_start, window_start)
            overlap_end = min(slot_end, window_end)
            overlap_size = overlap_end - overlap_start
            
            # Если занятие помещается в слот
            if overlap_size >= class_obj.duration:
                if overlap_size > best_fit or (overlap_size == best_fit and prefer_early and slot_start < best_slot['slot_start']):
                    best_slot = {
                        'slot_start': slot_start,
                        'slot_end': slot_end,
                        'overlap_start': overlap_start,
                        'overlap_end': overlap_end,
                        'overlap_size': overlap_size,
                        'placement_start': overlap_start if prefer_early else overlap_end - class_obj.duration,
                        'placement_end': (overlap_start if prefer_early else overlap_end - class_obj.duration) + class_obj.duration
                    }
                    best_fit = overlap_size
        
        return best_slot
    
    def reserve_slot(self, slot_info, class_obj):
        """
        Резервирует слот для занятия и обновляет список свободных слотов.
        
        Args:
            slot_info: Информация о слоте из find_best_slot
            class_obj: Объект размещаемого занятия
        """
        if not slot_info:
            return
        
        slot_start = slot_info['slot_start']
        slot_end = slot_info['slot_end']
        placement_start = slot_info['placement_start']
        placement_end = placement_start + class_obj.duration + class_obj.pause_after
        
        # Удаляем использованный слот
        if (slot_start, slot_end) in self.free_slots:
            self.free_slots.remove((slot_start, slot_end))
        
        # Добавляем оставшиеся части слота
        # Часть до размещенного занятия
        if placement_start > slot_start + 5:  # 5 минут буфер
            self.free_slots.append((slot_start, placement_start - 5))
        
        # Часть после размещенного занятия
        if placement_end + 5 < slot_end:  # 5 минут буфер
            self.free_slots.append((placement_end + 5, slot_end))
        
        # Сортируем слоты по времени начала
        self.free_slots.sort()
    
    def get_debug_info(self):
        """Возвращает отладочную информацию о временной шкале."""
        info = {
            'day': self.day,
            'common_window': f"{minutes_to_time(self.common_window_start)}-{minutes_to_time(self.common_window_end)}",
            'anchors': [],
            'free_slots': []
        }
        
        for anchor in self.anchors:
            info['anchors'].append({
                'idx': anchor['idx'],
                'time': f"{minutes_to_time(anchor['start_min'])}-{minutes_to_time(anchor['end_min'])}",
                'subject': getattr(anchor['class'], 'subject', 'Unknown')
            })
        
        for start_min, end_min in self.free_slots:
            info['free_slots'].append({
                'time': f"{minutes_to_time(start_min)}-{minutes_to_time(end_min)}",
                'duration': end_min - start_min
            })
        
        return info


def create_timeline(optimizer, day, class_list=None):
    """
    Создает временную шкалу для дня с фиксированными занятиями как "якорями".
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        day: День недели
        class_list: Список кортежей (idx, class_obj) для анализа (опционально)
        
    Returns:
        Timeline: Объект временной шкалы
    """
    if class_list is None:
        # Берем все занятия дня
        class_list = [(idx, c) for idx, c in enumerate(optimizer.classes) if c.day == day]
    
    # Разделение на фиксированные и оконные занятия
    fixed_classes = [(idx, c) for idx, c in class_list if c.start_time and not c.end_time]
    window_classes = [(idx, c) for idx, c in class_list if c.start_time and c.end_time]
    
    # Определяем общее временное окно для всех оконных занятий
    common_window_start = 8 * 60  # 8:00 по умолчанию
    common_window_end = 20 * 60   # 20:00 по умолчанию
    
    if window_classes:
        common_window_start = max(time_to_minutes(c.start_time) for _, c in window_classes)
        common_window_end = min(time_to_minutes(c.end_time) for _, c in window_classes)
    
    # Создаем временную шкалу
    timeline = Timeline(day, common_window_start, common_window_end)
    
    # Добавляем фиксированные занятия как якоря
    for idx, c in fixed_classes:
        timeline.add_anchor(idx, c)
    
    # Рассчитываем свободные слоты
    timeline.calculate_free_slots()
    
    return timeline


def find_free_slots(timeline, window_start_minutes=None, window_end_minutes=None):
    """
    Возвращает список свободных слотов в заданном временном окне.
    
    Args:
        timeline: Объект Timeline
        window_start_minutes: Начало временного окна в минутах (опционально)
        window_end_minutes: Конец временного окна в минутах (опционально)
        
    Returns:
        list: Список кортежей (start_min, end_min) свободных слотов
    """
    if window_start_minutes is None:
        window_start_minutes = timeline.common_window_start
    if window_end_minutes is None:
        window_end_minutes = timeline.common_window_end
    
    filtered_slots = []
    for slot_start, slot_end in timeline.free_slots:
        # Находим пересечение слота с заданным временным окном
        overlap_start = max(slot_start, window_start_minutes)
        overlap_end = min(slot_end, window_end_minutes)
        
        if overlap_end > overlap_start:
            filtered_slots.append((overlap_start, overlap_end))
    
    return filtered_slots


def check_slot_conflicts(optimizer, timeline, start_slot, duration_slots):
    """
    Проверяет, не создаст ли размещение занятия в указанном слоте конфликтов.
    
    Args:
        optimizer: Экземпляр ScheduleOptimizer
        timeline: Объект Timeline
        start_slot: Индекс начального временного слота
        duration_slots: Длительность в слотах
        
    Returns:
        bool: True, если конфликтов нет
    """
    if start_slot < 0 or start_slot >= len(optimizer.time_slots):
        return False
    
    if start_slot + duration_slots > len(optimizer.time_slots):
        return False
    
    start_time = optimizer.time_slots[start_slot]
    start_minutes = time_to_minutes(start_time)
    end_minutes = start_minutes + (duration_slots * optimizer.time_interval)
    
    # Проверяем конфликты с фиксированными занятиями (якорями)
    for anchor in timeline.anchors:
        anchor_start = anchor['start_min']
        anchor_end = anchor['end_min']
        
        # Проверяем пересечение временных интервалов
        if start_minutes < anchor_end and end_minutes > anchor_start:
            return False
    
    return True


def get_timeline_debug_info(timeline):
    """
    Возвращает отладочную информацию о временной шкале в удобном формате.
    
    Args:
        timeline: Объект Timeline
        
    Returns:
        str: Форматированная отладочная информация
    """
    debug_info = timeline.get_debug_info()
    
    lines = [
        f"Timeline for {debug_info['day']}:",
        f"  Common window: {debug_info['common_window']}",
        f"  Fixed classes (anchors): {len(debug_info['anchors'])}",
    ]
    
    for anchor in debug_info['anchors']:
        lines.append(f"    Class {anchor['idx']}: {anchor['time']} ({anchor['subject']})")
    
    lines.append(f"  Free slots: {len(debug_info['free_slots'])}")
    for slot in debug_info['free_slots']:
        lines.append(f"    {slot['time']} ({slot['duration']} min)")
    
    return "\n".join(lines)
