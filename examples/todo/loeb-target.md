## How the app works
A single-page to-do list. Users add items, mark them done and delete them. There is
no sign-in and no server beyond a static file server; the list is saved in the
browser's localStorage, so it survives a reload.

## Pages and selectors
`/` is the only page.
- `#new-todo`: the text input for a new item.
- `#add`: the Add button (pressing Enter in the input also adds).
- `#todo-list`: the list. Each item is an `li.todo-item` with a `data-id`, holding a
  `span.todo-text` (click it to toggle done; done items get the class `done`) and a
  `button.delete`. The newest item is shown first.
- `#count`: "N items", the number of items.

## Data to verify
The list is stored in localStorage under the key `todos`: a JSON array of
`{id, text, done}`, oldest first. There is no database. To check that a change was
saved, reload the page and compare the list and the count with what you expect.

## API endpoints
None.
