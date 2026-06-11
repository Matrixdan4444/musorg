import requests
import json


def debug_search(artist, album):
    url = "https://api.deezer.com/search"
    query = f'artist:"{artist}" album:"{album}"'

    response = requests.get(url, params={"q": query})
    data = response.json()

    results = data.get("data", [])

    print(f"\n=== SEARCH RESULTS ({len(results)}) ===\n")

    for i, r in enumerate(results[:5], 1):
        print(f"\n--- RESULT {i} ---")

        print("\nFULL JSON:")
        print(json.dumps(r, indent=2, ensure_ascii=False))

        print("\nEXTRACTED:")
        print("track artist:", r.get("artist", {}).get("name"))
        print("album title:", r.get("album", {}).get("title"))
        print("album id:", r.get("album", {}).get("id"))
        print("album cover:", r.get("album", {}).get("cover_xl"))
        print("genre id:", r.get("genre_id"))

        print("\n-------------------------")


def debug_album(album_id):
    url = f"https://api.deezer.com/album/{album_id}"
    response = requests.get(url)
    data = response.json()

    print("\n=== ALBUM DATA ===\n")
    print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    artist = "Баста"
    album = "Баста Гуф"

    debug_search(artist, album)

    album_id = input("\nВведи album_id для подробного анализа: ")

    if album_id:
        debug_album(album_id)
