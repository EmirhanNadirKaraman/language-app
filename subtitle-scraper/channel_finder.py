from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]

def get_subscribed_channel_ids() -> list[str]:
    flow = InstalledAppFlow.from_client_secrets_file(
        "client_secret.json",
        SCOPES,
    )
    creds = flow.run_local_server(port=0)

    youtube = build("youtube", "v3", credentials=creds)

    channel_ids = []
    page_token = None

    while True:
        request = youtube.subscriptions().list(
            part="snippet,contentDetails",
            mine=True,
            maxResults=50,
            pageToken=page_token,
        )
        response = request.execute()

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
    ids = get_subscribed_channel_ids()
    print(f"Found {len(ids)} subscribed channels")
    for channel_id in ids:
        print(channel_id)