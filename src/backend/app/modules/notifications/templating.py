"""Render de plantillas Jinja2 para notificaciones por email."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_templates_dir = Path(__file__).resolve().parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_templates_dir)),
    autoescape=select_autoescape(["html"]),
)


def render(template_name: str, **context) -> str:
    """Renderiza la plantilla con el contexto; devuelve HTML."""
    template = _env.get_template(template_name)
    return template.render(**context)
