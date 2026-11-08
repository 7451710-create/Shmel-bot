import json
import os
import secrets
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = os.environ["BOT_TOKEN"]
SECRET = os.environ["WEBHOOK_SECRET"]
SELLER = "Shmel_ToT"
PRODUCTS = [
    "Piña Colada AUTO",
    "My Thai AUTO",
    "Banana Split AUTO",
    "Bello y Dulce AUTO",
    "Deliziosa AUTO",
    "White Wedding RBX",
]
carts = {}
lock = threading.RLock()


def api(method, **data):
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/{method}",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        result = json.load(response)
    if not result.get("ok"):
        raise RuntimeError("Telegram API error")
    return result["result"]


def button(text, action):
    return {"text": text, "callback_data": action}


def send(chat, text, rows):
    api(
        "sendMessage",
        chat_id=chat,
        text=text,
        reply_markup={"inline_keyboard": rows},
    )


def catalog(chat):
    rows = [
        [button(f"{name} — 300 ₽", f"add:{i}")]
        for i, name in enumerate(PRODUCTS)
    ]
    rows.append([button("🛒 Корзина", "cart")])
    send(
        chat,
        "🐝 Shmel seeds bank\n\n"
        "Сувенирные семена каннабиса («орехи»).\n"
        "1 орех — 300 ₽.\n"
        "Нажмите на сорт, чтобы добавить один орех.",
        rows,
    )


def show_cart(chat, user):
    items = carts.get(user, {})
    if not items:
        send(chat, "Корзина пуста.", [
            [button("Каталог", "catalog")]
        ])
        return
    lines = [
        f"{PRODUCTS[i]}: {qty} шт. — {qty * 300} ₽"
        for i, qty in items.items()
    ]
    total = sum(items.values()) * 300
    send(
        chat,
        "🛒 Корзина\n\n" + "\n".join(lines)
        + f"\n\nТовары: {total} ₽"
        + "\nСтоимость доставки продавец сообщит "
        "в личной переписке.",
        [
            [button("Оформить заказ", "checkout")],
            [button("Добавить ещё", "catalog")],
            [button("Очистить корзину", "clear")],
        ],
    )


def handle(update):
    query = update.get("callback_query")
    if not query:
        message = update.get("message", {})
        chat = message.get("chat", {})
        if chat.get("type") == "private":
            catalog(chat["id"])
        return

    message = query.get("message", {})
    chat = message.get("chat", {})
    if chat.get("type") != "private":
        return

    api("answerCallbackQuery", callback_query_id=query["id"])
    chat_id = chat["id"]
    user = query["from"]["id"]
    action = query.get("data", "")

    with lock:
        if action == "catalog":
            catalog(chat_id)

        elif action.startswith("add:"):
            index = action.split(":", 1)[1]
            if not index.isdigit():
                return
            index = int(index)
            if index not in range(len(PRODUCTS)):
                return
            items = carts.setdefault(user, {})
            items[index] = min(items.get(index, 0) + 1, 999)
            show_cart(chat_id, user)

        elif action == "cart":
            show_cart(chat_id, user)

        elif action == "clear":
            carts.pop(user, None)
            show_cart(chat_id, user)

        elif action == "checkout":
            items = carts.get(user, {})
            if not items:
                show_cart(chat_id, user)
                return
            number = secrets.token_hex(4).upper()
            text = f"Заказ {number} — Shmel seeds bank\n\n"
            text += "\n".join(
                f"{PRODUCTS[i]}: {qty} шт. — {qty * 300} ₽"
                for i, qty in items.items()
            )
            text += f"\n\nТовары: {sum(items.values()) * 300} ₽"
            text += (
                "\nСтоимость доставки продавец сообщит "
                "в личной переписке."
            )
            url = (
                f"https://t.me/{SELLER}?"
                + urllib.parse.urlencode({"text": text})
            )
            send(
                chat_id,
                text + "\n\nНажмите кнопку и отправьте "
                "сообщение продавцу. Доставку и оплату "
                "согласуйте лично.",
                [
                    [{"text": "Написать продавцу", "url": url}],
                    [button("Каталог", "catalog")],
                ],
            )


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Shmel bot is running")

    def do_POST(self):
        received = self.headers.get(
            "X-Telegram-Bot-Api-Secret-Token", ""
        )
        if not secrets.compare_digest(received, SECRET):
            self.send_error(403)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 1_000_000:
                self.send_error(413)
                return
            update = json.loads(self.rfile.read(size))
            handle(update)
        except Exception:
            print("Update failed", flush=True)
            self.send_error(500)
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")


if __name__ == "__main__":
    host = os.environ["RENDER_EXTERNAL_URL"].rstrip("/")
    api(
        "setWebhook",
        url=host + "/telegram",
        secret_token=SECRET,
        allowed_updates=["message", "callback_query"],
    )
    server = ThreadingHTTPServer(
        ("0.0.0.0", int(os.getenv("PORT", "10000"))),
        Handler,
    )
    server.serve_forever()
