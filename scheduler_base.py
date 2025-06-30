from ortools.sat.python import cp_model
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Set, Any

# Импорт из локальных модулей
from reader import ScheduleReader, ScheduleClass
from sequential_scheduling_checker import enforce_window_chain_sequencing

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
        
        # Create a map of classes by subject+teacher for easy lookup
        self.class_map = {}
        for idx, c in enumerate(classes):
            key = f"{c.subject}_{c.teacher}_{c.day}_{c.start_time}"
            self.class_map[key] = idx
        
        print(f"Created class_map with {len(self.class_map)} entries.")
        print(f"Classes list has {len(classes)} elements.")
        
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
        """Find the index of a class in the classes list using the class_map."""
        key = f"{c.subject}_{c.teacher}_{c.day}_{c.start_time}"
        if key in self.class_map:
            return self.class_map[key]
        
        # Fallback for classes not in the map - try to find by attributes
        for idx, cls in enumerate(self.classes):
            if (cls.subject == c.subject and cls.teacher == c.teacher and 
                cls.day == c.day and cls.start_time == c.start_time):
                return idx
        
        # If we can't find the class, print details and raise an error
        print(f"ERROR: Could not find linked class in the classes list:")
        print(f"  Subject: {c.subject}")
        print(f"  Teacher: {c.teacher}")
        print(f"  Day: {c.day}")
        print(f"  Start Time: {c.start_time}")
        print(f"Available classes:")
        for idx, cls in enumerate(self.classes):
            print(f"  {idx}: {cls.subject} - {cls.teacher} - {cls.day} - {cls.start_time}")
        
        raise ValueError(f"Could not find linked class {c} in the classes list")
    
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
        if self.model is None:
            self.build_model()

        # Применение улучшений для временных окон
        try:
            from timewindow_adapter import apply_timewindow_improvements
            apply_timewindow_improvements(self)
            self.timewindow_already_processed = True
        except ImportError:
            print("Warning: timewindow_adapter module not found, skipping timewindow improvements")
        
        # Create the solver
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit_seconds
        
        # Добавляем логирование
        print("\nAttempting to solve model...")
        
        # Solve the model
        status = solver.Solve(self.model)
        
        # Инициализация solution перед любым использованием
        solution = []
        
        # Детальное логирование статуса
        print(f"\nSolver status: {status}")
        if status == cp_model.OPTIMAL:
            print("Solution is optimal")
        elif status == cp_model.FEASIBLE:
            print("Solution is feasible (but may not be optimal)")
        elif status == cp_model.INFEASIBLE:
            print("Problem is proven infeasible - no solution exists")
            print("Possible reasons for infeasibility:")
            print("1. Contradictory constraints for fixed classes")
            print("2. Insufficient time windows for sequential scheduling")
            print("3. Conflicting resources without alternatives")
        elif status == cp_model.MODEL_INVALID:
            print("Model is invalid - check for contradicting constraints")
        else:
            print("Solver timed out or was interrupted")
        
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            # Store the solution
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
            
        # В случае INFEASIBLE, вызвать анализ конфликтов
        if status == cp_model.INFEASIBLE:
            print("\nAnalyzing conflicts in the model...")
            try:
                sufficient_conflicts = solver.SufficientAssumptionsForInfeasibility()
                print(f"Found {len(sufficient_conflicts)} conflicting constraints:")
                for i, var_index in enumerate(sufficient_conflicts):
                    if var_index >= 0:
                        print(f"  Conflict {i+1}: Constraint with index {var_index}")
                    else:
                        print(f"  Conflict {i+1}: Assumption with index {-var_index-1}")
            except:
                print("Could not analyze conflicts - feature not supported in this version of OR-Tools")
            
        # Сохраняем solution независимо от результата
        self.solution = solution
        
        # Возвращаем True только если найдено оптимальное или допустимое решение
        return status == cp_model.OPTIMAL or status == cp_model.FEASIBLE