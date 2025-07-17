"""
Централизованный реестр ограничений для отслеживания всех добавленных в CP-SAT модель ограничений.
Используется для диагностики INFEASIBLE проблем и анализа конфликтов.
"""

import time
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class ConstraintType(Enum):
    """Типы ограничений для классификации."""
    SEQUENTIAL = "sequential"
    RESOURCE_CONFLICT = "resource_conflict"
    TIME_WINDOW = "time_window"
    ROOM_CONFLICT = "room_conflict"
    TEACHER_CONFLICT = "teacher_conflict"
    GROUP_CONFLICT = "group_conflict"
    CHAIN_ORDERING = "chain_ordering"
    SEPARATION = "separation"
    FIXED_TIME = "fixed_time"
    LINKED_CLASSES = "linked_classes"
    ANCHOR = "anchor"
    OBJECTIVE = "objective"
    OTHER = "other"


@dataclass
class ConstraintInfo:
    """Информация о добавленном ограничении."""
    constraint_id: str
    constraint_type: ConstraintType
    origin_module: str
    origin_function: str
    class_i: Optional[int] = None
    class_j: Optional[int] = None
    description: str = ""
    timestamp: float = field(default_factory=time.time)
    cp_sat_constraint: Any = None
    variables_used: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.constraint_id:
            self.constraint_id = f"{self.constraint_type.value}_{self.class_i}_{self.class_j}_{int(self.timestamp)}"


@dataclass
class SkippedConstraint:
    """Информация о пропущенном ограничении."""
    constraint_type: ConstraintType
    origin_module: str
    origin_function: str
    class_i: Optional[int] = None
    class_j: Optional[int] = None
    reason: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class ConflictInfo:
    """Информация о конфликте ограничений."""
    constraint_ids: List[str]
    conflict_type: str
    description: str
    classes_involved: List[int]
    timestamp: float = field(default_factory=time.time)


