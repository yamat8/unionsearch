import os, re, json, sys
import requests
from bs4 import BeautifulSoup

BASE = "https://diskunion.net"
# key: (表示名, 一覧URL)
CATEGORIES = {
    "reggae": ("REGGAE", f"{BASE}/used/reggae/new_release"),
    "noise_avant": ("NOISE/AVANT", f"{BASE}/used/noise_avant/new_release"),
}
# 3 = 中古新着順, 60件表示
PARAMS = {"base_search[orderby]": "3", "base_search[disp_number]": "60"}
SEEN_LIMIT = 1000
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/123.0 Safari/537.36")
}


def fetch(url):
    r = requests.get(url, params=PARAMS, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def text(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""


def parse(html):
    """ページ上の順番どおりに中古在庫のリストを返す。"""
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for li in soup.select("li.used-wide-product-item"):
        link = li.select_one(".product-name a[href]")
        if not link:
            continue
        href = link["href"]
        # 中古在庫ごとの固有ID（カート投入URL末尾）。無ければ商品コードで代用
        cart = li.select_one('[data-url*="/ajax/cart/up/"]')
        m = cart and re.search(r"/ajax/cart/up/(\d+)", cart["data-url"])
        sid = m.group(1) if m else "p" + href.rstrip("/").split("/")[-1]
        price = li.select_one(".price")
        price = re.search(r"¥\s*([\d,]+)", text(price)) if price else None
        items.append({
            "id": sid,
            "title": text(link),
            "artist": text(li.select_one(".product-artist")),
            "format": text(li.select_one(".product-type .txt")),
            "rank": text(li.select_one(".product-conditoin-rank span")),
            "price": price.group(1) if price else "",
            "url": BASE + href if href.startswith("/") else href,
        })
    m = re.search(r"検索結果\(\s*<span>\s*([\d,]+)", html)
    count = int(m.group(1).replace(",", "")) if m else None
    return count, items


def state_file(key):
    return f"state_{key}.json"


def load_state(key):
    if os.path.exists(state_file(key)):
        with open(state_file(key), encoding="utf-8") as f:
            return json.load(f)
    return None


def save_state(key, count, seen):
    with open(state_file(key), "w", encoding="utf-8") as f:
        json.dump({"count": count, "seen": seen[:SEEN_LIMIT]},
                  f, ensure_ascii=False, indent=2)


def fmt(it):
    who = f"{it['artist']} / " if it["artist"] else ""
    extra = " ".join(x for x in [
        it["format"], it["rank"] and f"盤質{it['rank']}",
        it["price"] and f"¥{it['price']}"] if x)
    return f"・{who}{it['title']}  [{extra}]"


def notify(label, list_url, new_items):
    lines = [fmt(it) for it in new_items[:10]]
    if len(new_items) > 10:
        lines.append(f"…他 {len(new_items) - 10} 件")
    body = "\n".join(lines)
    click = new_items[0]["url"] if len(new_items) == 1 else list_url
    if not NTFY_TOPIC:
        print("NTFY_TOPIC undefined; skip notify:\n" + body)
        return
    requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=body.encode("utf-8"),
        headers={"Title": f"diskunion {label} new arrival ({len(new_items)})",
                 "Tags": "cd,bell", "Click": click},
        timeout=30,
    ).raise_for_status()


def check(key, label, list_url):
    count, items = parse(fetch(list_url))
    if not items:
        raise RuntimeError(f"{key}: no items parsed; check page structure.")
    prev = load_state(key)
    ids = [it["id"] for it in items]
    if prev is None:
        save_state(key, count, ids)
        print(f"[{key}] first run; recorded {len(ids)} items (total {count}).")
        return
    seen = prev.get("seen", [])
    seen_set = set(seen)
    # 一覧末尾に押し出されて入ってきた既知でない古い在庫は無視するため、
    # 既知の在庫のうち最も下にあるものより上にある未知の在庫だけを新着とみなす
    last_known = max((i for i, s in enumerate(ids) if s in seen_set), default=len(ids))
    new_items = [it for it in items[:last_known] if it["id"] not in seen_set]
    save_state(key, count, ids + [s for s in seen if s not in set(ids)])
    if new_items:
        notify(label, list_url, new_items)
        print(f"[{key}] notified {len(new_items)}:\n" + "\n".join(map(fmt, new_items)))
    else:
        print(f"[{key}] no new items (total {prev.get('count')} -> {count}).")


def main():
    failed = False
    for key, (label, url) in CATEGORIES.items():
        try:
            check(key, label, url)
        except Exception as e:
            print(f"[{key}] ERROR: {e}")
            failed = True
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
