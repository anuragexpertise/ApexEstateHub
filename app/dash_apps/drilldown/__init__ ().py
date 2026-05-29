# app/dash_apps/drilldown/__init__.py
"""
Drill-Down UX Engine for EsateHub
=======================================
Central navigation engine that powers:
  KPI → List → Profile → Form transitions
  Filter propagation across role hierarchies
  Breadcrumb state management
  Pre-filled form context passing
"""
from . import loaders, renderers, state

__all__ = ['loaders', 'renderers', 'state']