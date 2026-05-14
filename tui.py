from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Header, Input, OptionList, RichLog, Static
from textual.widgets.option_list import Option


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

# An ``ArgsNode`` describes what can appear at one argument position.
#
#   None       — terminal: no more autocomplete, command is "done".
#   Ellipsis   — free-form from here: user types anything, palette stays closed.
#   dict       — fixed choices; each key maps to the next ``ArgsNode``.
#   callable   — ``(partial, prior_args) -> list[str] | ArgsNode``; returns
#                suggestions for the current position, or another node to
#                descend into.
ArgsNode = object


def choices(*opts: str) -> dict[str, None]:
    """Shorthand for a level of terminal choices: ``choices("a", "b")``."""
    return {opt: None for opt in opts}


@dataclass
class Command:
    name: str
    help: str
    handler: object  # callable(app, args) -> None
    args: ArgsNode = None

    async def __call__(self, app: WeeGPTApp, args: str) -> None:
        result = self.handler(app, args)
        if hasattr(result, "__await__") or hasattr(result, "send"):
            await result


_commands: dict[str, Command] = {}


def command(name: str, *, help: str = "", args: ArgsNode = None):
    """Decorator to register a slash command.

    ``args`` is a tree describing valid argument positions. Use ``choices(...)``
    for a flat list, nest ``dict``s for multi-step args, ``...`` (Ellipsis)
    for free-form input, and ``None`` (the default) for commands that take no
    arguments::

        @command("/view", args=choices("log", "inspector"))
        @command("/load", args={"latest": None, "best": None})
        @command("/echo", args=...)
        @command("/exit")  # no args
    """
    def decorator(fn):
        _commands[name] = Command(name=name, help=help, handler=fn, args=args)
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


@command("/exit", help="Exit the application")
async def cmd_exit(app: WeeGPTApp, args: str) -> None:
    app.exit()


@command("/clear", help="Clear the log view")
async def cmd_clear(app: WeeGPTApp, args: str) -> None:
    app.query_one("#log", RichLog).clear()