class ConstraintRegistry:
    """Централизованный реестр ограничений."""
    
    def __init__(self):
        """Инициализация реестра."""
        self.added: List[ConstraintInfo] = []
        self.skipped: List[SkippedConstraint] = []
        self.exceptions: List[Tuple[int, int, str]] = []  # (class_i, class_j, reason)
        self.timeline: List[str] = []  # Порядок добавления constraint_id
        self.conflicts: List[ConflictInfo] = []
        
        # Индексы для быстрого поиска
        self.by_type: Dict[ConstraintType, List[str]] = {}
        self.by_class_pair: Dict[Tuple[int, int], List[str]] = {}
        self.by_origin: Dict[str, List[str]] = {}
        
        # Счетчики
        self.constraint_counter = 0
        self.total_added = 0
        self.total_skipped = 0
    
    def add_constraint(self, constraint_expr, constraint_type: ConstraintType, 
                      origin_module: str, origin_function: str,
                      class_i: Optional[int] = None, class_j: Optional[int] = None,
                      description: str = "", variables_used: List[str] = None) -> ConstraintInfo:
        """
        Добавляет ограничение в реестр.
        
        Args:
            constraint_expr: CP-SAT ограничение
            constraint_type: Тип ограничения
            origin_module: Модуль, из которого добавлено ограничение
            origin_function: Функция, из которой добавлено ограничение
            class_i, class_j: Индексы классов (если применимо)
            description: Описание ограничения
            variables_used: Список использованных переменных
            
        Returns:
            ConstraintInfo: Информация о добавленном ограничении
        """
        self.constraint_counter += 1
        constraint_id = f"{constraint_type.value}_{self.constraint_counter}"
        
        constraint_info = ConstraintInfo(
            constraint_id=constraint_id,
            constraint_type=constraint_type,
            origin_module=origin_module,
            origin_function=origin_function,
            class_i=class_i,
            class_j=class_j,
            description=description,
            cp_sat_constraint=constraint_expr,
            variables_used=variables_used or []
        )
        
        # Добавляем в основной список
        self.added.append(constraint_info)
        self.timeline.append(constraint_id)
        self.total_added += 1
        
        # Обновляем индексы
        self._update_indices(constraint_info)
        
        return constraint_info
    
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
        skipped_info = SkippedConstraint(
            constraint_type=constraint_type,
            origin_module=origin_module,
            origin_function=origin_function,
            class_i=class_i,
            class_j=class_j,
            reason=reason
        )
        
        self.skipped.append(skipped_info)
        self.total_skipped += 1
    
    def add_exception(self, class_i: int, class_j: int, reason: str):
        """
        Добавляет исключение для пары классов.
        
        Args:
            class_i, class_j: Индексы классов
            reason: Причина исключения
        """
        self.exceptions.append((class_i, class_j, reason))
    
    def detect_conflict(self, constraint_ids: List[str], conflict_type: str,
                       description: str, classes_involved: List[int]):
        """
        Регистрирует обнаруженный конфликт.
        
        Args:
            constraint_ids: Список ID конфликтующих ограничений
            conflict_type: Тип конфликта
            description: Описание конфликта
            classes_involved: Список вовлеченных классов
        """
        conflict_info = ConflictInfo(
            constraint_ids=constraint_ids,
            conflict_type=conflict_type,
            description=description,
            classes_involved=classes_involved
        )
        
        self.conflicts.append(conflict_info)
    
    def _update_indices(self, constraint_info: ConstraintInfo):
        """Обновляет индексы для быстрого поиска."""
        # Индекс по типу
        if constraint_info.constraint_type not in self.by_type:
            self.by_type[constraint_info.constraint_type] = []
        self.by_type[constraint_info.constraint_type].append(constraint_info.constraint_id)
        
        # Индекс по паре классов
        if constraint_info.class_i is not None and constraint_info.class_j is not None:
            pair = (min(constraint_info.class_i, constraint_info.class_j), 
                   max(constraint_info.class_i, constraint_info.class_j))
            if pair not in self.by_class_pair:
                self.by_class_pair[pair] = []
            self.by_class_pair[pair].append(constraint_info.constraint_id)
        
        # Индекс по модулю
        if constraint_info.origin_module not in self.by_origin:
            self.by_origin[constraint_info.origin_module] = []
        self.by_origin[constraint_info.origin_module].append(constraint_info.constraint_id)
    
    def get_constraints_by_type(self, constraint_type: ConstraintType) -> List[ConstraintInfo]:
        """Возвращает все ограничения заданного типа."""
        constraint_ids = self.by_type.get(constraint_type, [])
        return [c for c in self.added if c.constraint_id in constraint_ids]
    
    def get_constraints_by_class_pair(self, class_i: int, class_j: int) -> List[ConstraintInfo]:
        """Возвращает все ограничения для пары классов."""
        pair = (min(class_i, class_j), max(class_i, class_j))
        constraint_ids = self.by_class_pair.get(pair, [])
        return [c for c in self.added if c.constraint_id in constraint_ids]
    
    def get_constraints_by_origin(self, origin_module: str) -> List[ConstraintInfo]:
        """Возвращает все ограничения из заданного модуля."""
        constraint_ids = self.by_origin.get(origin_module, [])
        return [c for c in self.added if c.constraint_id in constraint_ids]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Возвращает статистику по ограничениям."""
        stats = {
            'total_added': self.total_added,
            'total_skipped': self.total_skipped,
            'total_exceptions': len(self.exceptions),
            'total_conflicts': len(self.conflicts),
            'by_type': {},
            'by_origin': {}
        }
        
        # Статистика по типам
        for constraint_type, constraint_ids in self.by_type.items():
            stats['by_type'][constraint_type.value] = len(constraint_ids)
        
        # Статистика по модулям
        for origin, constraint_ids in self.by_origin.items():
            stats['by_origin'][origin] = len(constraint_ids)
        
        return stats
    
    def print_infeasible_report(self, optimizer=None):
        """
        Печатает детальный отчет об ограничениях при INFEASIBLE.
        
        Args:
            optimizer: Экземпляр ScheduleOptimizer для доступа к данным о классах
        """
        print("\n" + "="*60)
        print("INFEASIBLE ANALYSIS REPORT")
        print("="*60)
        
        # Общая статистика
        stats = self.get_statistics()
        print(f"\n📊 CONSTRAINT STATISTICS:")
        print(f"  Total added: {stats['total_added']}")
        print(f"  Total skipped: {stats['total_skipped']}")
        print(f"  Total exceptions: {stats['total_exceptions']}")
        print(f"  Total conflicts: {stats['total_conflicts']}")
        
        # Статистика по типам
        print(f"\n📋 BY TYPE:")
        for constraint_type, count in stats['by_type'].items():
            print(f"  {constraint_type}: {count}")
        
        # Статистика по модулям
        print(f"\n📁 BY MODULE:")
        for origin, count in stats['by_origin'].items():
            print(f"  {origin}: {count}")
        
        # Обнаруженные конфликты
        if self.conflicts:
            print(f"\n⚠️  DETECTED CONFLICTS ({len(self.conflicts)}):")
            for i, conflict in enumerate(self.conflicts, 1):
                print(f"  {i}. {conflict.conflict_type}: {conflict.description}")
                print(f"     Constraints: {', '.join(conflict.constraint_ids)}")
                print(f"     Classes: {conflict.classes_involved}")
        
        # Исключения
        if self.exceptions:
            print(f"\n🚫 CONSTRAINT EXCEPTIONS ({len(self.exceptions)}):")
            for i, (class_i, class_j, reason) in enumerate(self.exceptions, 1):
                print(f"  {i}. Classes {class_i} ↔ {class_j}: {reason}")
        
        # Анализ потенциальных проблем
        self._analyze_potential_issues(optimizer)
        
        print("\n" + "="*60)
    
    def _analyze_potential_issues(self, optimizer=None):
        """Анализирует потенциальные проблемы в ограничениях."""
        print(f"\n🔍 POTENTIAL ISSUES ANALYSIS:")
        
        # Проверка на избыточные ограничения
        class_pairs = {}
        for constraint in self.added:
            if constraint.class_i is not None and constraint.class_j is not None:
                pair = (min(constraint.class_i, constraint.class_j), 
                       max(constraint.class_i, constraint.class_j))
                if pair not in class_pairs:
                    class_pairs[pair] = []
                class_pairs[pair].append(constraint)
        
        redundant_pairs = [(pair, constraints) for pair, constraints in class_pairs.items() 
                          if len(constraints) > 3]
        
        if redundant_pairs:
            print(f"  ❌ Potentially redundant constraints for {len(redundant_pairs)} class pairs:")
            for pair, constraints in redundant_pairs[:5]:  # Показываем первые 5
                types = [c.constraint_type.value for c in constraints]
                print(f"    Classes {pair[0]} ↔ {pair[1]}: {len(constraints)} constraints ({', '.join(set(types))})")
        
        # Проверка на противоречивые ограничения
        sequential_constraints = self.get_constraints_by_type(ConstraintType.SEQUENTIAL)
        if len(sequential_constraints) > 0:
            print(f"  ⚡ Sequential constraints: {len(sequential_constraints)}")
            
            # Поиск потенциальных циклов
            dependencies = {}
            for constraint in sequential_constraints:
                if constraint.class_i is not None and constraint.class_j is not None:
                    if constraint.class_i not in dependencies:
                        dependencies[constraint.class_i] = []
                    dependencies[constraint.class_i].append(constraint.class_j)
            
            # Простая проверка на циклы длиной 2
            cycles = []
            for class_i, deps in dependencies.items():
                for class_j in deps:
                    if class_j in dependencies and class_i in dependencies[class_j]:
                        cycles.append((class_i, class_j))
            
            if cycles:
                print(f"    ⚠️  Potential 2-cycles detected: {len(cycles)}")
                for cycle in cycles[:3]:  # Показываем первые 3
                    print(f"      Classes {cycle[0]} ↔ {cycle[1]}")
        
        # Проверка на фиксированные времена
        fixed_time_constraints = self.get_constraints_by_type(ConstraintType.FIXED_TIME)
        if len(fixed_time_constraints) > 0:
            print(f"  ⏰ Fixed time constraints: {len(fixed_time_constraints)}")
            
            # Группировка по времени
            if optimizer:
                time_groups = {}
                for constraint in fixed_time_constraints:
                    if constraint.class_i is not None and constraint.class_i < len(optimizer.classes):
                        class_obj = optimizer.classes[constraint.class_i]
                        if hasattr(class_obj, 'start_time') and class_obj.start_time:
                            time_key = f"{class_obj.day}_{class_obj.start_time}"
                            if time_key not in time_groups:
                                time_groups[time_key] = []
                            time_groups[time_key].append(constraint.class_i)
                
                overlapping_times = [(time_key, classes) for time_key, classes in time_groups.items() 
                                   if len(classes) > 1]
                
                if overlapping_times:
                    print(f"    ⚠️  Overlapping fixed times: {len(overlapping_times)}")
                    for time_key, classes in overlapping_times[:3]:  # Показываем первые 3
                        print(f"      {time_key}: classes {classes}")
    
    def export_to_file(self, filename: str, only_conflicts: bool = False, optimizer=None):
        """
        Экспортирует реестр в файл для детального анализа.
        
        Args:
            filename: Имя файла для экспорта
            only_conflicts: Если True, экспортирует только конфликты и потенциальные проблемы
            optimizer: Экземпляр ScheduleOptimizer для доступа к данным о классах
        """
        with open(filename, 'w', encoding='utf-8') as f:
            if only_conflicts:
                f.write("CONSTRAINT REGISTRY - INFEASIBLE ANALYSIS\n")
                f.write("="*60 + "\n\n")
                
                # Статистика
                stats = self.get_statistics()
                f.write("📊 CONSTRAINT STATISTICS:\n")
                f.write(f"Total added: {stats['total_added']}\n")
                f.write(f"Total skipped: {stats['total_skipped']}\n")
                f.write(f"Total exceptions: {stats['total_exceptions']}\n")
                f.write(f"Total conflicts: {stats['total_conflicts']}\n\n")
                
                # Конфликты
                if self.conflicts:
                    f.write("⚠️  DETECTED CONFLICTS:\n")
                    f.write("-" * 50 + "\n")
                    for i, conflict in enumerate(self.conflicts, 1):
                        f.write(f"Conflict #{i}:\n")
                        f.write(f"🔗 Type: {conflict.conflict_type}\n")
                        f.write(f"📄 Description: {conflict.description}\n")
                        f.write(f"🔢 Constraints: {', '.join(conflict.constraint_ids)}\n")
                        
                        # Детальная информация о классах
                        if conflict.classes_involved:
                            f.write(f"👨‍🏫 Involved Classes:\n")
                            for class_idx in conflict.classes_involved:
                                class_name = self.get_class_name(class_idx, optimizer)
                                f.write(f"  - Class {class_idx}: {class_name}\n")
                        
                        import datetime
                        timestamp_str = datetime.datetime.fromtimestamp(conflict.timestamp).strftime("%H:%M:%S")
                        f.write(f"🕐 Detected: {timestamp_str}\n\n")
                
                # Исключения
                if self.exceptions:
                    f.write("🚫 CONSTRAINT EXCEPTIONS:\n")
                    f.write("-" * 50 + "\n")
                    for i, (class_i, class_j, reason) in enumerate(self.exceptions, 1):
                        f.write(f"Exception #{i}:\n")
                        class_i_name = self.get_class_name(class_i, optimizer)
                        class_j_name = self.get_class_name(class_j, optimizer)
                        f.write(f"👨‍🏫 Class {class_i}: {class_i_name}\n")
                        f.write(f"👨‍🏫 Class {class_j}: {class_j_name}\n")
                        f.write(f"📄 Reason: {reason}\n\n")
                
                # Потенциальные проблемы
                self._write_potential_issues_to_file(f, optimizer)
                
                # Детальная информация о наиболее проблемных ограничениях
                f.write("🔍 DETAILED CONSTRAINT ANALYSIS:\n")
                f.write("-" * 50 + "\n")
                
                # Группируем ограничения по парам классов
                class_pairs = {}
                for constraint in self.added:
                    if constraint.class_i is not None and constraint.class_j is not None:
                        pair = (min(constraint.class_i, constraint.class_j), 
                               max(constraint.class_i, constraint.class_j))
                        if pair not in class_pairs:
                            class_pairs[pair] = []
                        class_pairs[pair].append(constraint)
                
                # Показываем наиболее проблемные пары
                most_constrained = sorted(class_pairs.items(), 
                                        key=lambda x: len(x[1]), 
                                        reverse=True)[:10]
                
                for pair, constraints in most_constrained:
                    if len(constraints) > 1:  # Только пары с множественными ограничениями
                        f.write(f"Class Pair: {pair[0]} ↔ {pair[1]}\n")
                        class_i_name = self.get_class_name(pair[0], optimizer)
                        class_j_name = self.get_class_name(pair[1], optimizer)
                        f.write(f"👨‍🏫 Class {pair[0]}: {class_i_name}\n")
                        f.write(f"👨‍🏫 Class {pair[1]}: {class_j_name}\n")
                        f.write(f"📊 Total constraints: {len(constraints)}\n")
                        
                        # Группируем по типам
                        by_type = {}
                        for constraint in constraints:
                            if constraint.constraint_type not in by_type:
                                by_type[constraint.constraint_type] = []
                            by_type[constraint.constraint_type].append(constraint)
                        
                        f.write(f"📋 By type:\n")
                        for constraint_type, type_constraints in by_type.items():
                            f.write(f"  - {constraint_type.value}: {len(type_constraints)}\n")
                        
                        f.write(f"🔗 Detailed constraints:\n")
                        for j, constraint in enumerate(constraints, 1):
                            f.write(f"  {j}. {constraint.constraint_type.value}\n")
                            f.write(f"     📍 {constraint.origin_module}:{constraint.origin_function}\n")
                            f.write(f"     📄 {constraint.description or '—'}\n")
                            if constraint.variables_used:
                                f.write(f"     🔢 Variables: {', '.join(constraint.variables_used)}\n")
                        f.write("\n")
                
            else:
                f.write("CONSTRAINT REGISTRY - FULL EXPORT\n")
                f.write("="*60 + "\n\n")
                
                # Статистика
                stats = self.get_statistics()
                f.write("📊 STATISTICS:\n")
                f.write(f"Total added: {stats['total_added']}\n")
                f.write(f"Total skipped: {stats['total_skipped']}\n")
                f.write(f"Total exceptions: {stats['total_exceptions']}\n")
                f.write(f"Total conflicts: {stats['total_conflicts']}\n\n")
                
                # Все добавленные ограничения с улучшенным форматированием
                f.write("🔗 ADDED CONSTRAINTS:\n")
                f.write("-" * 50 + "\n")
                for i, constraint in enumerate(self.added, 1):
                    f.write(f"Constraint #{i}:\n")
                    formatted_constraint = self.format_constraint_for_report(constraint, optimizer)
                    f.write(formatted_constraint)
                    f.write("\n" + "-" * 30 + "\n")
                
                # Пропущенные ограничения
                if self.skipped:
                    f.write("⏭️ SKIPPED CONSTRAINTS:\n")
                    f.write("-" * 50 + "\n")
                    for i, skipped in enumerate(self.skipped, 1):
                        f.write(f"Skipped #{i}:\n")
                        f.write(f"🔗 Type: {skipped.constraint_type.value}\n")
                        origin = f"{skipped.origin_module}:{skipped.origin_function}" if skipped.origin_module else "Unknown"
                        f.write(f"📍 Origin: {origin}\n")
                        
                        if skipped.class_i is not None:
                            class_i_name = self.get_class_name(skipped.class_i, optimizer)
                            f.write(f"👨‍🏫 Class {skipped.class_i}: {class_i_name}\n")
                        
                        if skipped.class_j is not None:
                            class_j_name = self.get_class_name(skipped.class_j, optimizer)
                            f.write(f"👨‍🏫 Class {skipped.class_j}: {class_j_name}\n")
                        
                        f.write(f"📄 Reason: {skipped.reason}\n")
                        
                        import datetime
                        timestamp_str = datetime.datetime.fromtimestamp(skipped.timestamp).strftime("%H:%M:%S")
                        f.write(f"🕐 Skipped: {timestamp_str}\n\n")
                
                # Исключения
                if self.exceptions:
                    f.write("🚫 EXCEPTIONS:\n")
                    f.write("-" * 50 + "\n")
                    for i, (class_i, class_j, reason) in enumerate(self.exceptions, 1):
                        f.write(f"Exception #{i}:\n")
                        class_i_name = self.get_class_name(class_i, optimizer)
                        class_j_name = self.get_class_name(class_j, optimizer)
                        f.write(f"👨‍🏫 Class {class_i}: {class_i_name}\n")
                        f.write(f"👨‍🏫 Class {class_j}: {class_j_name}\n")
                        f.write(f"📄 Reason: {reason}\n\n")
                
                # Конфликты
                if self.conflicts:
                    f.write("⚠️  CONFLICTS:\n")
                    f.write("-" * 50 + "\n")
                    for i, conflict in enumerate(self.conflicts, 1):
                        f.write(f"Conflict #{i}:\n")
                        f.write(f"🔗 Type: {conflict.conflict_type}\n")
                        f.write(f"📄 Description: {conflict.description}\n")
                        f.write(f"🔢 Constraints: {', '.join(conflict.constraint_ids)}\n")
                        
                        if conflict.classes_involved:
                            f.write(f"👨‍🏫 Classes:\n")
                            for class_idx in conflict.classes_involved:
                                class_name = self.get_class_name(class_idx, optimizer)
                                f.write(f"  - Class {class_idx}: {class_name}\n")
                        
                        import datetime
                        timestamp_str = datetime.datetime.fromtimestamp(conflict.timestamp).strftime("%H:%M:%S")
                        f.write(f"🕐 Detected: {timestamp_str}\n\n")
    
    def _write_potential_issues_to_file(self, f, optimizer=None):
        """Записывает анализ потенциальных проблем в файл."""
        f.write("🔍 POTENTIAL ISSUES ANALYSIS:\n")
        f.write("-" * 50 + "\n")
        
        # Проверка на избыточные ограничения
        class_pairs = {}
        for constraint in self.added:
            if constraint.class_i is not None and constraint.class_j is not None:
                pair = (min(constraint.class_i, constraint.class_j), 
                       max(constraint.class_i, constraint.class_j))
                if pair not in class_pairs:
                    class_pairs[pair] = []
                class_pairs[pair].append(constraint)
        
        redundant_pairs = [(pair, constraints) for pair, constraints in class_pairs.items() 
                          if len(constraints) > 3]
        
        if redundant_pairs:
            f.write(f"❌ Potentially redundant constraints for {len(redundant_pairs)} class pairs:\n")
            for pair, constraints in redundant_pairs[:10]:  # Показываем первые 10
                class_i_name = self.get_class_name(pair[0], optimizer)
                class_j_name = self.get_class_name(pair[1], optimizer)
                types = [c.constraint_type.value for c in constraints]
                f.write(f"  - Classes {pair[0]} ↔ {pair[1]}: {len(constraints)} constraints\n")
                f.write(f"    👨‍🏫 {class_i_name} ↔ {class_j_name}\n")
                f.write(f"    📋 Types: {', '.join(set(types))}\n")
            f.write("\n")
        
        # Проверка на противоречивые ограничения
        sequential_constraints = self.get_constraints_by_type(ConstraintType.SEQUENTIAL)
        chain_constraints = self.get_constraints_by_type(ConstraintType.CHAIN_ORDERING)
        
        if len(sequential_constraints) > 0 or len(chain_constraints) > 0:
            f.write(f"⚡ Ordering constraints: {len(sequential_constraints)} sequential, {len(chain_constraints)} chain\n")
            
            # Поиск потенциальных циклов
            dependencies = {}
            for constraint in sequential_constraints + chain_constraints:
                if constraint.class_i is not None and constraint.class_j is not None:
                    if constraint.class_i not in dependencies:
                        dependencies[constraint.class_i] = []
                    dependencies[constraint.class_i].append(constraint.class_j)
            
            # Простая проверка на циклы длиной 2
            cycles = []
            for class_i, deps in dependencies.items():
                for class_j in deps:
                    if class_j in dependencies and class_i in dependencies[class_j]:
                        cycles.append((class_i, class_j))
            
            if cycles:
                f.write(f"  ⚠️  Potential 2-cycles detected: {len(cycles)}\n")
                for cycle in cycles[:5]:  # Показываем первые 5
                    class_i_name = self.get_class_name(cycle[0], optimizer)
                    class_j_name = self.get_class_name(cycle[1], optimizer)
                    f.write(f"    Classes {cycle[0]} ↔ {cycle[1]}\n")
                    f.write(f"    👨‍🏫 {class_i_name} ↔ {class_j_name}\n")
            f.write("\n")
        
        # Проверка на фиксированные времена
        fixed_time_constraints = self.get_constraints_by_type(ConstraintType.FIXED_TIME)
        if len(fixed_time_constraints) > 0:
            f.write(f"⏰ Fixed time constraints: {len(fixed_time_constraints)}\n")
            
            # Группировка по времени
            if optimizer:
                time_groups = {}
                for constraint in fixed_time_constraints:
                    if constraint.class_i is not None and constraint.class_i < len(optimizer.classes):
                        class_obj = optimizer.classes[constraint.class_i]
                        if hasattr(class_obj, 'start_time') and class_obj.start_time:
                            day = getattr(class_obj, 'day', 'Unknown')
                            time_key = f"{day}_{class_obj.start_time}"
                            if time_key not in time_groups:
                                time_groups[time_key] = []
                            time_groups[time_key].append(constraint.class_i)
                
                overlapping_times = [(time_key, classes) for time_key, classes in time_groups.items() 
                                   if len(classes) > 1]
                
                if overlapping_times:
                    f.write(f"  ⚠️  Overlapping fixed times: {len(overlapping_times)}\n")
                    for time_key, classes in overlapping_times[:3]:  # Показываем первые 3
                        f.write(f"    📅 {time_key}: classes {classes}\n")
                        for class_idx in classes:
                            class_name = self.get_class_name(class_idx, optimizer)
                            f.write(f"      👨‍🏫 Class {class_idx}: {class_name}\n")
            f.write("\n")
        
        # Топ-проблемные пары классов
        if class_pairs:
            most_constrained = sorted(class_pairs.items(), 
                                    key=lambda x: len(x[1]), 
                                    reverse=True)[:5]
            f.write("🔥 Most constrained class pairs:\n")
            for pair, constraints in most_constrained:
                class_i_name = self.get_class_name(pair[0], optimizer)
                class_j_name = self.get_class_name(pair[1], optimizer)
                types = [c.constraint_type.value for c in constraints]
                f.write(f"  - Classes {pair[0]} ↔ {pair[1]}: {len(constraints)} constraints\n")
                f.write(f"    👨‍🏫 {class_i_name} ↔ {class_j_name}\n")
                f.write(f"    📋 Types: {', '.join(set(types))}\n")
            f.write("\n")
        
        # Статистика по типам ограничений
        stats = self.get_statistics()
        f.write("📈 Constraint type distribution:\n")
        for constraint_type, count in sorted(stats['by_type'].items(), key=lambda x: x[1], reverse=True):
            f.write(f"  {constraint_type}: {count}\n")
        f.write("\n")
        
        # Статистика по модулям
        f.write("📁 Constraint origin distribution:\n")
        for origin, count in sorted(stats['by_origin'].items(), key=lambda x: x[1], reverse=True):
            f.write(f"  {origin}: {count}\n")
        f.write("\n")
        
        # Анализ переменных
        f.write("🔢 Variable usage analysis:\n")
        variable_usage = {}
        for constraint in self.added:
            for var in constraint.variables_used:
                if var not in variable_usage:
                    variable_usage[var] = 0
                variable_usage[var] += 1
        
        if variable_usage:
            most_used_vars = sorted(variable_usage.items(), key=lambda x: x[1], reverse=True)[:10]
            f.write("  Most used variables:\n")
            for var, count in most_used_vars:
                f.write(f"    {var}: {count} constraints\n")
        else:
            f.write("  No variable usage data available\n")
        f.write("\n")
    
    def get_class_name(self, class_idx: int, optimizer=None) -> str:
        """
        Возвращает человекочитаемое имя класса для отчетов.
        
        Args:
            class_idx: Индекс класса
            optimizer: Экземпляр ScheduleOptimizer для доступа к данным о классах
            
        Returns:
            str: Имя класса в формате "Subject, Group, Teacher"
        """
        if optimizer and hasattr(optimizer, 'classes') and class_idx < len(optimizer.classes):
            c = optimizer.classes[class_idx]
            subject = getattr(c, 'subject', 'Unknown')
            teacher = getattr(c, 'teacher', 'Unknown')
            group = getattr(c, 'group', 'Unknown')
            return f"{subject}, {group}, {teacher}"
        
        return f"Class {class_idx}"
    
    def format_constraint_for_report(self, constraint: ConstraintInfo, optimizer=None) -> str:
        """
        Форматирует ограничение для читаемого отчета.
        
        Args:
            constraint: Информация об ограничении
            optimizer: Экземпляр ScheduleOptimizer для доступа к данным о классах
            
        Returns:
            str: Форматированная строка ограничения
        """
        lines = []
        
        # Заголовок с типом ограничения
        lines.append(f"🔗 Type: {constraint.constraint_type.value}")
        
        # Источник ограничения
        origin = f"{constraint.origin_module}:{constraint.origin_function}" if constraint.origin_module else "Unknown"
        lines.append(f"📍 Origin: {origin}")
        
        # Информация о классах
        if constraint.class_i is not None:
            class_i_name = self.get_class_name(constraint.class_i, optimizer)
            lines.append(f"👨‍🏫 Class {constraint.class_i}: {class_i_name}")
        
        if constraint.class_j is not None:
            class_j_name = self.get_class_name(constraint.class_j, optimizer)
            lines.append(f"👨‍🏫 Class {constraint.class_j}: {class_j_name}")
        
        # Переменные
        if constraint.variables_used:
            variables_str = ", ".join(constraint.variables_used)
            lines.append(f"🔢 Variables: {variables_str}")
        else:
            lines.append(f"🔢 Variables: —")
        
        # Описание ограничения
        description = constraint.description if constraint.description else "—"
        lines.append(f"📄 Description: {description}")
        
        # Дополнительная информация на основе типа ограничения
        if constraint.constraint_type == ConstraintType.CHAIN_ORDERING:
            lines.append(f"⏳ Condition: Class {constraint.class_i} must end before Class {constraint.class_j} starts")
        elif constraint.constraint_type == ConstraintType.SEPARATION:
            lines.append(f"⏳ Condition: Classes {constraint.class_i} and {constraint.class_j} must have time gap")
        elif constraint.constraint_type == ConstraintType.RESOURCE_CONFLICT:
            lines.append(f"⏳ Condition: Classes {constraint.class_i} and {constraint.class_j} cannot share resources simultaneously")
        elif constraint.constraint_type == ConstraintType.TIME_WINDOW:
            lines.append(f"⏳ Condition: Class {constraint.class_i} must be within time window")
        elif constraint.constraint_type == ConstraintType.FIXED_TIME:
            lines.append(f"⏳ Condition: Class {constraint.class_i} has fixed start time")
        
        # Временная метка
        import datetime
        timestamp_str = datetime.datetime.fromtimestamp(constraint.timestamp).strftime("%H:%M:%S")
        lines.append(f"🕐 Added: {timestamp_str}")
        
        return "\n".join(lines)


def export_constraint_registry(registry: ConstraintRegistry, optimizer=None, only_conflicts: bool = False):
    """
    Экспортирует constraint registry в файл.
    
    Args:
        registry: Экземпляр ConstraintRegistry
        optimizer: Экземпляр ScheduleOptimizer для доступа к данным о классах
        only_conflicts: Если True, экспортирует только конфликты и проблемы
    """
    filename = "constraint_registry_infeasible.txt" if only_conflicts else "constraint_registry_full.txt"
    
    print(f"\n📋 Exporting constraint registry to {filename}...")
    registry.export_to_file(filename, only_conflicts=only_conflicts, optimizer=optimizer)
    
    if only_conflicts:
        print("\n🔍 INFEASIBLE ANALYSIS:")
        print("="*50)
        
        # Печать краткого отчета о конфликтах
        stats = registry.get_statistics()
        print(f"Total constraints: {stats['total_added']}")
        print(f"Detected conflicts: {stats['total_conflicts']}")
        print(f"Constraint exceptions: {stats['total_exceptions']}")
        
        # Показать наиболее проблемные ограничения
        if registry.conflicts:
            print(f"\n⚠️  DETECTED CONFLICTS:")
            for i, conflict in enumerate(registry.conflicts[:5], 1):
                classes_str = ", ".join([registry.get_class_name(c, optimizer) for c in conflict.classes_involved])
                print(f"  {i}. {conflict.conflict_type}: {classes_str}")
        
        # Показать наиболее ограниченные пары классов
        class_pairs = {}
        for constraint in registry.added:
            if constraint.class_i is not None and constraint.class_j is not None:
                pair = (min(constraint.class_i, constraint.class_j), 
                       max(constraint.class_i, constraint.class_j))
                if pair not in class_pairs:
                    class_pairs[pair] = []
                class_pairs[pair].append(constraint)
        
        if class_pairs:
            most_constrained = sorted(class_pairs.items(), 
                                    key=lambda x: len(x[1]), 
                                    reverse=True)[:3]
            print(f"\n🔥 Most constrained pairs:")
            for pair, constraints in most_constrained:
                class_i_name = registry.get_class_name(pair[0], optimizer)
                class_j_name = registry.get_class_name(pair[1], optimizer)
                types = [c.constraint_type.value for c in constraints]
                print(f"  {class_i_name} ↔ {class_j_name}: {len(constraints)} constraints ({', '.join(set(types))})")
        
        print(f"\nDetailed report saved to: {filename}")
        print("="*50)
    
    print(f"✅ Constraint registry exported to {filename}")


def print_infeasible_summary(registry: ConstraintRegistry, optimizer=None):
    """
    Печатает краткий отчет о потенциальных конфликтах при INFEASIBLE.
    
    Args:
        registry: Экземпляр ConstraintRegistry
        optimizer: Экземпляр ScheduleOptimizer для доступа к данным о классах
    """
    print("\n" + "="*60)
    print("❌ INFEASIBLE: Potential conflicting constraints")
    print("="*60)
    
    stats = registry.get_statistics()
    print(f"📊 Total constraints: {stats['total_added']}")
    
    # Показать конфликты
    if registry.conflicts:
        print(f"\n⚠️  Detected conflicts ({len(registry.conflicts)}):")
        for i, conflict in enumerate(registry.conflicts, 1):
            classes_str = ", ".join([registry.get_class_name(c, optimizer) for c in conflict.classes_involved])
            print(f"  {i}. {conflict.conflict_type}: {classes_str}")
            print(f"     {conflict.description}")
    
    # Показать наиболее проблемные пары
    class_pairs = {}
    for constraint in registry.added:
        if constraint.class_i is not None and constraint.class_j is not None:
            pair = (min(constraint.class_i, constraint.class_j), 
                   max(constraint.class_i, constraint.class_j))
            if pair not in class_pairs:
                class_pairs[pair] = []
            class_pairs[pair].append(constraint)
    
    redundant_pairs = [(pair, constraints) for pair, constraints in class_pairs.items() 
                      if len(constraints) > 3]
    
    if redundant_pairs:
        print(f"\n🔥 Potentially over-constrained pairs ({len(redundant_pairs)}):")
        for pair, constraints in redundant_pairs[:5]:
            class_i_name = registry.get_class_name(pair[0], optimizer)
            class_j_name = registry.get_class_name(pair[1], optimizer)
            types = [c.constraint_type.value for c in constraints]
            print(f"  - {class_i_name} ↔ {class_j_name}")
            print(f"    {len(constraints)} constraints: {', '.join(set(types))}")
            
            # Показать детали первых нескольких ограничений
            for j, constraint in enumerate(constraints[:3], 1):
                print(f"    {j}. {constraint.constraint_type.value}: {constraint.description}")
    
    # Показать исключения
    if registry.exceptions:
        print(f"\n🚫 Constraint exceptions ({len(registry.exceptions)}):")
        for class_i, class_j, reason in registry.exceptions[:5]:
            class_i_name = registry.get_class_name(class_i, optimizer)
            class_j_name = registry.get_class_name(class_j, optimizer)
            print(f"  - {class_i_name} ↔ {class_j_name}: {reason}")
    
    print(f"\n💡 Troubleshooting suggestions:")
    print(f"  1. Review classes with many constraints")
    print(f"  2. Check for conflicting time windows")
    print(f"  3. Relax some constraint exceptions")
    print(f"  4. Consider increasing time slots or resources")
    print(f"  5. Verify that linked class sequences are feasible")
    
    print("\n" + "="*60)

def generate_log_err_summary(registry: ConstraintRegistry, optimizer=None):
    """
    Генерирует краткий отчет для log_Err.txt с основными проблемами.
    
    Args:
        registry: Экземпляр ConstraintRegistry
        optimizer: Экземпляр ScheduleOptimizer для доступа к данным о классах
    """
    try:
        with open("log_Err.txt", "w", encoding="utf-8") as f:
            f.write("CONSTRAINT ANALYSIS - ERROR LOG\n")
            f.write("="*50 + "\n\n")
            
            # Статистика
            stats = registry.get_statistics()
            f.write(f"📊 STATISTICS:\n")
            f.write(f"Total constraints: {stats['total_added']}\n")
            f.write(f"Skipped constraints: {stats['total_skipped']}\n")
            f.write(f"Exceptions: {stats['total_exceptions']}\n")
            f.write(f"Conflicts: {stats['total_conflicts']}\n\n")
            
            # Топ-5 проблемных пар классов
            class_pairs = {}
            for constraint in registry.added:
                if constraint.class_i is not None and constraint.class_j is not None:
                    pair = (min(constraint.class_i, constraint.class_j), 
                           max(constraint.class_i, constraint.class_j))
                    if pair not in class_pairs:
                        class_pairs[pair] = []
                    class_pairs[pair].append(constraint)
            
            if class_pairs:
                most_constrained = sorted(class_pairs.items(), 
                                        key=lambda x: len(x[1]), 
                                        reverse=True)[:5]
                f.write(f"🔥 TOP 5 MOST CONSTRAINED PAIRS:\n")
                for i, (pair, constraints) in enumerate(most_constrained, 1):
                    class_i_name = registry.get_class_name(pair[0], optimizer)
                    class_j_name = registry.get_class_name(pair[1], optimizer)
                    types = [c.constraint_type.value for c in constraints]
                    f.write(f"{i}. {class_i_name} ↔ {class_j_name}\n")
                    f.write(f"   {len(constraints)} constraints: {', '.join(set(types))}\n")
                f.write("\n")
            
            # Конфликты
            if registry.conflicts:
                f.write(f"⚠️  DETECTED CONFLICTS:\n")
                for i, conflict in enumerate(registry.conflicts, 1):
                    classes_str = ", ".join([registry.get_class_name(c, optimizer) for c in conflict.classes_involved])
                    f.write(f"{i}. {conflict.conflict_type}: {classes_str}\n")
                    f.write(f"   {conflict.description}\n")
                f.write("\n")
            
            # Исключения
            if registry.exceptions:
                f.write(f"🚫 CONSTRAINT EXCEPTIONS:\n")
                for i, (class_i, class_j, reason) in enumerate(registry.exceptions, 1):
                    class_i_name = registry.get_class_name(class_i, optimizer)
                    class_j_name = registry.get_class_name(class_j, optimizer)
                    f.write(f"{i}. {class_i_name} ↔ {class_j_name}: {reason}\n")
                f.write("\n")
            
            # Распределение по типам
            f.write(f"📋 CONSTRAINT TYPES:\n")
            for constraint_type, count in sorted(stats['by_type'].items(), 
                                                key=lambda x: x[1], reverse=True):
                f.write(f"  {constraint_type}: {count}\n")
            f.write("\n")
            
            # Распределение по модулям
            f.write(f"📁 CONSTRAINT ORIGINS:\n")
            for origin, count in sorted(stats['by_origin'].items(), 
                                      key=lambda x: x[1], reverse=True):
                f.write(f"  {origin}: {count}\n")
            f.write("\n")
            
            # Рекомендации
            f.write(f"💡 RECOMMENDATIONS:\n")
            if registry.conflicts:
                f.write(f"  - Resolve {len(registry.conflicts)} detected conflicts\n")
            if stats['total_exceptions'] > 0:
                f.write(f"  - Review {stats['total_exceptions']} constraint exceptions\n")
            if class_pairs:
                over_constrained = [(pair, constraints) for pair, constraints in class_pairs.items() 
                                  if len(constraints) > 5]
                if over_constrained:
                    f.write(f"  - {len(over_constrained)} class pairs are heavily constrained\n")
            f.write(f"  - See constraint_registry_full.txt for detailed analysis\n")
            
        print("✅ Brief error summary saved to log_Err.txt")
        
    except Exception as e:
        print(f"❌ Error generating log_Err.txt: {e}")


# Функция для автоматической генерации всех отчетов
def generate_all_reports(registry: ConstraintRegistry, optimizer=None, infeasible=False):
    """
    Генерирует все типы отчетов: полный, конфликтный и краткий.
    
    Args:
        registry: Экземпляр ConstraintRegistry
        optimizer: Экземпляр ScheduleOptimizer для доступа к данным о классах
        infeasible: True если проблема INFEASIBLE
    """
    print("\n📋 Generating constraint reports...")
    
    # Полный отчет
    export_constraint_registry(registry, optimizer, only_conflicts=False)
    
    # Отчет о конфликтах (при INFEASIBLE)
    if infeasible:
        export_constraint_registry(registry, optimizer, only_conflicts=True)
    
    # Краткий отчет
    generate_log_err_summary(registry, optimizer)
    
    print("✅ All constraint reports generated successfully")
