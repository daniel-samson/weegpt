<p align="center">
  <img src="assets/mascot.jpg?v=2" alt="WeeGPT mascot" width="128" />
  <br />
  <strong>WeeGPT</strong>
  <br />
  I built a Wee Generative Pre-trained Transformer from scratch to understand the GPT architecture.
</p>

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

## TUI Commands

Type `/` to open the command palette, then filter or select a command.
Type `@` anywhere in the input to autocomplete files and folders recursively under the current directory.
File references like `/cmd @foo.py @src/bar.py` are passed to commands as `foo.py src/bar.py`.
Commands can also declare their own argument autocomplete (e.g. `/view ` shows `log` and `inspector`).

- `/help` — list available commands
- `/exit` — exit the application
- `/clear` — clear the log view
- `/view log|inspector` — switch views
- `/throbber <message>` — show/update the highland cow throbber (no arg hides it)
- `Up arrow` — recall previous commands

### Argument autocomplete

Pass an `args` tree to `@command` to describe valid argument positions:

```python
from tui import command, choices

@command("/view", args=choices("log", "inspector"))           # /view log | /view inspector
@command("/echo", args=...)                                   # free-form, no autocomplete
@command("/foo",  args={"init": choices("default", "fresh"),  # /foo init default | /foo init fresh
                        "save": None,                          # /foo save (done)
                        "load": ...})                          # /foo load <anything>
```

Each node in the tree is one of:

- `None` — terminal, palette stops after this position
- `dict` — fixed choices; each key maps to the next node
- `...` (Ellipsis) — free-form from here
- a callable `(partial, prior_args) -> list[str]` — dynamic suggestions

