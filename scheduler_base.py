from ortools.sat.python import cp_model
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Set, Any

# Импорт из локальных модулей
from reader import ScheduleReader, ScheduleClass
from sequential_scheduling_checker import enforce_window_chain_sequencing
from constraint_registry import ConstraintRegistry, ConstraintType

class ScheduleOptimizer:
    """
    Class that uses OR-Tools CP-SAT solver to create an optimized schedule
    based on the input constraints.
    """
    
    def __init__(self, classes: List[ScheduleClass], time_interval: int = 15):
        """
        Initialize the scheduler with the given classes and time interval.
        
        Args:
            classes: List of ScheduleClass objects to schedule
            time_interval: Time interval in minutes for scheduling (default: 15)
        """
        self.classes = classes
        self.time_interval = time_interval
        
        # Create a map of classes by subject+teacher+group+day+time for easy lookup
        self.class_map = {}
        for idx, c in enumerate(classes):
            # Include group and end_time to avoid key collisions
            key = f"{c.subject}_{c.teacher}_{c.group}_{c.day}_{c.start_time}_{c.end_time}"
            self.class_map[key] = idx
        
        # Create direct object-to-index mapping for more reliable lookups
        self.object_index_map = {c: idx for idx, c in enumerate(classes)}
        
        print(f"Created class_map with {len(self.class_map)} entries.")
        print(f"Created object_index_map with {len(self.object_index_map)} entries.")
        print(f"Classes list has {len(classes)} elements.")
        
        # Check for any remaining key collisions and warn about them
        if len(self.class_map) < len(classes):
            print(f"WARNING: Key collision detected! class_map has {len(self.class_map)} entries but classes list has {len(classes)} elements.")
            collision_keys = {}
            for idx, c in enumerate(classes):
                key = f"{c.subject}_{c.teacher}_{c.group}_{c.day}_{c.start_time}_{c.end_time}"
                if key in collision_keys:
                    print(f"  Collision: Key '{key}' used by classes {collision_keys[key]} and {idx}")
                else:
                    collision_keys[key] = idx
        
        # Extract all unique resources
        self.teachers = sorted(set(c.teacher for c in classes if c.teacher))
        self.rooms = sorted(set(room for c in classes for room in c.possible_rooms if room))
        self.groups = sorted(set(group for c in classes for group in c.get_groups() if group))
        self.days = sorted(set(c.day for c in classes if c.day))
        
        # Map days to indices
        day_order = ["Mo", "Di", "Mi", "Do", "Fr", "Sa"]
        self.day_indices = {day: idx for idx, day in enumerate(day_order) if day in self.days}
        
        # Generate time slots
        self.time_slots = self._generate_time_slots()
        self.time_slot_indices = {slot: idx for idx, slot in enumerate(self.time_slots)}
        
        # Initialize the model and variables
        self.model = None
        self.assigned_vars = {}
        self.start_vars = {}
        self.room_vars = {}
        self.day_vars = {}
        
        # Initialize constraint registry for tracking all constraints
        self.constraint_registry = ConstraintRegistry()
        
        # Results
        self.solution = None
    
    def _generate_time_slots(self) -> List[str]:
        """Generate time slots for the schedule."""
        time_slots = []
        start_time = datetime.strptime("08:00", "%H:%M")
        end_time = datetime.strptime("20:00", "%H:%M")
        
        current = start_time
        while current <= end_time:
            time_slots.append(current.strftime("%H:%M"))
            current += timedelta(minutes=self.time_interval)
        
        return time_slots
    
    def _time_to_minutes(self, time_str: str) -> int:
        """Convert a time string (HH:MM) to minutes since start of day."""
        if not time_str:
            return 0
        
        hours, minutes = map(int, time_str.split(':'))
        return hours * 60 + minutes
    
    def _get_time_slot_index(self, time_str: str) -> int:
        """Get the index of the time slot for a given time string."""
        # Find the closest time slot without going past the requested time
        time_minutes = self._time_to_minutes(time_str)
        for i, slot in enumerate(self.time_slots):
            slot_minutes = self._time_to_minutes(slot)
            if slot_minutes >= time_minutes:
                return i
        
        # If we're past the last slot, return the last one
        return len(self.time_slots) - 1
    
    def _calculate_overlapping_intervals(self, start1: int, duration1: int, start2: int, duration2: int) -> int:
        """Calculate the overlap between two intervals."""
        end1 = start1 + duration1
        end2 = start2 + duration2
        return max(0, min(end1, end2) - max(start1, start2))
    
    def _find_class_index(self, c: ScheduleClass) -> int:
        """Find the index of a class in the classes list using object mapping first, then string key."""
        # Try direct object lookup first (most reliable)
        if c in self.object_index_map:
            return self.object_index_map[c]
        
        # Fallback to string key lookup with improved key format
        key = f"{c.subject}_{c.teacher}_{c.group}_{c.day}_{c.start_time}_{c.end_time}"
        if key in self.class_map:
            return self.class_map[key]
        
        # Fallback for classes not found by either method - try to find by attributes
        for idx, cls in enumerate(self.classes):
            if (cls.subject == c.subject and cls.teacher == c.teacher and 
                cls.group == c.group and cls.day == c.day and 
                cls.start_time == c.start_time and cls.end_time == c.end_time):
                print(f"WARNING: Found class by attribute comparison for {key}")
                return idx
        
        # If we can't find the class, print details and raise an error
        print(f"ERROR: Could not find linked class in the classes list:")
        print(f"  Subject: {c.subject}")
        print(f"  Teacher: {c.teacher}")
        print(f"  Group: {c.group}")
        print(f"  Day: {c.day}")
        print(f"  Start Time: {c.start_time}")
        print(f"  End Time: {c.end_time}")
        print(f"  Key: {key}")
        print(f"Available classes:")
        for idx, cls in enumerate(self.classes):
            print(f"  {idx}: {cls.subject} - {cls.teacher} - {cls.group} - {cls.day} - {cls.start_time} - {cls.end_time}")
        
        raise ValueError(f"Could not find linked class {c} in the classes list")
    
    def add_constraint(self, constraint_expr, constraint_type: ConstraintType, 
                      origin_module: str, origin_function: str,
                      class_i: Optional[int] = None, class_j: Optional[int] = None,
                      description: str = "", variables_used: List[str] = None):
        """
        Централизованная обертка для добавления ограничений с отслеживанием.
        
        Args:
            constraint_expr: CP-SAT ограничение
            constraint_type: Тип ограничения из ConstraintType
            origin_module: Модуль, из которого добавлено ограничение
            origin_function: Функция, из которой добавлено ограничение
            class_i, class_j: Индексы классов (если применимо)
            description: Описание ограничения
            variables_used: Список использованных переменных
            
        Returns:
            ConstraintInfo: Информация о добавленном ограничении
        """
        import inspect
        
        # Автоматическое определение origin_module и origin_function если не указаны
        if origin_module == "auto" or origin_function == "auto":
            frame = inspect.currentframe().f_back
            if origin_module == "auto":
                origin_module = frame.f_globals.get('__name__', 'unknown')
            if origin_function == "auto":
                origin_function = frame.f_code.co_name
        
        # Извлечение имен переменных для отслеживания
        if variables_used is None:
            variables_used = []
            
            # Попытка извлечь переменные из ограничения
            if hasattr(constraint_expr, 'variables'):
                variables_used = [str(var) for var in constraint_expr.variables]
            
            # Дополнительная попытка для классов с известными индексами
            if class_i is not None or class_j is not None:
                # Добавляем стандартные переменные для классов
                if class_i is not None:
                    variables_used.extend([
                        f"start_vars[{class_i}]",
                        f"day_vars[{class_i}]",
                        f"room_vars[{class_i}]",
                        f"assigned_vars[{class_i}]"
                    ])
                if class_j is not None:
                    variables_used.extend([
                        f"start_vars[{class_j}]",
                        f"day_vars[{class_j}]",
                        f"room_vars[{class_j}]",
                        f"assigned_vars[{class_j}]"
                    ])
                
                # Удаляем дубликаты
                variables_used = list(set(variables_used))
            
            # Если все еще нет переменных, попытка автоматического определения
            if not variables_used:
                constraint_str = str(constraint_expr)
                # Ищем паттерны переменных в строке ограничения
                import re
                var_patterns = [
                    r'start_vars\[\d+\]',
                    r'day_vars\[\d+\]',
                    r'room_vars\[\d+\]',
                    r'assigned_vars\[\d+\]',
                    r'i_before_j_\d+_\d+',
                    r'same_room_\d+_\d+',
                    r'time_overlap_\d+_\d+',
                    r'conflict_\d+_\d+'
                ]
                
                for pattern in var_patterns:
                    matches = re.findall(pattern, constraint_str)
                    variables_used.extend(matches)
                
                # Удаляем дубликаты
                variables_used = list(set(variables_used))
        
        # Улучшаем описание на основе типа ограничения и доступных данных
        if not description:
            if constraint_type == ConstraintType.CHAIN_ORDERING and class_i is not None and class_j is not None:
                description = f"Chain ordering: class {class_i} before class {class_j}"
            elif constraint_type == ConstraintType.SEPARATION and class_i is not None and class_j is not None:
                description = f"Time separation: classes {class_i} and {class_j}"
            elif constraint_type == ConstraintType.RESOURCE_CONFLICT and class_i is not None and class_j is not None:
                description = f"Resource conflict prevention: classes {class_i} and {class_j}"
            elif constraint_type == ConstraintType.TIME_WINDOW and class_i is not None:
                description = f"Time window constraint: class {class_i}"
            elif constraint_type == ConstraintType.FIXED_TIME and class_i is not None:
                description = f"Fixed time constraint: class {class_i}"
            else:
                description = f"{constraint_type.value} constraint"
        
        # Добавление в реестр
        constraint_info = self.constraint_registry.add_constraint(
            constraint_expr=constraint_expr,
            constraint_type=constraint_type,
            origin_module=origin_module,
            origin_function=origin_function,
            class_i=class_i,
            class_j=class_j,
            description=description,
            variables_used=variables_used
        )
        
        # ВАЖНО: Добавляем ограничение в CP-SAT модель (если еще не добавлено)
        if hasattr(constraint_expr, 'OnlyEnforceIf') or hasattr(constraint_expr, 'Not'):
            # Это уже добавленное ограничение, возвращаем как есть
            actual_constraint = constraint_expr
        else:
            # Это выражение, нужно добавить в модель
            actual_constraint = self.model.Add(constraint_expr)
        
        print(f"  ✓ Added constraint {constraint_info.constraint_id}: {description}")
        return actual_constraint  # Возвращаем фактическое ограничение CP-SAT
    
    def skip_constraint(self, constraint_type: ConstraintType, 
                       origin_module: str, origin_function: str,
                       class_i: Optional[int] = None, class_j: Optional[int] = None,
                       reason: str = ""):
        """
        Регистрирует пропущенное ограничение.
        
        Args:
            constraint_type: Тип ограничения
            origin_module: Модуль, из которого должно было быть добавлено ограничение
            origin_function: Функция, из которой должно было быть добавлено ограничение
            class_i, class_j: Индексы классов (если применимо)
            reason: Причина пропуска
        """
        import inspect
        
        # Автоматическое определение origin_module и origin_function если не указаны
        if origin_module == "auto" or origin_function == "auto":
            frame = inspect.currentframe().f_back
            if origin_module == "auto":
                origin_module = frame.f_globals.get('__name__', 'unknown')
            if origin_function == "auto":
                origin_function = frame.f_code.co_name
        
        self.constraint_registry.skip_constraint(
            constraint_type=constraint_type,
            origin_module=origin_module,
            origin_function=origin_function,
            class_i=class_i,
            class_j=class_j,
            reason=reason
        )
        
        print(f"  ⚠️  Skipped constraint {constraint_type.value}: {reason}")
    
    def add_constraint_exception(self, class_i: int, class_j: int, reason: str):
        """
        Добавляет исключение для пары классов.
        
        Args:
            class_i, class_j: Индексы классов
            reason: Причина исключения
        """
        self.constraint_registry.add_exception(class_i, class_j, reason)
        print(f"  🚫 Added constraint exception for classes {class_i} ↔ {class_j}: {reason}")
    
    def detect_constraint_conflict(self, constraint_ids: List[str], conflict_type: str,
                                 description: str, classes_involved: List[int]):
        """
        Регистрирует обнаруженный конфликт ограничений.
        
        Args:
            constraint_ids: Список ID конфликтующих ограничений
            conflict_type: Тип конфликта
            description: Описание конфликта
            classes_involved: Список вовлеченных классов
        """
        self.constraint_registry.detect_conflict(
            constraint_ids=constraint_ids,
            conflict_type=conflict_type,
            description=description,
            classes_involved=classes_involved
        )
        print(f"  ⚠️  Detected constraint conflict: {description}")

    def build_model(self):
        """Build the constraint programming model."""
        from model_variables import create_variables
        from constraints import add_linked_constraints, add_resource_conflict_constraints
        from objective import add_objective_function
        
        self.model = cp_model.CpModel()
        
        # Create variables for classes
        create_variables(self)
        
        # Add constraints for linked classes
        add_linked_constraints(self)
        
        # Add constraints to prevent resource conflicts
        add_resource_conflict_constraints(self)
   
        # Add objective function
        add_objective_function(self)
    
    def solve(self, time_limit_seconds=60):
        """
        Solve the scheduling problem.
        
        Args:
            time_limit_seconds: Maximum solving time in seconds
            
        Returns:
            True if a solution was found, False otherwise
        """
        # Очищаем кеши перед новой оптимизацией
        from sequential_scheduling import clear_analysis_cache
        clear_analysis_cache()
        
        if self.model is None:
            self.build_model()

        # Добавить защиту от повторного применения улучшений временных окон
        if not hasattr(self, 'timewindow_already_processed'):
            # НОВОЕ: Обнаружение циклов перед применением ограничений
            try:
                from conflict_detector import detect_constraint_cycles, prevent_constraint_cycles
                cycles = detect_constraint_cycles(self)
                if cycles:
                    prevent_constraint_cycles(self, cycles)
            except ImportError:
                print("Warning: conflict_detector module not found, skipping cycle detection")
            
            try:
                from timewindow_adapter import apply_timewindow_improvements
                apply_timewindow_improvements(self)
                self.timewindow_already_processed = True
                print("DEBUG: Applied timewindow improvements")
            except ImportError:
                print("Warning: timewindow_adapter module not found, skipping timewindow improvements")
        else:
            print("DEBUG: Timewindow improvements already applied, skipping")
        
        # Create the solver
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit_seconds
        
        # Добавляем логирование состояния модели
        print(f"\n📊 MODEL STATISTICS:")
        print(f"  Variables: {len(self.assigned_vars)} assigned, {len(self.start_vars)} start, {len(self.room_vars)} room, {len(self.day_vars)} day")
        print(f"  Constraints: {self.constraint_registry.total_added} added, {self.constraint_registry.total_skipped} skipped")
        
        # Отчет о типах ограничений
        stats = self.constraint_registry.get_statistics()
        print(f"  Constraint types: {', '.join([f'{k}: {v}' for k, v in stats['by_type'].items()])}")
        
        # Solve the problem
        print(f"\n🚀 Starting CP-SAT solver (time limit: {time_limit_seconds}s)...")
        status = solver.Solve(self.model)
        
        # Сохраняем статус решателя для анализа
        if status == cp_model.OPTIMAL:
            self.solver_status = 'OPTIMAL'
            print("✅ Solution found: OPTIMAL")
        elif status == cp_model.FEASIBLE:
            self.solver_status = 'FEASIBLE'
            print("✅ Solution found: FEASIBLE")
        elif status == cp_model.INFEASIBLE:
            self.solver_status = 'INFEASIBLE'
            print("❌ No solution found: INFEASIBLE")
            
            # Генерируем все отчеты для анализа
            from constraint_registry import generate_all_reports
            generate_all_reports(self.constraint_registry, optimizer=self, infeasible=True)
            
            self.solution = None
            return False
        elif status == cp_model.MODEL_INVALID:
            self.solver_status = 'MODEL_INVALID'
            print("❌ Model is invalid")
            self.solution = None
            return False
        else:
            self.solver_status = 'TIMEOUT'
            print(f"❓ Solver returned status: {status}")
            self.solution = None
            return False
        
        # Если дошли до этой точки, значит есть решение (OPTIMAL или FEASIBLE)
        # Store the solution
        solution = []
        for idx, c in enumerate(self.classes):
            # Get assigned values
            day = self.day_vars[idx]
            if not isinstance(day, int):
                day = solver.Value(day)
                    
            start_slot = self.start_vars[idx]
            if not isinstance(start_slot, int):
                start_slot = solver.Value(start_slot)
                    
            room_idx = self.room_vars[idx]
            if not isinstance(room_idx, int):
                room_idx = solver.Value(room_idx)
            
            day_name = list(self.day_indices.keys())[list(self.day_indices.values()).index(day)]
            room_name = self.rooms[room_idx]
            start_time = self.time_slots[start_slot]
            
            # Calculate end time
            time_obj = datetime.strptime(start_time, "%H:%M")
            time_obj += timedelta(minutes=c.duration)
            end_time = time_obj.strftime("%H:%M")
            
            # Store the assignment
            solution.append({
                "subject": c.subject,
                "group": c.group,
                "teacher": c.teacher,
                "room": room_name,
                "building": c.building,
                "day": day_name,
                "start_time": start_time,
                "end_time": end_time,
                "duration": c.duration,
                "pause_before": c.pause_before,
                "pause_after": c.pause_after
            })
        
        # Сохраняем решение
        self.solution = solution
        self.solver = solver  # Сохраняем solver для возможного использования позже
        
        # Генерируем полный отчет о ограничениях для анализа
        from constraint_registry import generate_all_reports
        generate_all_reports(self.constraint_registry, optimizer=self, infeasible=False)
        
        return True