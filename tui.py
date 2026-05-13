from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, RichLog, Static


# ---------------------------------------------------------------------------
# Backend protocol — implement this in weegpt.py to wire up your model
# ---------------------------------------------------------------------------

@runtime_checkable
class Backend(Protocol):
    def handle_input(self, text: str) -> str:
        """Process free-form user input and return a response string."""
        ...


class StubBackend:
    """Default backend used when no model is connected yet."""

    def handle_input(self, text: str) -> str:
        return f"[dim](no backend connected)[/dim] echo: {text}"


# ---------------------------------------------------------------------------
# Command registry
# ---------------------------------------------------------------------------

@dataclass
class Command:
    name: str
    help: str
    handler: object  # callable(app, args) -> None

    async def __call__(self, app: WeeGPTApp, args: str) -> None:
        result = self.handler(app, args)
        if hasattr(result, "__await__") or hasattr(result, "send"):
            await result


_commands: dict[str, Command] = {}


def command(name: str, *, help: str = ""):
    """Decorator to register a slash command.

    Usage:
        @command("/step", help="Step through one forward pass")
        async def cmd_step(app, args):
            ...
    """
    def decorator(fn):
        _commands[name] = Command(name=name, help=help, handler=fn)
        return fn
    return decorator


def get_commands() -> dict[str, Command]:
    return _commands


# ---------------------------------------------------------------------------
# Built-in commands
# ---------------------------------------------------------------------------

@command("/help", help="Show available commands")
async def cmd_help(app: WeeGPTApp, args: str) -> None:
    log = app.query_one("#log", RichLog)
    log.write("[bold underline]Commands[/]")
    for name, cmd in sorted(_commands.items()):
        log.write(f"  [cyan]{name}[/] — {cmd.help or 'no description'}")


@command("/quit", help="Exit the application")
async def cmd_quit(app: WeeGPTApp, args: str) -> None:
    app.exit()


@command("/clear", help="Clear the log view")
async def cmd_clear(app: WeeGPTApp, args: str) -> None:
    app.query_one("#log", RichLog).clear()


@command("/view", help="Switch view: /view log | /view inspector")
async def cmd_view(app: WeeGPTApp, args: str) -> None:
    name = args.strip().lower()
    if name == "log":
        app.activate_view("log")
    elif name == "inspector":
        app.activate_view("inspector")
    else:
        log = app.query_one("#log", RichLog)
        log.write(f"[red]Unknown view:[/] {name}. Use 'log' or 'inspector'.")


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class LogView(Vertical):
    """Main chat/log view."""

    def compose(self) -> ComposeResult:
        yield RichLog(id="log", highlight=True, markup=True, wrap=True)


class InspectorView(Vertical):
    """Placeholder inspector view for tensor visualizations."""

    def compose(self) -> ComposeResult:
        yield Static(
            "[dim]Inspector view — nothing here yet. "
            "Wire up tensor visualizations in weegpt.py.[/]",
            id="inspector-placeholder",
        )


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class WeeGPTApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }

    #view-container {
        height: 1fr;
    }

    LogView, InspectorView {
        height: 1fr;
    }

    #log {
        height: 1fr;
        border: solid $accent;
        padding: 0 1;
    }

    #inspector-placeholder {
        height: 1fr;
        border: solid $accent;
        padding: 1 2;
        color: $text-muted;
    }

    #prompt {
        dock: bottom;
        margin: 0 0;
    }

    #view-label {
        dock: top;
        height: 1;
        padding: 0 1;
        background: $accent;
        color: $text;
        text-style: bold;
    }
    """

    TITLE = "WeeGPT"
    SUB_TITLE = "tiny transformer playground"

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True, priority=True),
        Binding("tab", "switch_view", "Switch view", show=True),
    ]

    def __init__(self, backend: Backend | None = None) -> None:
        super().__init__()
        self.backend: Backend = backend or StubBackend()
        self._current_view: str = "log"
        self._command_history: list[str] = []
        self._history_index: int = -1
        self._views: dict[str, type] = {
            "log": LogView,
            "inspector": InspectorView,
        }

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("view: log", id="view-label")
        with Vertical(id="view-container"):
            yield LogView()
        yield Input(placeholder="Type a command (/help) or message…", id="prompt")
        yield Footer()

    def on_mount(self) -> None:
        log = self.query_one("#log", RichLog)
        log.write("[bold green]WeeGPT[/] ready. Type [cyan]/help[/] for commands.")
        self.query_one("#prompt", Input).focus()

    # -- view switching -------------------------------------------------------

    def activate_view(self, name: str) -> None:
        if name not in self._views:
            return
        self._current_view = name
        container = self.query_one("#view-container", Vertical)
        container.remove_children()
        container.mount(self._views[name]())
        self.query_one("#view-label", Static).update(f"view: {name}")
        self.query_one("#prompt", Input).focus()

    def action_switch_view(self) -> None:
        names = list(self._views.keys())
        idx = names.index(self._current_view)
        next_name = names[(idx + 1) % len(names)]
        self.activate_view(next_name)

    # -- input handling -------------------------------------------------------

    @on(Input.Submitted, "#prompt")
    async def on_prompt_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.clear()
        if not text:
            return

        self._command_history.append(text)
        self._history_index = -1

        if self._current_view != "log":
            self.activate_view("log")

        log = self.query_one("#log", RichLog)

        if text.startswith("/"):
            parts = text.split(maxsplit=1)
            cmd_name = parts[0].lower()
            cmd_args = parts[1] if len(parts) > 1 else ""
            cmd = _commands.get(cmd_name)
            if cmd:
                await cmd(self, cmd_args)
            else:
                log.write(f"[red]Unknown command:[/] {cmd_name}. Try /help.")
        else:
            log.write(f"[bold]> {text}[/]")
            response = self.backend.handle_input(text)
            log.write(response)

    # -- command history via up/down arrow ------------------------------------

    def on_key(self, event) -> None:
        prompt = self.query_one("#prompt", Input)
        if not prompt.has_focus:
            return

        if event.key == "up":
            if self._command_history:
                if self._history_index == -1:
                    self._history_index = len(self._command_history) - 1
                elif self._history_index > 0:
                    self._history_index -= 1
                prompt.value = self._command_history[self._history_index]
                prompt.cursor_position = len(prompt.value)
            event.prevent_default()
        elif event.key == "down":
            if self._history_index != -1:
                if self._history_index < len(self._command_history) - 1:
                    self._history_index += 1
                    prompt.value = self._command_history[self._history_index]
                else:
                    self._history_index = -1
                    prompt.value = ""
                prompt.cursor_position = len(prompt.value)
            event.prevent_default()
