import musicbrainzngs
import json

musicbrainzngs.set_useragent("musorg-research", "0.1", "test@example.com")


def search_release_group(artist, album):
    result = musicbrainzngs.search_release_groups(
        artist=artist, releasegroup=album, limit=5
    )

    groups = result.get("release-group-list", [])

    print(f"\n=== RELEASE GROUPS ({len(groups)}) ===\n")

    for i, g in enumerate(groups, 1):
        print(f"\n--- RESULT {i} ---")
        print("title:", g.get("title"))
        print("id:", g.get("id"))
        print("primary type:", g.get("primary-type"))
        print("first release date:", g.get("first-release-date"))

        print("\nartist-credit:")
        print(json.dumps(g.get("artist-credit"), indent=2, ensure_ascii=False))


def get_release_group_details(rg_id):
    result = musicbrainzngs.get_release_group_by_id(rg_id, includes=["artists"])

    rg = result.get("release-group", {})

    print("\n=== RELEASE GROUP DETAILS ===\n")
    print(json.dumps(rg, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    artist = "Баста"
    album = "Баста Гуф"

    search_release_group(artist, album)

    rg_id = input("\nВведи release_group_id: ")

    if rg_id:
        get_release_group_details(rg_id)
