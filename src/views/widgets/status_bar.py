"""
StatusBar widget - Displays status messages with animated conveyor-style rotation.

Messages slide in from the right and exit to the left with fade effect.
Multiple messages can be visible simultaneously, separated by arrow delimiters.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, List

from PyQt5.QtWidgets import (
    QLabel,
    QWidget,
    QHBoxLayout,
    QGraphicsOpacityEffect,
)
from PyQt5.QtCore import (
    QTimer,
    QPropertyAnimation,
    QParallelAnimationGroup,
    QEasingCurve,
    QPoint,
    Qt,
    QSize,
)
from PyQt5.QtGui import QFontMetrics

from ...events.event_bus import EventBus, StatusMessageEvent, ErrorEvent


class MessageState(Enum):
    """State of a message in the conveyor."""

    ENTERING = auto()
    VISIBLE = auto()
    EXITING = auto()


@dataclass
class AnimatedMessage:
    """Wrapper for a message being displayed in the conveyor."""

    text: str
    timeout_ms: int
    low_priority: bool = False  # Low priority messages can expire out of FIFO order
    label: Optional[QLabel] = None
    delimiter_label: Optional[QLabel] = None
    opacity_effect: Optional[QGraphicsOpacityEffect] = None
    state: MessageState = MessageState.ENTERING
    remaining_ms: int = field(init=False)
    entering_ticks: int = field(init=False)  # Tracks time in ENTERING state

    def __post_init__(self):
        self.remaining_ms = self.timeout_ms
        self.entering_ticks = 0


class MessageQueue(QWidget):
    """
    Animated message queue that displays messages as a horizontal conveyor belt.

    Messages slide in from the right, are separated by arrow delimiters,
    and slide out to the left with a fade effect when they timeout.
    Shows a "+N" badge when messages are queued but not visible.
    """

    ANIMATION_DURATION_MS = 175  # 150-200ms range
    DELIMITER = " → "
    TICK_INTERVAL_MS = 100  # How often to check timeouts
    BADGE_MARGIN = 8

    # State messages that persist when idle (no other messages pending)
    # These provide helpful status info and only disappear when new messages arrive
    PERSISTENT_MESSAGES = {
        "Ready.",
        "No card present.",
        "Unsupported card present.",
        "Compatible card present.",
    }

    # Message prefixes that should immediately expire persistent messages
    # These indicate operations that change the "Ready" state
    EXPIRE_PERSISTENT_PREFIXES = (
        "Installing:",
        "Uninstalling",  # "Uninstalling with {file}"
    )

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize the animated message queue.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        # Queue of messages waiting to be displayed
        self._pending_queue: List[tuple] = []  # (message, timeout_ms, low_priority)

        # Currently visible messages
        self._visible_messages: List[AnimatedMessage] = []

        # Setup the container
        self.setMinimumHeight(20)

        # Use a layout but we'll position items manually for animation
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # Container for messages (will clip overflow)
        self._message_container = QWidget(self)
        self._message_container.setStyleSheet("background: transparent;")
        self._layout.addWidget(self._message_container, 1)

        # Queue badge (shows +N when messages are waiting)
        self._badge = QLabel(self)
        self._badge.setStyleSheet(
            "QLabel { color: #666; font-size: 11px; padding: 0 4px; }"
        )
        self._badge.hide()
        self._layout.addWidget(self._badge)

        # Timer for processing message timeouts
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._on_tick)

        # Track running animations
        self._active_animations: List[QParallelAnimationGroup] = []

    def add_message(self, message: str, low_priority: bool = False) -> None:
        """
        Add a message to the queue.

        Duplicate messages are ignored if already pending or visible.
        Persistent state messages are immediately expired when new messages arrive.

        Args:
            message: Message text to display
            low_priority: If True, message can expire out of FIFO order when
                          blocked by a frozen persistent message. Use for
                          "informational" messages that shouldn't disrupt
                          important status indicators.
        """
        # Skip if message is already in pending queue
        if any(msg == message for msg, _, _ in self._pending_queue):
            return

        # Skip if message is already visible (but allow if it's exiting)
        if any(msg.text == message and msg.state != MessageState.EXITING
               for msg in self._visible_messages):
            return

        # Immediately expire persistent messages when an operation starts
        if message.startswith(self.EXPIRE_PERSISTENT_PREFIXES):
            for msg in self._visible_messages:
                if msg.text in self.PERSISTENT_MESSAGES and msg.state != MessageState.EXITING:
                    msg.remaining_ms = 0  # Will be expired on next tick

        timeout = self._calculate_timeout(message)
        self._pending_queue.append((message, timeout, low_priority))
        self._update_badge()
        self._try_show_next_message()

        # Start the tick timer if not running
        if not self._tick_timer.isActive():
            self._tick_timer.start(self.TICK_INTERVAL_MS)

    def clear(self) -> None:
        """Clear all pending and visible messages."""
        self._pending_queue.clear()

        # Stop all animations
        for anim in self._active_animations:
            anim.stop()
        self._active_animations.clear()

        # Remove all visible message widgets
        for msg in self._visible_messages:
            if msg.label:
                msg.label.deleteLater()
            if msg.delimiter_label:
                msg.delimiter_label.deleteLater()
        self._visible_messages.clear()

        self._tick_timer.stop()
        self._update_badge()

    def _calculate_timeout(self, message: str) -> int:
        """Calculate display timeout based on message length."""
        return max(3000, len(message) * 50)

    def _calculate_visible_width(self) -> int:
        """Calculate the total width of currently visible messages."""
        total = 0
        for msg in self._visible_messages:
            if msg.label and msg.state != MessageState.EXITING:
                total += msg.label.sizeHint().width()
            if msg.delimiter_label and msg.state != MessageState.EXITING:
                total += msg.delimiter_label.sizeHint().width()
        return total

    def _get_available_width(self) -> int:
        """Get the available width for messages."""
        badge_width = self._badge.sizeHint().width() if self._badge.isVisible() else 0
        return self._message_container.width() - badge_width - self.BADGE_MARGIN

    def _has_space_for_message(self, message: str) -> bool:
        """Check if there's space to display a new message."""
        if not self._visible_messages:
            return True

        # Calculate width needed for new message + delimiter
        font_metrics = QFontMetrics(self.font())
        new_msg_width = font_metrics.horizontalAdvance(message)
        delimiter_width = font_metrics.horizontalAdvance(self.DELIMITER)

        current_width = self._calculate_visible_width()
        needed_width = current_width + delimiter_width + new_msg_width

        return needed_width <= self._get_available_width()

    def _try_show_next_message(self) -> None:
        """Try to show the next message from the pending queue."""
        if not self._pending_queue:
            return

        message, timeout, low_priority = self._pending_queue[0]

        if self._has_space_for_message(message):
            self._pending_queue.pop(0)
            self._show_message(message, timeout, low_priority)
            self._update_badge()

    def _show_message(self, message: str, timeout_ms: int, low_priority: bool = False) -> None:
        """Create and animate a new message into view."""
        # When showing a persistent message, expire other visible persistent messages
        # This happens here (not in add_message) so it only triggers when actually shown
        if message in self.PERSISTENT_MESSAGES:
            for msg in self._visible_messages:
                if msg.text in self.PERSISTENT_MESSAGES and msg.state != MessageState.EXITING:
                    msg.remaining_ms = 0  # Will be expired on next tick

        animated_msg = AnimatedMessage(text=message, timeout_ms=timeout_ms, low_priority=low_priority)

        # Calculate target x position based on existing visible messages
        target_x = self._calculate_visible_width()
        delim_target_x = target_x

        # Create delimiter if there are existing messages
        if self._visible_messages:
            delimiter = QLabel(self.DELIMITER, self._message_container)
            delimiter.setStyleSheet("color: #888;")
            animated_msg.delimiter_label = delimiter
            delimiter.adjustSize()
            delimiter.show()
            # Delimiter goes at current end, message after it
            delim_target_x = target_x
            target_x += delimiter.sizeHint().width()

        # Create the message label
        label = QLabel(message, self._message_container)
        label.setStyleSheet("color: #333;")
        animated_msg.label = label
        label.adjustSize()
        label.show()

        # Create opacity effect for fade animations
        opacity_effect = QGraphicsOpacityEffect(label)
        opacity_effect.setOpacity(1.0)
        label.setGraphicsEffect(opacity_effect)
        animated_msg.opacity_effect = opacity_effect

        # Position for slide-in animation (start off-screen to the right)
        start_x = self._message_container.width()
        label.move(start_x, 0)

        if animated_msg.delimiter_label:
            animated_msg.delimiter_label.move(
                start_x - animated_msg.delimiter_label.width(), 0
            )

        # Animate slide-in
        self._animate_slide_in(
            animated_msg,
            target_x,
            delim_target_x if animated_msg.delimiter_label else None
        )

        self._visible_messages.append(animated_msg)

    def _recalculate_positions(self) -> None:
        """Recalculate and apply positions of all visible messages."""
        x_pos = 0
        for msg in self._visible_messages:
            if msg.state == MessageState.EXITING:
                continue
            if msg.delimiter_label:
                msg.delimiter_label.move(x_pos, 0)
                x_pos += msg.delimiter_label.sizeHint().width()
            if msg.label:
                msg.label.move(x_pos, 0)
                x_pos += msg.label.sizeHint().width()

    def _animate_slide_in(
        self,
        msg: AnimatedMessage,
        target_x: int,
        delim_target_x: Optional[int]
    ) -> None:
        """Animate a message sliding in from the right."""
        msg.state = MessageState.ENTERING

        # If container isn't properly sized yet, skip animation and position directly
        container_width = self._message_container.width()
        if container_width <= 0:
            if msg.label:
                msg.label.move(target_x, 0)
            if msg.delimiter_label and delim_target_x is not None:
                msg.delimiter_label.move(delim_target_x, 0)
            msg.state = MessageState.VISIBLE
            # Defer _try_show_next_message until after _show_message completes
            # and appends this message to _visible_messages
            QTimer.singleShot(0, self._try_show_next_message)
            return

        anim_group = QParallelAnimationGroup(self)

        if msg.label:
            label_anim = QPropertyAnimation(msg.label, b"pos", self)
            label_anim.setDuration(self.ANIMATION_DURATION_MS)
            label_anim.setStartValue(msg.label.pos())
            label_anim.setEndValue(QPoint(target_x, 0))
            label_anim.setEasingCurve(QEasingCurve.OutCubic)
            anim_group.addAnimation(label_anim)

        if msg.delimiter_label and delim_target_x is not None:
            delim_anim = QPropertyAnimation(msg.delimiter_label, b"pos", self)
            delim_anim.setDuration(self.ANIMATION_DURATION_MS)
            delim_anim.setStartValue(msg.delimiter_label.pos())
            delim_anim.setEndValue(QPoint(delim_target_x, 0))
            delim_anim.setEasingCurve(QEasingCurve.OutCubic)
            anim_group.addAnimation(delim_anim)

        def on_finished():
            msg.state = MessageState.VISIBLE
            if anim_group in self._active_animations:
                self._active_animations.remove(anim_group)
            # Try to show more messages now that this one is settled
            self._try_show_next_message()

        anim_group.finished.connect(on_finished)
        self._active_animations.append(anim_group)
        anim_group.start()

    def _animate_slide_out(self, msg: AnimatedMessage) -> None:
        """Animate a message sliding out to the left with fade."""
        msg.state = MessageState.EXITING

        anim_group = QParallelAnimationGroup(self)

        # Slide to the left
        if msg.label:
            label_anim = QPropertyAnimation(msg.label, b"pos", self)
            label_anim.setDuration(self.ANIMATION_DURATION_MS)
            label_anim.setStartValue(msg.label.pos())
            label_anim.setEndValue(QPoint(-msg.label.width(), 0))
            label_anim.setEasingCurve(QEasingCurve.InOutCubic)
            anim_group.addAnimation(label_anim)

            # Fade out
            if msg.opacity_effect:
                fade_anim = QPropertyAnimation(msg.opacity_effect, b"opacity", self)
                fade_anim.setDuration(self.ANIMATION_DURATION_MS)
                fade_anim.setStartValue(1.0)
                fade_anim.setEndValue(0.0)
                fade_anim.setEasingCurve(QEasingCurve.InOutCubic)
                anim_group.addAnimation(fade_anim)

        if msg.delimiter_label:
            delim_anim = QPropertyAnimation(msg.delimiter_label, b"pos", self)
            delim_anim.setDuration(self.ANIMATION_DURATION_MS)
            delim_anim.setStartValue(msg.delimiter_label.pos())
            delim_anim.setEndValue(QPoint(-msg.delimiter_label.width() - msg.label.width() if msg.label else 0, 0))
            delim_anim.setEasingCurve(QEasingCurve.InOutCubic)
            anim_group.addAnimation(delim_anim)

        def on_finished():
            # Clean up the widgets
            if msg.label:
                msg.label.deleteLater()
            if msg.delimiter_label:
                msg.delimiter_label.deleteLater()
            if msg in self._visible_messages:
                self._visible_messages.remove(msg)
            if anim_group in self._active_animations:
                self._active_animations.remove(anim_group)

            # Shift remaining messages left and try to show more
            self._animate_shift_left()
            self._try_show_next_message()

        anim_group.finished.connect(on_finished)
        self._active_animations.append(anim_group)
        anim_group.start()

    def _animate_shift_left(self) -> None:
        """Animate remaining messages shifting left to fill the gap."""
        if not self._visible_messages:
            return

        x_pos = 0
        anim_group = QParallelAnimationGroup(self)
        delimiters_to_remove = []
        is_first = True

        for msg in self._visible_messages:
            if msg.state == MessageState.EXITING:
                continue

            # The first (oldest) visible message shouldn't have a delimiter
            # If it does, slide it off to the left and mark for removal
            if is_first and msg.delimiter_label:
                anim = QPropertyAnimation(msg.delimiter_label, b"pos", self)
                anim.setDuration(self.ANIMATION_DURATION_MS)
                anim.setStartValue(msg.delimiter_label.pos())
                anim.setEndValue(QPoint(-msg.delimiter_label.width(), 0))
                anim.setEasingCurve(QEasingCurve.InOutCubic)
                anim_group.addAnimation(anim)
                delimiters_to_remove.append((msg, msg.delimiter_label))
            elif msg.delimiter_label:
                if msg.delimiter_label.x() != x_pos:
                    anim = QPropertyAnimation(msg.delimiter_label, b"pos", self)
                    anim.setDuration(self.ANIMATION_DURATION_MS)
                    anim.setStartValue(msg.delimiter_label.pos())
                    anim.setEndValue(QPoint(x_pos, 0))
                    anim.setEasingCurve(QEasingCurve.InOutCubic)
                    anim_group.addAnimation(anim)
                x_pos += msg.delimiter_label.sizeHint().width()

            if msg.label:
                if msg.label.x() != x_pos:
                    anim = QPropertyAnimation(msg.label, b"pos", self)
                    anim.setDuration(self.ANIMATION_DURATION_MS)
                    anim.setStartValue(msg.label.pos())
                    anim.setEndValue(QPoint(x_pos, 0))
                    anim.setEasingCurve(QEasingCurve.InOutCubic)
                    anim_group.addAnimation(anim)
                x_pos += msg.label.sizeHint().width()

            is_first = False

        if anim_group.animationCount() > 0:
            def on_finished():
                if anim_group in self._active_animations:
                    self._active_animations.remove(anim_group)
                # Clean up delimiters that were slid off
                for msg, delim in delimiters_to_remove:
                    delim.deleteLater()
                    msg.delimiter_label = None

            anim_group.finished.connect(on_finished)
            self._active_animations.append(anim_group)
            anim_group.start()

    def _on_tick(self) -> None:
        """Called periodically to update message timeouts."""
        if not self._visible_messages and not self._pending_queue:
            self._tick_timer.stop()
            return

        # Check if we're in "idle" state - only persistent messages visible, nothing pending
        # Exclude EXITING messages from this check since they're on their way out
        active_messages = [m for m in self._visible_messages if m.state != MessageState.EXITING]

        # Check if any non-persistent messages are still active
        has_non_persistent = any(
            msg.text not in self.PERSISTENT_MESSAGES for msg in active_messages
        )

        is_idle = (
            not self._pending_queue
            and active_messages
            and all(msg.text in self.PERSISTENT_MESSAGES for msg in active_messages)
        )

        # Update remaining time for visible messages
        # Messages expire in FIFO order (oldest/leftmost first)
        oldest_ready_to_expire = None

        for msg in self._visible_messages:
            # Persistent messages should freeze their timeout if:
            # 1. We're idle (only persistent messages, nothing pending), OR
            # 2. There are still non-persistent messages active (wait for them to clear)
            should_persist = msg.text in self.PERSISTENT_MESSAGES and (
                is_idle or has_non_persistent
            )

            if msg.state == MessageState.ENTERING:
                # Track time in ENTERING state for safety fallback
                msg.entering_ticks += self.TICK_INTERVAL_MS

                # Don't consume timeout for persistent messages when idle
                if not should_persist:
                    msg.remaining_ms -= self.TICK_INTERVAL_MS

                # Force ENTERING messages to VISIBLE after animation should have completed
                # This is a safety fallback in case the animation's finished signal didn't fire
                if msg.entering_ticks >= 500:  # Animation is 175ms, give it 500ms max
                    msg.state = MessageState.VISIBLE

            elif msg.state == MessageState.VISIBLE:
                # Don't decrement timeout for persistent messages when idle
                if not should_persist:
                    msg.remaining_ms -= self.TICK_INTERVAL_MS

        # FIFO expiration: find the oldest non-EXITING message
        oldest_msg = None
        for msg in self._visible_messages:
            if msg.state != MessageState.EXITING:
                oldest_msg = msg
                break

        if oldest_msg:
            # Check if oldest is a frozen persistent message
            oldest_should_persist = oldest_msg.text in self.PERSISTENT_MESSAGES and (
                is_idle or has_non_persistent
            )
            oldest_is_frozen = oldest_should_persist and oldest_msg.remaining_ms > 0

            if oldest_is_frozen:
                # Oldest is frozen persistent - only allow LOW PRIORITY messages
                # to expire out of FIFO order. This lets "informational" messages
                # (like reader count updates) clear without blocking important
                # persistent status indicators.
                for msg in self._visible_messages:
                    if (msg.state != MessageState.EXITING and
                        msg.low_priority and
                        msg.remaining_ms <= 0):
                        self._animate_slide_out(msg)
                        break
            elif oldest_msg.remaining_ms <= 0:
                # Normal FIFO: expire oldest if timed out
                self._animate_slide_out(oldest_msg)

    def _update_badge(self) -> None:
        """Update the queue badge visibility and text."""
        count = len(self._pending_queue)
        if count > 0:
            self._badge.setText(f"+{count}")
            self._badge.show()
        else:
            self._badge.hide()

    def resizeEvent(self, event) -> None:
        """Handle resize to potentially show more messages."""
        super().resizeEvent(event)
        self._try_show_next_message()

    def sizeHint(self) -> QSize:
        """Return the preferred size."""
        return QSize(200, 24)


