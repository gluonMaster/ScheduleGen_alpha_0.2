# Система эффективных границ (Effective Bounds)

## Обзор

Система эффективных границ обеспечивает централизованное хранение и управление актуальными временными ограничениями занятий после применения всех constraint'ов. Это решает проблему несогласованности между различными компонентами системы планирования.

## Проблемы, которые решает

1. **Дублирующиеся ограничения**: Разные модули применяли одинаковые ограничения, ведущие к INFEASIBLE решениям
2. **Несогласованность данных**: `resource_constraints.py` использовал исходные временные окна, игнорируя ограничения из `chain_constraints.py`
3. **Отсутствие прозрачности**: Сложно было понять, какие ограничения активны для конкретного занятия

## Архитектура

### Основные компоненты

1. **`effective_bounds_utils.py`** - Основной модуль с утилитами
2. **`EffectiveBounds`** - Класс для хранения границ временного окна
3. **Интеграция в существующие модули** - Обновления в `chain_constraints.py`, `resource_constraints.py`, и др.

### Структура данных

```python
class EffectiveBounds:
    min_slot: int           # Минимальный слот времени
    max_slot: int           # Максимальный слот времени  
    min_time: str           # Минимальное время (HH:MM)
    max_time: str           # Максимальное время (HH:MM)
    source: str             # Источник определения границ
    confidence: str         # Уровень уверенности
    applied_constraints: list  # История примененных ограничений
```

## Использование

### Инициализация

```python
from effective_bounds_utils import initialize_effective_bounds

# В начале работы с оптимизатором
initialize_effective_bounds(optimizer)
```

### Установка границ

```python
from effective_bounds_utils import set_effective_bounds

# При добавлении ограничения времени
set_effective_bounds(optimizer, class_idx, min_slot, max_slot, 
                    "time_window", "Window constraint: 09:00-11:00")
```

### Получение границ с fallback

```python
from effective_bounds_utils import get_effective_bounds

# Получение актуальных границ (с автоматическим fallback к исходным данным)
bounds = get_effective_bounds(optimizer, class_idx, class_obj)
```

### Обновление после применения ограничений

```python
from effective_bounds_utils import update_bounds_from_constraint

# После добавления ограничения цепочки
update_bounds_from_constraint(optimizer, class_idx, "chain_ordering",
                             min_slot=new_min_slot, 
                             description="Chain constraint applied")
```

## Интеграция с существующими модулями

### chain_constraints.py

```python
# ДО:
constraint = optimizer.model.Add(optimizer.start_vars[idx] >= window_start_slot)

# ПОСЛЕ:
constraint = optimizer.add_constraint(...)
set_effective_bounds(optimizer, idx, window_start_slot, max_start_slot,
                    "time_window", f"Window: {start_time}-{end_time}")
```

### resource_constraints.py

```python
# ДО:
def times_overlap(c1, c2):
    # Использует только исходные start_time/end_time

# ПОСЛЕ:  
def times_overlap(optimizer, c1, c2, idx1, idx2):
    # Использует эффективные границы для более точного анализа
    bounds1 = get_effective_bounds(optimizer, idx1, c1)
    bounds2 = get_effective_bounds(optimizer, idx2, c2)
```

### sequential_scheduling.py

```python
# ДО:
def can_schedule_sequentially(c1, c2, idx1, idx2, verbose):

# ПОСЛЕ:
def can_schedule_sequentially(c1, c2, idx1, idx2, verbose, optimizer=None):
    # Поддержка анализа через эффективные границы
    if optimizer:
        bounds1 = get_effective_bounds(optimizer, idx1, c1)
        bounds2 = get_effective_bounds(optimizer, idx2, c2)
```

## Отчетность и отладка

### Детальный отчет

```python
from effective_bounds_utils import print_bounds_report

# Выводит полный отчет по всем эффективным границам
print_bounds_report(optimizer)
```

### Сводная статистика

```python
from effective_bounds_utils import get_bounds_summary

summary = get_bounds_summary(optimizer)
print(f"Classes with bounds: {summary['classes_with_bounds']}")
print(f"Sources: {summary['bounds_by_source']}")
```

## Примеры использования

### Установка фиксированного времени

```python
# Для занятия с фиксированным временем
fixed_slot = time_to_slot(optimizer, "09:00")
set_effective_bounds(optimizer, class_idx, fixed_slot, fixed_slot,
                    "fixed_time", "Fixed at 09:00")
```

### Ограничение временного окна

```python
# Для занятия с временным окном 09:00-11:00
start_slot = time_to_slot(optimizer, "09:00") 
end_slot = time_to_slot(optimizer, "11:00")
duration_slots = class_obj.duration // optimizer.time_interval
max_start_slot = end_slot - duration_slots

set_effective_bounds(optimizer, class_idx, start_slot, max_start_slot,
                    "time_window", "Window: 09:00-11:00")
```

### Цепочка ограничений

```python
# Класс должен начаться не раньше чем через 5 слотов после другого класса
update_bounds_from_constraint(optimizer, next_class_idx, "chain_ordering",
                             min_slot=5, 
                             description="Chain: after class X + 5 slots")
```

## Преимущества

1. **Консистентность**: Все модули используют одни и те же актуальные границы
2. **Прозрачность**: Легко отследить, откуда взялись ограничения
3. **Отладка**: Детальные отчеты помогают понять причины INFEASIBLE
4. **Производительность**: Кеширование и избежание дублирования вычислений
5. **Обратная совместимость**: Fallback к исходным данным при отсутствии эффективных границ

## Файлы изменений

- ✅ `effective_bounds_utils.py` - новый модуль с основной функциональностью  
- ✅ `chain_constraints.py` - интеграция при установке ограничений окон
- ✅ `timewindow_adapter.py` - использование при применении улучшений
- ✅ `resource_constraints.py` - использование в анализе конфликтов
- ✅ `sequential_scheduling.py` - использование в анализе последовательности
- ✅ `effective_bounds_demo.py` - примеры использования

## Следующие шаги

1. Интеграция с `model_variables.py` для установки начальных границ
2. Добавление валидации границ при изменениях
3. Интеграция с системой логирования для отслеживания изменений
4. Оптимизация производительности для больших расписаний
