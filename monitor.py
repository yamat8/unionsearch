import os, re, json, sys
import requests
from bs4 import BeautifulSoup

URL = "https://diskunion.net/used/ct/avant/new_ulist/0/53/0/0/01031062090611/0/10/"
STATE_FILE = "state.json"
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/123.0 Safari/537.36")
}


def fetch():
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def parse(html):
    m = re.search(r"新入荷一覧\D*?(\d[\d,]*)\s*件", html)
    count = int(m.group(1).replace(",", "")) if m else None
    soup = BeautifulSoup(html, "html.parser")
    items = {}
    for a in soup.select('a[href*="/udetail/"]'):
        mid = re.search(r"/udetail/([A-Za-z0-9]+)", a.get("href", ""))
        if not mid:
            continue
        gid = mid.group(1)
        text = a.get_text(strip=True)
        if not text or text.startswith("http") or "その他中古" in text:
            continue
        if gid not in items or len(text) > len(items[gid]):
            items[gid] = text
    return count, items


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return None


def save_state(count, items):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"count": count, "ids": list(items.keys())},
                  f, ensure_ascii=False, indent=2)


def notify(body):
    if not NTFY_TOPIC:
        print("NTFY_TOPIC undefined; skip notify:\n", body)
        return
    requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=body.encode("utf-8"),
        headers={"Title": "diskunion AVANT new arrival",
                 "Tags": "cd,bell", "Click": URL},
        timeout=30,
    )


def main():
    html = fetch()
    count, items = parse(html)
    if count is None:
        print("count not found; check page structure.")
        sys.exit(1)
    prev = load_state()
    save_state(count, items)
    if prev is None:
        print(f"first run; recorded {count} items.")
        return
    if count > prev["count"]:
        prev_ids = set(prev.get("ids", []))
        new_items = [t for gid, t in items.items() if gid not in prev_ids]
        delta = count - prev["count"]
        lines = [f"出品数 {prev['count']} → {count}（+{delta}）"]
        if new_items:
            lines.append("")
            lines += [f"・{t}" for t in new_items[:10]]
        notify("\n".join(lines))
        print("notified:\n" + "\n".join(lines))
    else:
        print(f"no increase ({prev['count']} -> {count}); skip.")


if __name__ == "__main__":
    main()
