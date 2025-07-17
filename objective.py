"""
Module for defining the objective function.
"""

def add_objective_function(optimizer):
    """Define the objective function to optimize the schedule."""
    num_classes = len(optimizer.classes)
    
    # 1. Minimize the number of teacher room changes
    teacher_changes = []
    
    # Group classes by teacher and day
    teacher_day_classes = {}
    for idx, c in enumerate(optimizer.classes):
        if not c.teacher:
            continue
            
        teacher = c.teacher
        if teacher not in teacher_day_classes:
            teacher_day_classes[teacher] = {}
        
        day_var = optimizer.day_vars[idx]
        if isinstance(day_var, int):
            day = day_var
            if day not in teacher_day_classes[teacher]:
                teacher_day_classes[teacher][day] = []
            teacher_day_classes[teacher][day].append(idx)
        else:
            # For classes with variable days, we need to consider all possibilities
            for day in range(len(optimizer.day_indices)):
                day_match = optimizer.model.NewBoolVar(f"day_match_{idx}_{day}")
                constraint_expr = optimizer.model.Add(day_var == day).OnlyEnforceIf(day_match)
                constraint_expr = optimizer.model.Add(day_var != day).OnlyEnforceIf(day_match.Not())
                
                if day not in teacher_day_classes[teacher]:
                    teacher_day_classes[teacher][day] = []
                
                # Add the class to this day's list (conditional on day_match)
                teacher_day_classes[teacher][day].append((idx, day_match))
    
    # For each teacher and day, count room changes
    for teacher, days in teacher_day_classes.items():
        for day, classes in days.items():
            # Skip if only one class
            if len(classes) <= 1:
                continue
            
            # Sort classes by start time
            if all(isinstance(item, int) for item in classes):
                # All fixed day classes
                sorted_classes = sorted(classes, key=lambda idx: 
                                  optimizer.start_vars[idx] if isinstance(optimizer.start_vars[idx], int) 
                                  else 0)  # Put variable starts first for now
                
                # Count room changes
                for i in range(len(sorted_classes) - 1):
                    curr_idx = sorted_classes[i]
                    next_idx = sorted_classes[i + 1]
                    
                    room_change = optimizer.model.NewBoolVar(f"room_change_{curr_idx}_{next_idx}")
                    if isinstance(optimizer.room_vars[curr_idx], int) and isinstance(optimizer.room_vars[next_idx], int):
                        # Both rooms are fixed - создаем явное сравнение
                        if optimizer.room_vars[curr_idx] != optimizer.room_vars[next_idx]:
                            constraint_expr = optimizer.model.Add(room_change == 1)
                        else:
                            constraint_expr = optimizer.model.Add(room_change == 0)
                    elif isinstance(optimizer.room_vars[curr_idx], int):
                        constraint_expr = optimizer.model.Add(optimizer.room_vars[next_idx] != optimizer.room_vars[curr_idx]).OnlyEnforceIf(room_change)
                        constraint_expr = optimizer.model.Add(optimizer.room_vars[next_idx] == optimizer.room_vars[curr_idx]).OnlyEnforceIf(room_change.Not())
                    elif isinstance(optimizer.room_vars[next_idx], int):
                        constraint_expr = optimizer.model.Add(optimizer.room_vars[curr_idx] != optimizer.room_vars[next_idx]).OnlyEnforceIf(room_change)
                        constraint_expr = optimizer.model.Add(optimizer.room_vars[curr_idx] == optimizer.room_vars[next_idx]).OnlyEnforceIf(room_change.Not())
                    else:
                        constraint_expr = optimizer.model.Add(optimizer.room_vars[curr_idx] != optimizer.room_vars[next_idx]).OnlyEnforceIf(room_change)
                        constraint_expr = optimizer.model.Add(optimizer.room_vars[curr_idx] == optimizer.room_vars[next_idx]).OnlyEnforceIf(room_change.Not())
                    
                    teacher_changes.append(room_change)
            else:
                # Some classes have variable days
                # This is more complex and depends on the specific problem constraints
                # For now, we'll simplify and just count potential changes
                pass
    
    # 2. Minimize empty time slots ("gaps") for teachers and groups
    gaps = []
    
    # For teachers
    for teacher, days in teacher_day_classes.items():
        for day, classes in days.items():
            # Skip if only one class
            if len(classes) <= 1:
                continue
            
            # Sort classes by start time (simplified for now)
            if all(isinstance(item, int) for item in classes):
                sorted_classes = sorted(classes, key=lambda idx: 
                                  optimizer.start_vars[idx] if isinstance(optimizer.start_vars[idx], int) 
                                  else 0)
                
                # Measure gaps between consecutive classes
                for i in range(len(sorted_classes) - 1):
                    curr_idx = sorted_classes[i]
                    next_idx = sorted_classes[i + 1]
                    
                    # Calculate expected gap size
                    if isinstance(optimizer.start_vars[curr_idx], int) and isinstance(optimizer.start_vars[next_idx], int):
                        # Both start times are fixed
                        curr_end = optimizer.start_vars[curr_idx] + (optimizer.classes[curr_idx].duration + 
                                                             optimizer.classes[curr_idx].pause_after) // optimizer.time_interval
                        next_start = optimizer.start_vars[next_idx] - (optimizer.classes[next_idx].pause_before // optimizer.time_interval)
                        
                        gap_size = next_start - curr_end
                        if gap_size > 0:
                            # We only care about minimizing gaps, not eliminating them
                            gaps.append(optimizer.model.NewConstant(gap_size))
                    else:
                        # For variable start times, create a gap variable
                        curr_end = optimizer.model.NewIntVar(0, len(optimizer.time_slots), f"end_{curr_idx}")
                        if isinstance(optimizer.start_vars[curr_idx], int):
                            curr_end_val = optimizer.start_vars[curr_idx] + (optimizer.classes[curr_idx].duration + 
                                                                    optimizer.classes[curr_idx].pause_after) // optimizer.time_interval
                            constraint_expr = optimizer.model.Add(curr_end == curr_end_val)
                        else:
                            curr_duration = (optimizer.classes[curr_idx].duration + 
                                           optimizer.classes[curr_idx].pause_after) // optimizer.time_interval
                            constraint_expr = optimizer.model.Add(curr_end == optimizer.start_vars[curr_idx] + curr_duration)
                        
                        next_start = optimizer.model.NewIntVar(0, len(optimizer.time_slots), f"effective_start_{next_idx}")
                        if isinstance(optimizer.start_vars[next_idx], int):
                            next_start_val = optimizer.start_vars[next_idx] - (optimizer.classes[next_idx].pause_before // optimizer.time_interval)
                            constraint_expr = optimizer.model.Add(next_start == next_start_val)
                        else:
                            next_pause = optimizer.classes[next_idx].pause_before // optimizer.time_interval
                            constraint_expr = optimizer.model.Add(next_start == optimizer.start_vars[next_idx] - next_pause)
                        
                        # Gap is the difference between next start and current end
                        gap = optimizer.model.NewIntVar(0, len(optimizer.time_slots), f"gap_{curr_idx}_{next_idx}")
                        constraint_expr = optimizer.model.Add(gap == next_start - curr_end)
                        
                        # Only consider positive gaps
                        positive_gap = optimizer.model.NewBoolVar(f"positive_gap_{curr_idx}_{next_idx}")
                        constraint_expr = optimizer.model.Add(gap > 0).OnlyEnforceIf(positive_gap)
                        constraint_expr = optimizer.model.Add(gap <= 0).OnlyEnforceIf(positive_gap.Not())
                        
                        # Conditional gap value
                        cond_gap = optimizer.model.NewIntVar(0, len(optimizer.time_slots), f"cond_gap_{curr_idx}_{next_idx}")
                        constraint_expr = optimizer.model.Add(cond_gap == gap).OnlyEnforceIf(positive_gap)
                        constraint_expr = optimizer.model.Add(cond_gap == 0).OnlyEnforceIf(positive_gap.Not())
                        
                        gaps.append(cond_gap)
    
    # 3. Define the objective function
    # We'll give more weight to room changes than to gaps
    objective_terms = []
    
    # Add teacher room changes (weight 10)
    for change in teacher_changes:
        objective_terms.append(change * 10)
    
    # Add gaps (weight 1)
    for gap in gaps:
        objective_terms.append(gap)
    
    # Добавляем веса для улучшения планирования с временными окнами
    try:
        from timewindow_adapter import add_objective_weights_for_timewindows
        additional_terms = add_objective_weights_for_timewindows(optimizer)
        objective_terms.extend(additional_terms)
    except ImportError:
        # Если модуль не найден, продолжаем без дополнительных весов
        pass

    # Minimize the sum
    optimizer.model.Minimize(sum(objective_terms))