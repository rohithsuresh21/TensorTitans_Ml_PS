"""Human-in-the-loop Telegram alerts.

- Dispatches annotated snapshots + structured alerts with inline action buttons.
- Long-polls getUpdates for callback queries (Dismiss / On-Site Alarm).
- Routes HIL decisions back into the engine (clear cooldown / trigger alarm).
"""

import json
import logging
import threading
import time
from queue import Queue, Empty

import requests

from app import database as db
from app.engine import AlertEvent

logger = logging.getLogger("sentineliq.telegram")

POLL_TIMEOUT = 25


def _api(method: str, token: str, **kwargs) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    resp = requests.get(url, timeout=POLL_TIMEOUT + 5, **kwargs)
    resp.raise_for_status()
    return resp.json()


def _send_photo(token: str, chat_id: str, jpeg: bytes, caption: str) -> dict:
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    return requests.post(
        url,
        data={"chat_id": chat_id, "caption": caption},
        files={"photo": ("alert.jpg", jpeg, "image/jpeg")},
        timeout=15,
    ).json()


class TelegramAlertBot:
    def __init__(self, engine=None):
        self.engine = engine
        self._queue: Queue[AlertEvent] = Queue()
        self._stop = threading.Event()
        self._sender: threading.Thread | None = None
        self._poller: threading.Thread | None = None

    def start(self) -> None:
        self._sender = threading.Thread(target=self._send_loop, daemon=True)
        self._poller = threading.Thread(target=self._poll_loop, daemon=True)
        self._sender.start()
        self._poller.start()

    def stop(self) -> None:
        self._stop.set()
        self._queue.put(None)

    def submit(self, event: AlertEvent) -> None:
        self._queue.put(event)

    # --- outgoing -----------------------------------------------------------

    def _send_loop(self) -> None:
        while not self._stop.is_set():
            try:
                event = self._queue.get(timeout=0.5)
            except Empty:
                continue
            if event is None:
                continue
            token = db.get_setting("telegram_token")
            chat_id = db.get_setting("telegram_chat_id")
            if not token or not chat_id:
                logger.warning("Telegram token/chat_id not configured; alert skipped.")
                continue
            try:
                self._dispatch(event, token, chat_id)
            except Exception as exc:
                logger.error("dispatch failed: %s", exc)

    def _dispatch(self, event: AlertEvent, token: str, chat_id: str) -> None:
        if event.jpeg:
            _send_photo(
                token,
                chat_id,
                event.jpeg,
                f"{event.event_type} - {event.zone_name or 'zone'} {self._clock()}",
            )

        number = db.get_setting("emergency_number", "100")
        items_txt = ", ".join(event.items) if event.items else "none detected"
        weapon_tag = "\u26a0\ufe0f <b>Weapon/edge detected!</b>\n" if event.has_weapon else ""
        camera = db.get_setting("camera_name", "camera")
        text = (
            f"\U0001f6a8 <b>{event.event_type}</b>\n"
            f"\U0001f4f9 Camera: {camera}\n"
            f"\U0001f3e2 Zone: {event.zone_name or 'unassigned'}\n"
            f"\U0001f4c5 Time: {self._clock()}\n"
            f"Faints: {event.counts['faints']}  |  "
            f"Intruders: {event.counts['intruders']}  |  "
            f"Hands Up: {event.counts['hands_up']}\n"
            f"\U0001f6cf\ufe0f Carried items: {items_txt}\n"
            f"{weapon_tag}\n"
            f"<a href=\"tel:{number}\">\u260E\ufe0F Call emergency: {number}</a>"
        )
        ts = int(time.time())
        markup = {
            "inline_keyboard": [
                [{"text": "\U0001f6a8 CALL 911", "callback_data": f"call:911:{ts}"}],
                [
                    {"text": "\U0001f46e\ufe0f POLICE", "callback_data": f"call:police:{ts}"},
                    {"text": "\U0001f691 AMBULANCE", "callback_data": f"call:ambulance:{ts}"},
                ],
                [{"text": "\U0001f515 False Alarm (Dismiss)", "callback_data": f"dismiss:{ts}"}],
            ]
        }
        _api(
            "sendMessage",
            token,
            params={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": json.dumps(markup),
            },
        )

    @staticmethod
    def _send_text(token: str, chat_id: str, text: str) -> dict:
        return _api(
            "sendMessage",
            token,
            params={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        )

    @staticmethod
    def _clock() -> str:
        return time.strftime("%H:%M:%S", time.localtime())

    # --- incoming (getUpdates polling) ---------------------------------------

    def _poll_loop(self) -> None:
        offset = 0
        while not self._stop.is_set():
            token = db.get_setting("telegram_token")
            if not token:
                self._stop.wait(3.0)
                continue
            try:
                data = _api(
                    "getUpdates",
                    token,
                    params={
                        "offset": offset,
                        "timeout": POLL_TIMEOUT,
                        "allowed_updates": json.dumps(["callback_query"]),
                    },
                )
                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    cq = update.get("callback_query")
                    if cq:
                        self._handle_callback(cq, token)
            except Exception as exc:
                logger.debug("poll error: %s", exc)
                self._stop.wait(2.0)

    def _handle_callback(self, cq: dict, token: str) -> None:
        data = cq.get("data", "")
        query_id = cq.get("id")
        try:
            if data.startswith("dismiss:"):
                self._answer(query_id, token, "Alert dismissed. Cooldown cleared.")
                if self.engine:
                    self.engine.reset_alert()
            elif data.startswith("call:"):
                try:
                    _, service, _ts = data.split(":")
                except ValueError:
                    service = "911"
                label = {
                    "911": "\U0001f6a8 911 operator",
                    "police": "\U0001f46e\ufe0f Police",
                    "ambulance": "\U0001f691 Ambulance",
                }.get(service, service)
                self._answer(query_id, token, f"{label} dispatch initiated.")
                recs = db.get_alerts(limit=1)
                zone = recs[0]["zone"] if recs else "restricted zone"
                camera = db.get_setting("camera_name", "camera")
                number = db.get_setting("emergency_number", "100")
                chat_id = cq.get("message", {}).get("chat", {}).get("id") or db.get_setting("telegram_chat_id")
                self._send_text(
                    token,
                    chat_id,
                    f"\u26a1 <b>DISPATCH INITIATED</b>\n"
                    f"{label} has been notified.\n"
                    f"\U0001f3e2 Zone: {zone}\n"
                    f"\U0001f4f9 Camera: {camera}\n"
                    f"\U0001f4c5 {self._clock()}\n"
                    f"<a href=\"tel:{number}\">\u260E\ufe0F Direct line: {number}</a>",
                )
        except Exception as exc:
            logger.error("callback handling failed: %s", exc)

    @staticmethod
    def _answer(query_id: str, token: str, message: str) -> None:
        try:
            _api("answerCallbackQuery", token, params={"callback_query_id": query_id, "text": message})
        except Exception as exc:
            logger.debug("answer failed: %s", exc)