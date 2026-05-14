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
- `Up arrow` — recall previous commands

### Argument autocomplete

Pass a `complete` callable to `@command` to suggest values for arguments:

```python
from tui import command, static_args

@command("/load", help="Load a checkpoint", complete=static_args("latest", "best"))
async def cmd_load(app, args):
    ...
```

The callable receives `(partial, prior_args)` and returns a list of full suggestions.

