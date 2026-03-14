"""
Merges channels from channels.json and subscribed_channels.txt into merged_channels.json.
Channels from subscribed_channels.txt are assumed to be German.
"""

import json


def load_channels():
    seen_ids = set()
    channels = []

    with open("channels.json") as f:
        channel_dict = json.load(f)
    for language, channel_list in channel_dict.items():
        for ch in channel_list:
            if ch["id"] not in seen_ids:
                channels.append({"id": ch["id"], "name": ch["name"], "language": language})
                seen_ids.add(ch["id"])

    with open("subscribed_channels.txt") as f:
        for line in f:
            channel_id = line.strip()
            if channel_id and channel_id not in seen_ids:
                channels.append({"id": channel_id, "name": None, "language": "de"})
                seen_ids.add(channel_id)

    return channels


if __name__ == "__main__":
    channels = load_channels()

    with open("merged_channels.json", "w") as f:
        json.dump(channels, f, indent=2)

    print(f"Merged {len(channels)} channels into merged_channels.json")
