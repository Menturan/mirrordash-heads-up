import json
from pathlib import Path

from jinja2 import (  # the mirror's template engine, the same autoescape
    Environment,
    FileSystemLoader,
    select_autoescape,
)

from mirrordash_heads_up import plugin
from mirrordash_heads_up.plugin import HeadsUpModule

PACKAGE = Path(plugin.__file__).parent
SCHEMA = json.loads((PACKAGE / "config_schema.json").read_text())
DEFAULTS = {key: prop["default"] for key, prop in SCHEMA["properties"].items()}
# The mirror's environment (features/modules/loader.py): templates are .html, so they are autoescaped
ENV = Environment(loader=FileSystemLoader(PACKAGE / "templates"), autoescape=select_autoescape(["html", "xml"]))


class Clock:
    """The module's time, moved by hand."""
    t = 1000.0

    def __call__(self):
        return self.t


def make_module(**settings):
    module = HeadsUpModule({**DEFAULTS, **settings})
    module.render_template = lambda name, **context: ENV.get_template(name).render(translations={}, **context)
    module.now = Clock()
    return module
