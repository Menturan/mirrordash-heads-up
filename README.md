# mirrordash-heads-up

A short text in the centre of the mirror for a few seconds: "Someone is at the door", "The laundry is done", "The bus
leaves in 6 minutes". It fades in, stays for a few seconds and fades away; the rest of the time the card is empty and
the mirror is a mirror. Texts can come from Home Assistant, a web call, another module, a schedule or a watched web
address, and they wait in a queue.

![Screenshot](screenshot.png)

## Set it up

1. Install the module from **Admin → Modules** and turn it on.
2. Put it in the centre (`middle_center`), in a spot of its own: the text is large and meant to be alone there.
   (A module cannot choose its own place, so the position is yours to set.)
3. In the module's settings: **Time shown** (3 to 120, default 15), **Text size** (Normal or Large) and
   **Keep a waiting heads-up for** (1 to 72, default 12). Then set up the ways you want to send (below).

Whichever way a text comes, it is made one line (spaces and line breaks collapse), cut to 255 characters and shown as
plain text (no HTML). A text over 100 characters is set a little smaller so it fits.

## Ways to send a heads-up

### Home Assistant (MQTT)

Turn on MQTT control for the instance: **Admin → Settings → MQTT**, share the *Heads-up* module and allow it to be
controlled. Home Assistant then gets a text entity, `text.<mirror>_heads_up_heads_up` (the exact name is shown in Home
Assistant under the mirror's device).

```yaml
automation:
  - alias: "Doorbell on the mirror"
    triggers:
      - trigger: state
        entity_id: binary_sensor.front_door_ring
        to: "on"
    actions:
      - action: text.set_value
        target:
          entity_id: text.mirror_heads_up_heads_up
        data:
          value: "Someone is at the door"
```

An empty text (`value: ""`) is the one exception to "empty is ignored": it ends the text showing **and empties the
queue**.

### HTTP

`POST http://mirrordash.local/api/modules/<name>/show`, where `<name>` is the module's name shown on its card in the
admin page. Send JSON with `text` and, if you like, `seconds` (3 to 120; anything else uses the setting):

```bash
curl -X POST http://mirrordash.local/api/modules/<name>/show \
  -H "Content-Type: application/json" -H "X-Token: <your token>" \
  -d '{"text": "The laundry is done", "seconds": 20}'
```

The text can also be a query parameter, which is easier for phone shortcuts and simple devices:
`POST http://mirrordash.local/api/modules/<name>/show?text=The%20laundry%20is%20done`. In an iPhone Shortcut: *Get
contents of URL*, the address above, Method *POST*, and under Headers `X-Token` (a token may instead be given as
`?token=...`, but a header keeps it out of logs and history).

The answer is `{"ok": true, "waiting": 2}` (how many wait their turn), `403` for a wrong or missing token (when one is
set) and `422` for no text. A GET never shows anything, so a browser prefetch cannot put text on the mirror.

The **Access token** setting is optional. Empty, anyone on your home network can send; with a token set, every call must carry
it.

### From other modules

Under **Modules that may send**, add the package name of each module whose heads-ups you want, for example
`mirrordash_now_playing_spotify`. That module must be installed and set to send. The convention for module authors:
publish the event `<your_package>.heads_up` with a text and, optionally, seconds:

```python
event_bus = config.get("event_bus")  # not there in a test
if event_bus:
    event_bus.publish(f"{self.name}.heads_up", {"text": "Door open", "seconds": 10}, public=True)
```

Only the listed packages are heard, and their data is checked (a text, and seconds from 3 to 120).

### At set times

**Texts at Set Times**: add a row with a time, the days (none ticked means every day) and a text. It is shown once when
its time comes, in the mirror's time zone. Only whole minutes are checked, once a minute. A row never fires for a time
before the module started.

### From a watched address

**Address to watch** (empty: off) is asked every **Time between checks** (10 to 3600, default 60). The text is shown
when it changes. The first answer after a start is only remembered, not shown. If the answer is JSON, **Field in a JSON
Answer** is the path to the text in it (`state.message`; a list item is a number: `items.0.name`); empty means the
answer's plain text. A failed check is ignored. The address may be on the home network or the internet.

## The queue

- A text that arrives while another shows waits its turn: first in, first out. Nothing replaces a text showing.
- Between two texts the card is empty for a moment, so each fades in on its own.
- At most 20 wait; when more arrive, the oldest waiting one is dropped.
- A text that arrives while the card is not on the screen (screen resting, privacy mode, the module's schedule) is kept
  and shown when the card is back, a few seconds after.
- A waiting text older than **Keep a waiting heads-up for** is dropped instead of shown. Age counts from arrival.

## Limits

- **A text that starts in the last couple of seconds before the screen goes off is cut**: the mirror tells a module
  only after the screen has faded out.
- **The first text after the screen wakes starts a few seconds late** (3 s), so its start is not hidden by the screen
  fading in. An owner with a long start delay or fade may still see its start clipped.
- **The queue is not saved**: a restart of the module (also when a setting is saved) loses what waits.
- **Anyone on the home network can send a heads-up unless a token is set.**
- A module cannot wake the screen: a text sent to a resting mirror waits until someone wakes it.
- No history, priorities, colours or sounds.
- With a mirror that reloads its screen (a restart of the screen, a new browser connection) a heads-up still showing is
  drawn again from its start, so it can stay a few seconds longer than set.

## Develop

```bash
uv run pytest                    # the module's tests
uvx mirrordash-sdk validate .    # checks the module before you push it
```
