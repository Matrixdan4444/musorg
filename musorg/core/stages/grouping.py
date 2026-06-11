from musorg.utils.debug import log


def build_album_groups(tracks):
    albums = {}

    for track in tracks:
        album_artist = track.get("albumartist")

        # STRICT: use ONLY albumartist
        if album_artist:
            album_artist = album_artist.strip().lower()
        else:
            album_artist = "unknown"

        album = track.get("album", "Unknown").strip().lower()

        key = (album_artist, album)

        if key not in albums:
            albums[key] = []

        albums[key].append(track)

    return albums


def group_by_album(context):
    albums = build_album_groups(context.tracks)

    context.albums = albums

    log("Group", f"Organized album structure for {len(albums)} albums", "📚")

    return context