class StatusBar(QWidget):
    """
    Status bar widget that displays rotating status messages.

    Can be used standalone or with EventBus integration:
    - Direct: statusbar.add_message("Hello")
    - EventBus: Automatically subscribes to StatusMessageEvent, ErrorEvent

    Example:
        # Standalone usage
        status = StatusBar()
        status.add_message("Ready.")

        # With EventBus (auto-subscribed)
        status = StatusBar(subscribe_to_events=True)
        EventBus.instance().emit(StatusMessageEvent(message="Hello"))
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        initial_message: str = "Ready.",
        subscribe_to_events: bool = True,
    ):
        """
        Initialize the status bar.

        Args:
            parent: Parent widget
            initial_message: Initial status message
            subscribe_to_events: If True, subscribe to EventBus events
        """
        super().__init__(parent)

        # Create layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create message queue widget
        self._queue = MessageQueue(self)
        layout.addWidget(self._queue)

        # Add initial message
        if initial_message:
            self._queue.add_message(initial_message)

        # Subscribe to EventBus if requested
        self._event_bus: Optional[EventBus] = None
        if subscribe_to_events:
            self._subscribe_to_events()

    def _subscribe_to_events(self) -> None:
        """Subscribe to EventBus events."""
        self._event_bus = EventBus.instance()
        self._event_bus.subscribe(StatusMessageEvent, self._on_status_message)
        self._event_bus.subscribe(ErrorEvent, self._on_error)

    def _on_status_message(self, event: StatusMessageEvent) -> None:
        """Handle StatusMessageEvent."""
        self.add_message(event.message)

    def _on_error(self, event: ErrorEvent) -> None:
        """Handle ErrorEvent by displaying error message."""
        self.add_message(f"Error: {event.message}")

    def add_message(self, message: str) -> None:
        """
        Add a message to display.

        Args:
            message: Message text to show
        """
        self._queue.add_message(message)

    def set_text(self, text: str) -> None:
        """
        Set a message directly (clears queue and shows this message).

        Args:
            text: Text to display immediately
        """
        self._queue.clear()
        if text:
            self._queue.add_message(text)

    def clear(self) -> None:
        """Clear all pending messages."""
        self._queue.clear()

    def unsubscribe(self) -> None:
        """Unsubscribe from EventBus events."""
        if self._event_bus:
            self._event_bus.unsubscribe(StatusMessageEvent, self._on_status_message)
            self._event_bus.unsubscribe(ErrorEvent, self._on_error)
            self._event_bus = None

    @property
    def message_queue(self) -> MessageQueue:
        """Get the message queue for direct access."""
        return self._queue
