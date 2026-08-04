"""Pure navigation state machine for unit tests and shared semantics."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NavState:
    screen: str = "home"
    focus_index: int = 0
    items: list[str] = field(default_factory=list)
    confirm_action: str | None = None
    wrap: bool = True
    diagnostics_mode: bool = False

    def set_items(self, items: list[str]) -> None:
        self.items = list(items)
        if self.focus_index >= len(self.items):
            self.focus_index = max(0, len(self.items) - 1)
        if self.focus_index < 0:
            self.focus_index = 0

    @property
    def focused(self) -> str | None:
        if not self.items:
            return None
        return self.items[self.focus_index]

    def next(self) -> str | None:
        if not self.items:
            return None
        if self.focus_index >= len(self.items) - 1:
            if self.wrap:
                self.focus_index = 0
            return self.focused
        self.focus_index += 1
        return self.focused

    def prev(self) -> str | None:
        if not self.items:
            return None
        if self.focus_index <= 0:
            if self.wrap:
                self.focus_index = len(self.items) - 1
            return self.focused
        self.focus_index -= 1
        return self.focused

    def apply_intent(self, intent: str) -> str | None:
        """Apply a navigation intent. Returns focused item on select, else None."""
        if intent == "next":
            self.next()
            return None
        if intent == "prev":
            self.prev()
            return None
        if intent == "back":
            if self.confirm_action:
                self.confirm_action = None
                return None
            if self.screen != "home":
                self.screen = "home"
                self.focus_index = 0
            return None
        if intent == "select":
            return self.focused
        return None
