# Example: a to-do list with one planted bug

`index.html` is a to-do list in a single file: add items, mark them done, delete them.
One of those actions has a bug. It's here to try Löb end to end without your own app.

```bash
cd examples/todo
python -m http.server 8000          # leave it running; continue in a second terminal

cd examples/todo
export WEBSITE_URL=http://localhost:8000
export ANTHROPIC_API_KEY=...        # or put both in a .env here
loeb check                          # no LLM call: the page loads, every selector matches
loeb run "Test adding, completing and deleting items"
```

`loeb.json` and `loeb-target.md` here are what a coding agent would write after
reading `index.html` and following `loeb guide`.
