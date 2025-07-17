from constraint_registry import ConstraintType
"""
Модуль для добавления ограничений для связанных занятий.

⚠️  ВНИМАНИЕ: Этот модуль ОТКЛЮЧЕН для предотвращения дублирующих ограничений!
⚠️  Все ограничения для цепочек теперь обрабатываются через chain_constraints.py

Функция build_linked_chains перенесена в linked_chain_utils.py
"""

def build_linked_chains(optimizer):
    """
    УСТАРЕВШАЯ функция - перенесена в linked_chain_utils.py
    
    ⚠️  ПРЕДУПРЕЖДЕНИЕ: Используйте linked_chain_utils.build_linked_chains()
    """
    print("⚠️  WARNING: build_linked_chains is deprecated. Use linked_chain_utils.build_linked_chains() instead")
    from linked_chain_utils import build_linked_chains as new_build_linked_chains
    return new_build_linked_chains(optimizer)

def add_linked_constraints(optimizer):
    """
    ⚠️  ОТКЛЮЧЕННАЯ ФУНКЦИЯ: предотвращение дублирующих ограничений
    
    Эта функция больше НЕ ИСПОЛЬЗУЕТСЯ для предотвращения конфликтов между
    linked_constraints.py и chain_constraints.py
    
    Все ограничения для цепочек теперь обрабатываются через:
    - chain_constraints.py (основные ограничения)
    - linked_chain_utils.py (утилиты)
    """
    print("⚠️  WARNING: add_linked_constraints() is DISABLED to prevent duplicate constraints!")
    print("   All linked class constraints are now handled by chain_constraints.py")
    print("   This function call is being ignored.")
    
    # НЕ добавляем ограничения - возвращаемся сразу
    return
    
    for idx, c in enumerate(optimizer.classes):
        if hasattr(c, 'linked_classes') and c.linked_classes:
            # Process linked classes (classes that must occur in sequence)
            prev_class = c
            prev_idx = idx
            
            for linked_class in c.linked_classes:
                try:
                    # Find the index of the linked class using our helper method
                    linked_idx = optimizer._find_class_index(linked_class)
                    
                    # Classes must be on the same day
                    if isinstance(optimizer.day_vars[prev_idx], int) and isinstance(optimizer.day_vars[linked_idx], int):
                        # Both days are fixed, verify they are the same
                        if optimizer.day_vars[prev_idx] != optimizer.day_vars[linked_idx]:
                            raise ValueError(f"Linked classes {prev_class.subject} and {linked_class.subject} "
                                           f"have different fixed days")
                    elif isinstance(optimizer.day_vars[prev_idx], int):
                        # Previous day is fixed, linked day must match
                        constraint_expr = optimizer.day_vars[linked_idx] == optimizer.day_vars[prev_idx]
                        optimizer.add_constraint(
                            constraint_expr=constraint_expr,
                            constraint_type=ConstraintType.LINKED_CLASSES,
                            origin_module=__name__,
                            origin_function="add_linked_constraints",
                            class_i=prev_idx,
                            class_j=linked_idx,
                            description=f"Linked classes same day (fixed prev): classes {prev_idx} and {linked_idx}",
                            variables_used=[f"day_vars[{linked_idx}]"]
                        )
                    elif isinstance(optimizer.day_vars[linked_idx], int):
                        # Linked day is fixed, previous day must match
                        constraint_expr = optimizer.day_vars[prev_idx] == optimizer.day_vars[linked_idx]
                        optimizer.add_constraint(
                            constraint_expr=constraint_expr,
                            constraint_type=ConstraintType.LINKED_CLASSES,
                            origin_module=__name__,
                            origin_function="add_linked_constraints",
                            class_i=prev_idx,
                            class_j=linked_idx,
                            description=f"Linked classes same day (fixed linked): classes {prev_idx} and {linked_idx}",
                            variables_used=[f"day_vars[{prev_idx}]"]
                        )
                    else:
                        # Neither day is fixed, they must be equal
                        constraint_expr = optimizer.day_vars[prev_idx] == optimizer.day_vars[linked_idx]
                        optimizer.add_constraint(
                            constraint_expr=constraint_expr,
                            constraint_type=ConstraintType.LINKED_CLASSES,
                            origin_module=__name__,
                            origin_function="add_linked_constraints",
                            class_i=prev_idx,
                            class_j=linked_idx,
                            description=f"Linked classes same day (both variable): classes {prev_idx} and {linked_idx}",
                            variables_used=[f"day_vars[{prev_idx}]", f"day_vars[{linked_idx}]"]
                        )
                    
                    # Second class must start after first class ends
                    if isinstance(optimizer.start_vars[prev_idx], int) and isinstance(optimizer.start_vars[linked_idx], int):
                        # Both start times are fixed, verify sequence
                        prev_end = optimizer.start_vars[prev_idx] + (prev_class.duration + prev_class.pause_after) // optimizer.time_interval
                        if prev_end + (linked_class.pause_before // optimizer.time_interval) > optimizer.start_vars[linked_idx]:
                            raise ValueError(f"Fixed start times for linked classes {prev_class.subject} and "
                                          f"{linked_class.subject} do not allow sufficient time between them")
                    elif isinstance(optimizer.start_vars[prev_idx], int):
                        # Previous start is fixed, calculate end time
                        prev_end = optimizer.start_vars[prev_idx] + (prev_class.duration + prev_class.pause_after) // optimizer.time_interval
                        min_linked_start = prev_end + (linked_class.pause_before // optimizer.time_interval)
                        constraint_expr = optimizer.start_vars[linked_idx] >= min_linked_start
                        optimizer.add_constraint(
                            constraint_expr=constraint_expr,
                            constraint_type=ConstraintType.LINKED_CLASSES,
                            origin_module=__name__,
                            origin_function="add_linked_constraints",
                            class_i=prev_idx,
                            class_j=linked_idx,
                            description=f"Linked sequence (fixed prev): class {prev_idx} ends before class {linked_idx} starts",
                            variables_used=[f"start_vars[{linked_idx}]"]
                        )
                    elif isinstance(optimizer.start_vars[linked_idx], int):
                        # Linked start is fixed, calculate latest previous end
                        max_prev_end = optimizer.start_vars[linked_idx] - (linked_class.pause_before // optimizer.time_interval)
                        slots_needed = (prev_class.duration + prev_class.pause_after) // optimizer.time_interval
                        max_prev_start = max_prev_end - slots_needed
                        constraint_expr = optimizer.start_vars[prev_idx] <= max_prev_start
                        optimizer.add_constraint(
                            constraint_expr=constraint_expr,
                            constraint_type=ConstraintType.LINKED_CLASSES,
                            origin_module=__name__,
                            origin_function="add_linked_constraints",
                            class_i=prev_idx,
                            class_j=linked_idx,
                            description=f"Linked sequence (fixed linked): class {prev_idx} ends before class {linked_idx} starts",
                            variables_used=[f"start_vars[{prev_idx}]"]
                        )
                    else:
                        # Neither start is fixed
                        # Calculate the number of time slots needed for the previous class
                        prev_slots = (prev_class.duration + prev_class.pause_after) // optimizer.time_interval
                        linked_pause_slots = linked_class.pause_before // optimizer.time_interval
                        
                        # Next class must start after previous class ends plus pause
                        constraint_expr = optimizer.start_vars[linked_idx] >= optimizer.start_vars[prev_idx] + prev_slots + linked_pause_slots
                        optimizer.add_constraint(
                            constraint_expr=constraint_expr,
                            constraint_type=ConstraintType.LINKED_CLASSES,
                            origin_module=__name__,
                            origin_function="add_linked_constraints",
                            class_i=prev_idx,
                            class_j=linked_idx,
                            description=f"Linked sequence (both variable): class {prev_idx} ends before class {linked_idx} starts",
                            variables_used=[f"start_vars[{prev_idx}]", f"start_vars[{linked_idx}]"]
                        )
                    
                    # Update for next iteration
                    prev_class = linked_class
                    prev_idx = linked_idx
                except ValueError as e:
                    print(f"Warning: Error processing linked class: {str(e)}")
                    # Continue with next linked class
                    continue