@command(
    "/view",
    help="Switch view: /view log | /view inspector",
    args=choices("log", "inspector"),
)
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
    #view-label {
        height: 1;
        padding: 0 1;
        background: $accent;
        color: $text;
        text-style: bold;
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

    #prompt-area {
        height: auto;
        max-height: 14;
    }

    #command-palette {
        height: auto;
        max-height: 10;
        display: none;
        border: solid $accent;
        padding: 0;
    }

    #command-palette.visible {
        display: block;
    }

    #prompt {
        height: 3;
    }
    """

    TITLE = "WeeGPT"
    SUB_TITLE = "tiny transformer playground"

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
        # palette state — tracks what the palette is currently completing
        self._palette_mode: str | None = None  # "command" | "file" | None
        self._token_start: int = 0  # index of trigger char (/ or @) in input
        self._token_end: int = 0    # cursor position when palette opened

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("view: log", id="view-label")
        with Vertical(id="view-container"):
            yield LogView()
        with Vertical(id="prompt-area"):
            yield OptionList(id="command-palette")
            yield Input(
                placeholder="Type / for commands, @ for files, or enter a message…",
                id="prompt",
                select_on_focus=False,
            )

    def on_mount(self) -> None:
        log = self.query_one("#log", RichLog)
        log.write("[bold green]WeeGPT[/] ready. Type [cyan]/[/] to see commands.")
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

    # -- palette (commands and file refs) -------------------------------------

    def _detect_trigger(self, text: str, cursor: int):
        """Return a trigger descriptor for the token under the cursor.

        Returns a tuple shaped like one of:
            ("command", token_start, partial)
            ("file",    token_start, partial)
            ("arg",     token_start, partial, command_name, prior_args)
        or None when no palette should be shown.
        """
        # Walk back from cursor to the start of the current token.
        i = cursor
        while i > 0 and not text[i - 1].isspace():
            i -= 1
        token = text[i:cursor]

        if token.startswith("@"):
            return ("file", i, token[1:])

        # Command mode: "/" at position 0 and cursor still in the command name.
        if i == 0 and text.startswith("/"):
            return ("command", 0, text[1:cursor])

        # Argument mode: cursor is past the command name in a "/cmd ..." input.
        if text.startswith("/") and i > 0:
            head = text.split(maxsplit=1)[0].lower()
            cmd = _commands.get(head)
            if cmd is not None and cmd.args is not None:
                before = text[len(head):i].split()
                return ("arg", i, token, head, before)

        return None

    def _show_command_options(self, query: str) -> bool:
        palette = self.query_one("#command-palette", OptionList)
        q = query.lower()
        matches = [
            (name, cmd.help)
            for name, cmd in sorted(_commands.items())
            if q in name.lower() or q in (cmd.help or "").lower()
        ]
        palette.clear_options()
        if not matches:
            return False
        for name, help_text in matches:
            palette.add_option(Option(f"{name}  [dim]{help_text}[/]", id=name))
        palette.highlighted = 0
        return True

    _SKIP_DIRS = frozenset({
        ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
        "dist", "build", ".mypy_cache", ".pytest_cache", ".ruff_cache",
        ".idea", ".vscode", ".tox", ".cache", "site-packages",
    })

    def _show_file_options(self, partial: str) -> bool:
        palette = self.query_one("#command-palette", OptionList)
        cwd = Path.cwd()
        query = partial.replace("\\", "/").lower()
        max_results = 50

        matches: list[tuple[str, bool]] = []

        def walk(directory: Path) -> None:
            if len(matches) >= max_results:
                return
            try:
                entries = sorted(directory.iterdir(), key=lambda e: e.name.lower())
            except (PermissionError, OSError):
                return
            for entry in entries:
                if len(matches) >= max_results:
                    return
                if entry.name.startswith("."):
                    continue
                if entry.is_dir() and entry.name in self._SKIP_DIRS:
                    continue
                rel = entry.relative_to(cwd).as_posix()
                is_dir = entry.is_dir()
                if not query or query in rel.lower():
                    matches.append((rel + ("/" if is_dir else ""), is_dir))
                if is_dir:
                    walk(entry)

        walk(cwd)

        palette.clear_options()
        if not matches:
            return False
        # Directories first, then files; shorter paths win ties.
        matches.sort(key=lambda m: (not m[1], len(m[0]), m[0].lower()))
        for value, is_dir in matches:
            icon = "[cyan]▸[/]" if is_dir else "[dim]·[/]"
            palette.add_option(Option(f"{icon} {value}", id=value))
        palette.highlighted = 0
        return True

    def _update_palette(self) -> None:
        prompt = self.query_one("#prompt", Input)
        trigger = self._detect_trigger(prompt.value, prompt.cursor_position)
        palette = self.query_one("#command-palette", OptionList)

        if trigger is None:
            self._hide_palette()
            return

        mode = trigger[0]
        start = trigger[1]
        partial = trigger[2]

        if mode == "command":
            shown = self._show_command_options(partial)
        elif mode == "file":
            shown = self._show_file_options(partial)
        else:  # arg
            cmd_name = trigger[3]
            prior = trigger[4]
            shown = self._show_arg_options(cmd_name, partial, prior)

        if not shown:
            self._hide_palette()
            return

        self._palette_mode = mode
        self._token_start = start
        self._token_end = prompt.cursor_position
        palette.add_class("visible")

    @staticmethod
    def _walk_args(node: ArgsNode, prior: list[str]) -> ArgsNode:
        """Walk the args tree consuming ``prior`` tokens, return the node at
        the cursor position. Returns ``None`` when args are exhausted, or
        ``...`` when the remaining position is free-form."""
        for arg in prior:
            if node is None or node is Ellipsis:
                return node
            if callable(node):
                try:
                    node = node(arg, prior)
                except Exception:
                    return None
            if isinstance(node, dict):
                if arg in node:
                    node = node[arg]
                else:
                    # Unknown token: treat the rest of the line as free-form.
                    return Ellipsis
            else:
                return None
        return node

    def _show_arg_options(self, cmd_name: str, partial: str, prior: list[str]) -> bool:
        palette = self.query_one("#command-palette", OptionList)
        cmd = _commands.get(cmd_name)
        if cmd is None or cmd.args is None:
            return False

        node = self._walk_args(cmd.args, prior)
        if node is None or node is Ellipsis:
            return False

        suggestions: list[str] = []
        if isinstance(node, dict):
            p = partial.lower()
            suggestions = sorted(k for k in node if k.lower().startswith(p))
        elif callable(node):
            try:
                result = node(partial, prior)
            except Exception:
                return False
            if isinstance(result, (list, tuple)):
                p = partial.lower()
                suggestions = [s for s in result if s.lower().startswith(p)]

        if not suggestions:
            return False
        palette.clear_options()
        for value in suggestions:
            palette.add_option(Option(f"[cyan]·[/] {value}", id=value))
        palette.highlighted = 0
        return True

    def _hide_palette(self) -> None:
        palette = self.query_one("#command-palette", OptionList)
        palette.remove_class("visible")
        palette.clear_options()
        self._palette_mode = None

    def _apply_selection(self, value: str) -> None:
        """Replace the active token in the input with ``value``."""
        if self._palette_mode is None:
            return
        prompt = self.query_one("#prompt", Input)
        text = prompt.value
        mode = self._palette_mode

        if mode == "command":
            # value already includes the leading "/" (e.g. "/view")
            new_text = value + " " + text[self._token_end:]
            new_cursor = len(value) + 1
        elif mode == "file":
            # preserve "@" prefix; append "/" if value is a dir,
            # otherwise a trailing space to move on to the next arg.
            is_dir = value.endswith("/")
            suffix = "" if is_dir else " "
            new_text = (
                text[: self._token_start]
                + "@"
                + value
                + suffix
                + text[self._token_end:]
            )
            new_cursor = self._token_start + 1 + len(value) + len(suffix)
        else:  # arg
            new_text = (
                text[: self._token_start]
                + value
                + " "
                + text[self._token_end:]
            )
            new_cursor = self._token_start + len(value) + 1

        prompt.value = new_text
        prompt.cursor_position = new_cursor
        # Collapse any selection that the input may have created.
        try:
            prompt.selection = type(prompt.selection)(new_cursor, new_cursor)
        except Exception:
            pass
        if mode == "file" and value.endswith("/"):
            self._update_palette()
        else:
            self._hide_palette()
        prompt.focus()

    @on(Input.Changed, "#prompt")
    def on_prompt_changed(self, event: Input.Changed) -> None:
        self._update_palette()

    @on(OptionList.OptionSelected, "#command-palette")
    def on_palette_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._apply_selection(event.option.id)

    # -- input handling -------------------------------------------------------

    @staticmethod
    def _parse_args(raw: str) -> str:
        """Strip the leading "@" from each whitespace-delimited token."""
        return " ".join(tok[1:] if tok.startswith("@") else tok for tok in raw.split())

    @on(Input.Submitted, "#prompt")
    async def on_prompt_submitted(self, event: Input.Submitted) -> None:
        palette = self.query_one("#command-palette", OptionList)
        palette_visible = palette.has_class("visible")

        # When the palette is open, Enter just autocompletes — it never
        # executes. The user presses Enter a second time to run.
        if palette_visible and palette.highlighted is not None:
            option = palette.get_option_at_index(palette.highlighted)
            self._apply_selection(option.id)
            return

        text = event.value.strip()
        event.input.clear()
        self._hide_palette()
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
            cmd_args = self._parse_args(parts[1]) if len(parts) > 1 else ""
            cmd = _commands.get(cmd_name)
            if cmd:
                await cmd(self, cmd_args)
            else:
                log.write(f"[red]Unknown command:[/] {cmd_name}. Try /help.")
        else:
            log.write(f"[bold]> {text}[/]")
            response = self.backend.handle_input(self._parse_args(text))
            log.write(response)

    # -- keyboard navigation --------------------------------------------------

    def on_key(self, event) -> None:
        prompt = self.query_one("#prompt", Input)
        palette = self.query_one("#command-palette", OptionList)
        palette_visible = palette.has_class("visible")

        if not prompt.has_focus and not palette.has_focus:
            return

        if event.key == "escape" and palette_visible:
            self._hide_palette()
            prompt.focus()
            event.prevent_default()
            return

        if palette_visible and event.key in ("up", "down"):
            palette.focus()
            return

        # Enter while the palette has focus is handled by OptionList itself,
        # which emits OptionSelected — see on_palette_option_selected.

        if prompt.has_focus and not palette_visible:
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
