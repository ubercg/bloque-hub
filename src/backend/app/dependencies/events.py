"""Dependencies for event dispatching (e.g. reservation confirmed -> fulfillment)."""

from fastapi import Request

from app.modules.booking.services import EventDispatcher


def get_event_dispatcher(request: Request) -> EventDispatcher:
    """Return the app's event dispatcher (set at startup). Falls back to no-op if not set."""
    return getattr(request.app.state, "event_dispatcher", None) or EventDispatcher()
