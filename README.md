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
Type `@` anywhere in the input to autocomplete files and folders relative to the current directory.
File references like `/cmd @foo.py @src/bar.py` are passed to commands as `foo.py src/bar.py`.

- `/help` — list available commands
- `/exit` — exit the application
- `/clear` — clear the log view
- `/view log|inspector` — switch views
- `Up arrow` — recall previous commands
