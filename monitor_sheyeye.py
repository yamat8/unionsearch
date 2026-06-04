import os, re, json, sys
import requests
from bs4 import BeautifulSoup

URL = "https://www.sheyeye.com/?mode=cate&cbid=561707&csid=0&sort=n"
STATE_FILE = "state_sheyeye.json"
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/123.0 Safari/537.36")
}


def fetch():
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.content.decode("euc-jp", errors="replace")


def parse(html):
    soup = BeautifulSoup(html, "html.parser")
    items = {}
    for a in soup.select('a[href*="pid="]'):
        mid = re.search(r"[?&]pid=(\d+)", a.get("href", ""))
        if not mid:
            continue
        pid = mid.group(1)
        text = a.get_text(strip=True)
        if not text:
            continue
        if pid not in items or len(text) > len(items[pid]):
            items[pid] = text
    return items


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return None


def save_state(items):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"ids": list(items.keys())}, f, ensure_ascii=False, indent=2)


def notify(body):
    if not NTFY_TOPIC:
        print("NTFY_TOPIC undefined; skip notify:\n", body)
        return
    requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=body.encode("utf-8"),
        headers={"Title": "sheyeye new arrival", "Tags": "cd,bell", "Click": URL},
        timeout=30,
    )


def main():
    html = fetch()
    items = parse(html)
    if not items:
        print("no items parsed; check page structure.")
        sys.exit(1)
    prev = load_state()
    save_state(items)
    if prev is None:
        print(f"first run; recorded {len(items)} items.")
        return
    prev_ids = set(prev.get("ids", []))
    new_ids = [pid for pid in items if pid not in prev_ids]
    if new_ids:
        lines = [f"sheyeye 新着 {len(new_ids)}件"]
        lines += [f"・{items[pid]}" for pid in new_ids[:10]]
        notify("\n".join(lines))
        print("notified:\n" + "\n".join(lines))
    else:
        print("no new items; skip.")


if __name__ == "__main__":
    main()
