import aiohttp
from collections import defaultdict

async def scrape_collectibles(cookie, user_id):
    next_page_cursor = ""
    items = defaultdict(list)

    async with aiohttp.ClientSession() as session:
        while True:
            url = f"https://inventory.roblox.com/v1/users/{user_id}/assets/collectibles?limit=100&cursor={next_page_cursor}"
            async with session.get(url, cookies={".ROBLOSECURITY": cookie}) as response:
                if response.status != 200:
                    break

                json_response = await response.json()
                for item in json_response["data"]:
                    items[item["assetId"]].append(item)

                if not json_response.get("nextPageCursor"):
                    break

                next_page_cursor = json_response["nextPageCursor"]

    return dict(items)