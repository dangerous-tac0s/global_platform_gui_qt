"""
Event system for decoupled communication between components.
"""

from .event_bus import EventBus, CardEvent

__all__ = ["EventBus", "CardEvent"]
