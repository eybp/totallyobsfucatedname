import aiohttp
from collections import deque
import asyncio
import logging
from typing import Dict, Union, Optional

from .models import item
from .data_types import item_types
from .helpers import JSVariableExtractor, pass_session
from . import errors
from . import trades

async def post_ad(roli_verification, player_id, offer_item_ids, request_item_ids, request_tags):
    async with aiohttp.ClientSession() as session:
        async with session.post("https://api.rolimons.com/tradeads/v1/createad", json={"player_id": player_id, "offer_item_ids": offer_item_ids, "request_item_ids": request_item_ids, "request_tags": request_tags}, cookies={"_RoliVerification": roli_verification}) as response:
            return response.status == 201

@pass_session
async def generic_item_info(session: Optional[aiohttp.ClientSession] = None) -> Union[Dict[str, item.ItemDetails], errors.invalid_cookie]:
    """
    Fetches and parses item details from the main Rolimon's catalog page by extracting embedded JavaScript variables.
    """
    assert session
    async with session.get(item.BASE_GENERIC_ITEM_URL) as response:
        if response.status == 200:
            response_text = await response.text()
            extractor = JSVariableExtractor(response_text)
            extracted_variables = extractor.extract()

            if item.BASE_GENERIC_ITEM_VAR_NAME not in extracted_variables:
                raise errors.invalid_cookie(f"Could not find '{item.BASE_GENERIC_ITEM_VAR_NAME}' variable on Rolimon's page.")

            raw_item_details = extracted_variables[item.BASE_GENERIC_ITEM_VAR_NAME].value
            for item_id, data in raw_item_details.items():
                raw_item_details[item_id] = tuple(data)

            data_items: item_types.ItemDetails = raw_item_details
            data = {
                item_id: item.ItemDetails(
                    item_name=raw[0],
                    acronym=raw[15],
                    asset_type_id=raw[1],
                    original_price=raw[2],
                    best_price=raw[5],
                    rap=raw[8],
                    value=raw[16],
                    created=raw[3],
                    first_timestamp=raw[4],
                    owners=raw[9],
                    bc_owners=raw[10],
                    copies=raw[11],
                    deleted_copies=raw[12],
                    bc_copies=raw[13],
                    num_sellers=raw[7],
                    hoarded_copies=raw[14],
                    favorited=raw[6],
                    demand=raw[17],
                    trend=raw[18],
                    projected=raw[19],
                    hyped=raw[20],
                    rare=raw[21],
                    thumbnail_url_lg=raw[23],
                )
                for item_id, raw in data_items.items()
            }
            return data
        else:
            raise errors.invalid_cookie(f"Failed to fetch Rolimon's data. URL: {item.BASE_GENERIC_ITEM_URL}, STATUS: {response.status}")

async def limiteds():
    """
    Fetches the main item details list from Rolimon's by scraping the catalog page
    and transforms it into the format required by the trading algorithm.
    """
    try:
        item_details_objects = await generic_item_info()
        if not item_details_objects:
            logging.warning("⚠️ No item details were fetched from Rolimon's.")
            return {}

        formatted_items = {}
        for item_id, details in item_details_objects.items():
            formatted_items[item_id] = [
                details.item_name,
                details.acronym,
                details.rap,
                details.value if details.value is not None else -1,
                details.original_price,
                details.demand if details.demand is not None else 0,
                details.trend if details.trend is not None else 0,
                1 if details.projected else 0,
                1 if details.hyped else 0,
                1 if details.rare else 0,
                None
            ]
        return formatted_items
    except Exception as e:
        logging.error(f"❌ An exception occurred while fetching and processing Rolimon's item details: {e}")
        return {}

async def track_trade_ads(self):
    seen_ids = deque(maxlen=500)
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                while True:
                    try:
                        async with session.get("https://api.rolimons.com/tradeads/v1/getrecentads") as response:
                            if response.status != 200:
                                await asyncio.sleep(5)
                                continue

                            json_response = await response.json()
                            for trade_ad in json_response.get("trade_ads", []):
                                user_id = trade_ad[2]
                                if user_id not in seen_ids:
                                    seen_ids.append(user_id)
                                    await trades.send_trade(self, user_id)
                                    await asyncio.sleep(self.sleep_time_trade_send)
                    except aiohttp.ClientError:
                        break

        except Exception as outer_error:
            print(f"[tracker] Full session error: {outer_error}")
            await asyncio.sleep(10)
