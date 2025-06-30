"""
Module for creating optimization model variables.
"""
from ortools.sat.python import cp_model
from datetime import datetime, timedelta

def create_variables(optimizer):
    """Create variables for each class."""
    # Debug: вывод информации о слотах времени
    print("Available time slots:")
    for i, slot in enumerate(optimizer.time_slots):
        if i % 4 == 0:  # Print every 4th slot for readability
            print(f"  Slot {i}: {slot}")
    
    # Create variables for each class
    for idx, c in enumerate(optimizer.classes):
        # Create variables for day assignment (if not fixed)
        if c.day:
            # If day is specified, use a constant
            optimizer.day_vars[idx] = optimizer.day_indices[c.day]
        else:
            # Otherwise, create a variable
            optimizer.day_vars[idx] = optimizer.model.NewIntVar(
                0, len(optimizer.day_indices) - 1, f"day_{idx}")
        
        # Create variables for start time assignment
        if c.start_time:
            # Проверяем, есть ли время окончания (временное окно)
            if c.end_time:
                # Для удобства переведем времена в минуты с начала дня
                start_minutes = time_to_minutes(c.start_time)
                end_minutes = time_to_minutes(c.end_time)
                class_duration = c.duration

                print(f"\nProcessing class {c.subject} with time window {c.start_time}-{c.end_time}:")
                print(f"  Start minutes: {start_minutes}")
                print(f"  End minutes: {end_minutes}")
                print(f"  Class duration: {class_duration} min")
                print(f"  Available time for class: {end_minutes - start_minutes} min")
                
                # Найдем слоты для начала и конца временного окна
                start_slot = find_closest_slot(optimizer.time_slots, c.start_time)
                end_slot = find_closest_slot(optimizer.time_slots, c.end_time)
                
                # Вычисляем допустимый диапазон времени начала занятия
                max_start_minutes = end_minutes - class_duration
                max_start_time = minutes_to_time(max_start_minutes)
                max_start_slot = find_closest_slot(optimizer.time_slots, max_start_time)
                
                # Проверка валидности окна
                if max_start_minutes < start_minutes:
                    print(f"  WARNING: Class {c.subject} duration ({class_duration} min) doesn't fit in time window" + 
                          f" {c.start_time}-{c.end_time} ({end_minutes - start_minutes} min available)")
                    max_start_slot = start_slot
                else:
                    print(f"  Class fits in window. Latest possible start: {max_start_time} (slot {max_start_slot})")
                
                # Отладочный вывод для диагностики
                print(f"  Start slot range: {start_slot}-{max_start_slot}")
                print(f"  Time slot values: {optimizer.time_slots[start_slot]}-{optimizer.time_slots[max_start_slot]}")
                
                # Создаем переменную с ограничением на возможное время начала
                optimizer.start_vars[idx] = optimizer.model.NewIntVar(
                    start_slot, max_start_slot, f"start_{idx}")
                
                # Отметим, что это занятие имеет временное окно, а не фиксированное время начала
                c.has_time_window = True
                c.fixed_start_time = False
                print(f"Class {c.subject} has time window: {c.start_time}-{c.end_time}")

                #---Debug---
                # Для классов с временными окнами:
                print(f"DEBUG: Creating variable for window class {idx} '{c.subject}':")
                print(f"  - Window: {c.start_time}-{c.end_time}")
                print(f"  - Duration: {c.duration} min")
                print(f"  - Slot range: {start_slot}-{max_start_slot} ({optimizer.time_slots[start_slot]}-{optimizer.time_slots[max_start_slot]})")
                #-----------
            else:
                # Если конец временного окна не указан, используем фиксированное время начала
                start_slot = find_closest_slot(optimizer.time_slots, c.start_time)
                optimizer.start_vars[idx] = start_slot
                c.has_time_window = False
                c.fixed_start_time = True
                print(f"Class {c.subject} has fixed start time: {c.start_time} (slot {start_slot})")
        else:
            # Нет указанного времени начала, создаем переменную с полным диапазоном
            max_start = len(optimizer.time_slots) - 1
            slots_needed = (c.duration + c.pause_before + c.pause_after) // optimizer.time_interval
            if slots_needed > 0:
                max_start = max(0, len(optimizer.time_slots) - slots_needed - 1)
            
            optimizer.start_vars[idx] = optimizer.model.NewIntVar(
                0, max_start, f"start_{idx}")
            c.has_time_window = False
            c.fixed_start_time = False
            print(f"Class {c.subject} has no time constraints")

        # Добавим склонность к более поздним временам для занятий с окнами
        if c.has_time_window:
            # Проверим, есть ли у этого преподавателя другие занятия в этот день
            teacher_classes_same_day = [
                other_idx for other_idx, other_c in enumerate(optimizer.classes)
                if other_c.teacher == c.teacher and other_c.day == c.day and other_idx != idx and other_idx < idx
            ]
            
            if teacher_classes_same_day:
                # Добавляем мягкое ограничение - предпочтительней ставить занятие с окном позже
                # чем занятие с фиксированным временем того же преподавателя
                for other_idx in teacher_classes_same_day:
                    other_c = optimizer.classes[other_idx]
                    if other_c.has_fixed_time:  # Если другое занятие имеет фиксированное время
                        other_end_slot = optimizer.start_vars[other_idx]
                        if isinstance(other_end_slot, int):  # Если время начала фиксировано
                            other_end = other_end_slot + (other_c.duration + other_c.pause_after) // optimizer.time_interval
                            # Мягкое ограничение - предпочтительнее ставить занятие после другого
                            optimizer.model.Add(optimizer.start_vars[idx] >= other_end)
        
        # Create variables for room assignment
        if len(c.possible_rooms) == 1:
            # If only one room is possible, use a constant
            room_index = optimizer.rooms.index(c.main_room)
            optimizer.room_vars[idx] = room_index
        else:
            # Otherwise, create a variable for room selection
            possible_room_indices = [optimizer.rooms.index(room) for room in c.possible_rooms if room]
            # Используем Domain из модуля cp_model, а не из экземпляра модели
            optimizer.room_vars[idx] = optimizer.model.NewIntVarFromDomain(
                cp_model.Domain.FromValues(possible_room_indices), f"room_{idx}")
        
        # Variable to track if the class is assigned (always true for this model)
        optimizer.assigned_vars[idx] = optimizer.model.NewBoolVar(f"assigned_{idx}")
        optimizer.model.Add(optimizer.assigned_vars[idx] == 1)  # All classes must be assigned

def time_to_minutes(time_str):
    """Convert time string (HH:MM) to minutes since midnight."""
    if not time_str:
        return 0
    hours, minutes = map(int, time_str.split(':'))
    return hours * 60 + minutes

def minutes_to_time(minutes):
    """Convert minutes since midnight to time string (HH:MM)."""
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"

def find_closest_slot(time_slots, time_str):
    """Find the index of the closest time slot for a given time string."""
    target_minutes = time_to_minutes(time_str)
    best_slot = 0
    min_diff = float('inf')
    
    for i, slot in enumerate(time_slots):
        slot_minutes = time_to_minutes(slot)
        diff = abs(slot_minutes - target_minutes)
        if diff < min_diff:
            min_diff = diff
            best_slot = i
            
    return best_slot