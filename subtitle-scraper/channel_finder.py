import csv
import re
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]
CSV_PATH = "top-1000-most-subscribed-youtube-channels-in-germany.csv"


def build_youtube_client():
    flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
    creds = flow.run_local_server(port=0)
    return build("youtube", "v3", credentials=creds)


def get_channel_ids_from_csv(youtube, csv_path: str) -> list[str]:
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        names = [row["Youtuber"] for row in reader]

    channel_ids = []
    not_found = []

    for name in names:
        handle = "@" + re.sub(r"[^a-zA-Z0-9_\-.]", "", name.replace(" ", ""))
        response = youtube.channels().list(
            part="snippet",
            forHandle=handle,
        ).execute()
        items = response.get("items", [])
        if items:
            channel_ids.append(items[0]["id"])
        else:
            not_found.append(name)

    if not_found:
        print(f"Could not find {len(not_found)} channels by handle:")
        for name in not_found:
            print(f"  {name}")

    return channel_ids


def get_subscribed_channel_ids(youtube) -> list[str]:
    channel_ids = []
    page_token = None

    while True:
        response = youtube.subscriptions().list(
            part="snippet,contentDetails",
            mine=True,
            maxResults=50,
            pageToken=page_token,
        ).execute()

        for item in response.get("items", []):
            resource = item.get("snippet", {}).get("resourceId", {})
            channel_id = resource.get("channelId")
            if channel_id:
                channel_ids.append(channel_id)

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return channel_ids


if __name__ == "__main__":
    youtube = build_youtube_client()

    subscribed = get_subscribed_channel_ids(youtube)
    print(f"Found {len(subscribed)} subscribed channels")

    csv_ids = get_channel_ids_from_csv(youtube, CSV_PATH)
    print(f"Found {len(csv_ids)} channels from CSV")

    combined = list(dict.fromkeys(subscribed + csv_ids))  # deduplicate, preserve order
    print(f"Total unique channels: {len(combined)}")

    with open("subscribed_channels.txt", "w") as f:
        f.write("\n".join(combined))
    print("Written to subscribed_channels.txt")
