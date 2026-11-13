# mirrordash-heads-up

A short text in the centre of the mirror for a few seconds, sent by your home automation: "Someone is at the door",
"The laundry is done", "The bus leaves in 6 minutes". It fades in, stays for a few seconds and fades away; the rest of
the time the card is empty and the mirror is a mirror.

![Screenshot](screenshot.png)

## Set it up

1. Install the module from **Admin → Modules** and turn it on.
2. Put it in the centre (`middle_center`), in a spot of its own: the text is large and meant to be alone there.
   (A module cannot choose its own place, so the position is yours to set.)
3. Turn on MQTT control for the instance: **Admin → Settings → MQTT**, share the *Heads-up* module and allow it to
   be controlled. Home Assistant then gets a text entity, `text.<mirror>_heads_up_heads_up` (the exact name is shown in
   Home Assistant under the mirror's device).
4. Optional, in the module's settings: **Seconds Shown** (3 to 120, default 15) and **Text Size** (Normal or Large).

## Send a heads-up from Home Assistant

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

- A new text while one is showing replaces it and starts the time again.
- An empty text (`value: ""`) takes it away at once.
- Spaces and line breaks are collapsed to single spaces, and everything is shown as plain text (no HTML).
- A long text (over 100 characters) is set a little smaller so it fits; it always wraps inside the centre.

## Limits

- **A text is at most 255 characters**: that is the platform's limit for a text entity, and what Home Assistant
  allows here.
- **A heads-up that arrives while the screen is resting is shown on a dark screen**, and is gone when someone
  arrives: a module cannot wake the screen, and the time runs out while it sleeps.
- One heads-up at a time: no queue, no history, no priorities, no colours or sounds.
- With a mirror that reloads its screen (a restart of the screen, a new browser connection) a heads-up still showing is
  drawn again from its start, so it can stay a few seconds longer than set.

## Develop

```bash
uv run pytest                    # the module's tests
uvx mirrordash-sdk validate .    # checks the module before you push it
```
