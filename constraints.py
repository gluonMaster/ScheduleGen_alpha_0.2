"""
Основной модуль для добавления ограничений в модель оптимизации.
Объединяет функциональность из отдельных модулей.

ОБНОВЛЕНИЕ: linked_constraints отключен для предотвращения дублирующих ограничений.
Все ограничения для цепочек теперь обрабатываются через chain_constraints.py
"""

# ОТКЛЮЧЕНО: from linked_constraints import add_linked_constraints
from resource_constraints import add_resource_conflict_constraints
from time_conflict_constraints import _add_time_conflict_constraints

# Re-экспорт основных функций для обратной совместимости
# ОБНОВЛЕНО: убран add_linked_constraints
__all__ = ['add_resource_conflict_constraints']
