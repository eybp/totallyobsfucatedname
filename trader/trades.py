import aiohttp
import asyncio
import random
import time
from datetime import datetime, timezone

from . import algorithm
from . import user

import logging

class IgnoreUnclosedSessionFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        if "Unclosed client session" in msg or "Unclosed connector" in msg:
            return False
        return True

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(message)s",
    datefmt="%d-%b-%Y %H:%M:%S",
    handlers=[logging.StreamHandler()]
)

for handler in logging.getLogger().handlers:
    handler.addFilter(IgnoreUnclosedSessionFilter())

async def check_outbound(self):
    while True:
        next_page_cursor = ""
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    async with session.get(
                        f"https://trades.roblox.com/v1/trades/outbound?cursor={next_page_cursor}&limit=100&sortOrder=Desc",
                        cookies={".ROBLOSECURITY": self.cookie}
                    ) as response:
                        if response.status == 200:
                            if not getattr(self, 'roblox_cookie_working', True):
                                self.roblox_cookie_working = True
                                logging.info("✅ Roblox cookie authentication has recovered.")

                            json_data = await response.json()
                            for trade in json_data.get("data", []):
                                try:
                                    giving_items, receiving_items, item_ids_giver, item_ids_receiver, trade_json = await trade_info(self, trade["id"])

                                    if not giving_items or not receiving_items:
                                        continue

                                    keep, giving_score, receiving_score = await algorithm.evaluate_trade(giving_items, receiving_items, self.algorithm, allow_edge=True)
                                    if not keep or any(int(item_id) in self.item_ids_not_for_trade for item_id in item_ids_giver) or any(int(item_id) in self.item_ids_not_accepting for item_id in item_ids_receiver):
                                        message, status = await decline(self, trade["id"])
                                        if status == 200:
                                            logging.info(f"🚫 Declined losing outbound trade {trade['id']}")
                                        else:
                                            logging.warning(f"🛑 Failed to decline losing outbound trade {trade['id']}")
                                            await self.send_webhook_notification({"content": f"Failed to decline losing outbound trade. Reason: {message['errors'][0]['message']} Please cancel outbound trade as soon as possible. Giving score: `{giving_score}`, Receiving score: `{receiving_score}`. https://www.roblox.com/trades#{trade['id']}"})
                                except Exception as e:
                                    logging.error(f"❌ Error processing outbound trade {trade['id']}: {e}")
                                finally:
                                    await asyncio.sleep(5)

                            next_page_cursor = json_data.get("nextPageCursor")
                            if not next_page_cursor:
                                break
                        else:
                            if response.status in [401, 403] and getattr(self, 'roblox_cookie_working', True):
                                self.roblox_cookie_working = False
                                logging.error("🚨 Roblox cookie is invalid. Pausing outbound trade checker.")
                                error_embed = await generate_error_embed("roblox_cookie")
                                await self.send_webhook_notification(error_embed)
                                await asyncio.sleep(3600)

                            logging.warning(f"⚠️ Failed to fetch outbound trades. Status: {response.status}")
                            break
                except Exception as e:
                    logging.error(f"❌ Error during outbound trades fetching: {e}")
                    if session.closed:
                        break
                finally:
                    await asyncio.sleep(10)

async def check_inbound(self):
    while True:
        next_page_cursor = ""
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    async with session.get(
                        f"https://trades.roblox.com/v1/trades/inbound?cursor={next_page_cursor}&limit=100&sortOrder=Desc",
                        cookies={".ROBLOSECURITY": self.cookie}
                    ) as response:
                        if response.status == 200:
                            if not getattr(self, 'roblox_cookie_working', True):
                                self.roblox_cookie_working = True
                                logging.info("✅ Roblox cookie authentication has recovered.")

                            json_data = await response.json()
                            for trade in json_data.get("data", []):
                                try:
                                    giving_items, receiving_items, item_ids_giver, item_ids_receiver, trade_json = await trade_info(self, trade["id"])

                                    if not giving_items or not receiving_items or any(int(item_id) in self.item_ids_not_for_trade for item_id in item_ids_giver) or any(int(item_id) in self.item_ids_not_accepting for item_id in item_ids_receiver):
                                        continue

                                    keep, giving_score, receiving_score = await algorithm.evaluate_trade(giving_items, receiving_items, self.algorithm, allow_edge=False)
                                    if keep:
                                        if (await self.authenticator_client.accept_trade(TAG=self.cookie[-10:], TRADE_ID=trade["id"])).status == 200:
                                            logging.info(f"✅ Successfully accepted inbound trade {trade['id']}")
                                        else:
                                            logging.warning(f"⚠️ Failed to accept inbound trade {trade['id']}")
                                    else:
                                        logging.info(f"🔄 Searching for counter trade for trade {trade['id']}")

                                        # Check if we can send a trade before generating one
                                        can_send_trade = True
                                        now = time.time()
                                        self.trade_timestamps = [ts for ts in self.trade_timestamps if now - ts < self.TRADE_LIMIT_WINDOW]

                                        if now < self.rate_limit_until:
                                            logging.warning(f"🕒 Rate limited. Cannot send counter-trade. Next attempt possible in {int((self.rate_limit_until - now)/60)} minutes.")
                                            can_send_trade = False
                                        elif len(self.trade_timestamps) >= self.TRADE_LIMIT_COUNT:
                                            logging.warning(f"🕒 Daily trade limit of {self.TRADE_LIMIT_COUNT} reached. Cannot counter.")
                                            self.rate_limit_until = self.trade_timestamps[0] + self.TRADE_LIMIT_WINDOW
                                            can_send_trade = False

                                        trade_data = None
                                        if can_send_trade:
                                            trade_data = await generate_trade(self, trade['user']['id'], True)

                                        if trade_data:
                                            logging.info(f"✉️ Sending counter trade to user {trade['user']['id']}.")
                                            response_counter = await self.authenticator_client.counter_trade(TAG=self.cookie[-10:], TRADE_DATA=trade_data, TRADE_ID = trade["id"])

                                            if response_counter.status == 200:
                                                self.trade_timestamps.append(time.time())
                                                json_data_response = await response_counter.json()
                                                logging.info(f"✅ Successfully countered inbound trade {trade['id']}")
                                                async with aiohttp.ClientSession() as new_session:
                                                    async with new_session.get(f"https://trades.roblox.com/v1/trades/{json_data_response['id']}", cookies={".ROBLOSECURITY": self.cookie}) as trade_info_resp:
                                                        if trade_info_resp.status == 200:
                                                            trade_info_json = await trade_info_resp.json()
                                                            await self.send_webhook_notification(await generate_trade_content(self, trade_info_json))
                                                continue # Skip declining and move to next inbound trade

                                            elif response_counter.status == 429:
                                                logging.error("❌ Failed to send counter-trade: Rate limited by Roblox (429).")
                                                now = time.time()
                                                self.trade_timestamps = [ts for ts in self.trade_timestamps if now - ts < self.TRADE_LIMIT_WINDOW]

                                                if len(self.trade_timestamps) >= self.TRADE_LIMIT_COUNT:
                                                    self.rate_limit_until = self.trade_timestamps[0] + self.TRADE_LIMIT_WINDOW
                                                else: # Cold start case
                                                    logging.warning("🕒 Rate limited on a cold start. Waiting 24 hours as a precaution.")
                                                    self.rate_limit_until = now + self.TRADE_LIMIT_WINDOW

                                                # Send embed notification
                                                rate_limit_embed = await generate_rate_limit_embed(self.rate_limit_until)
                                                await self.send_webhook_notification(rate_limit_embed)

                                            else:
                                                logging.warning(f"⚠️ Failed to counter inbound trade {trade['id']}")
                                                await self.send_webhook_notification({"content": f"Failed to counter trade. Response status: {response_counter.status}. https://www.roblox.com/trades#{str(trade['id'])}. Response json: {await response_counter.json()}"})

                                        # Decline if no counter was found or if sending the counter failed
                                        logging.info(f"🚫 No counter trade found for {trade['id']} or could not send. Declining.")
                                        message, status = await decline(self, trade["id"])
                                        if status == 200:
                                            logging.info(f"✅ Successfully declined trade {trade['id']}.")
                                        else:
                                            logging.warning(f"⚠️ Failed to decline trade {trade['id']}: {message}")
                                finally:
                                    await asyncio.sleep(self.sleep_time_trade_send)

                            next_page_cursor = json_data.get("nextPageCursor")
                            if not next_page_cursor:
                                break
                        else:
                            if response.status in [401, 403] and getattr(self, 'roblox_cookie_working', True):
                                self.roblox_cookie_working = False
                                logging.error("🚨 Roblox cookie is invalid. Pausing inbound trade checker.")
                                error_embed = await generate_error_embed("roblox_cookie")
                                await self.send_webhook_notification(error_embed)
                                await asyncio.sleep(3600)

                            logging.warning(f"⚠️ Failed to fetch inbound trades. Status: {response.status}")
                            break
                except Exception as e:
                    logging.error(f"❌ Error during inbound trades fetching: {e}")
                    if session.closed:
                        break
                finally:
                    await asyncio.sleep(10)

async def trade_info(self, trade_id):
    giving_items, receiving_items, item_ids_giver, item_ids_receiver = [], [], [], []

    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://trades.roblox.com/v1/trades/{trade_id}", cookies={".ROBLOSECURITY": self.cookie}) as response:
            if response.status == 200:
                json_response = await response.json()
                if json_response["offers"][0]["robux"] > 0 or json_response["offers"][1]["robux"] > 0:
                    return [], [], [], [], {}
                giver_index = 0 if json_response["offers"][0]["user"]["id"] == self.user_id else 1
                receiver_index = 0 if giver_index == 1 else 1

                for item in json_response["offers"][giver_index]["userAssets"]:
                    if str(item["assetId"]) in self.all_limiteds:
                        item_ids_giver.append(str(item["assetId"]))
                        giving_items.append(self.all_limiteds[str(item["assetId"])])
                    else:
                        return [], [], item_ids_giver, item_ids_receiver, json_response

                for item in json_response["offers"][receiver_index]["userAssets"]:
                        if str(item["assetId"]) in self.all_limiteds:
                            item_ids_receiver.append(str(item["assetId"]))
                            receiving_items.append(self.all_limiteds[str(item["assetId"])])
                        else:
                            return [], [], item_ids_giver, item_ids_receiver, json_response

                return giving_items, receiving_items, item_ids_giver, item_ids_receiver, json_response
            else:
                logging.warning(f"⚠️ Failed to scrape trade info for trade ID {trade_id}. Response status: {response.status}")
                return [], [], [], [], {}

async def decline(self, trade_id):
    async with aiohttp.ClientSession() as session:
        async with session.post(f"https://trades.roblox.com/v1/trades/{trade_id}/decline", cookies={".ROBLOSECURITY": self.cookie}, headers={"x-csrf-token": await self.get_xcsrf_token()}) as response:
            json_response = await response.json()
            return json_response, response.status

async def trades_watcher(self):
    completed_trades, status_completed = await scrape_trades_completed_inactive(self, "completed")
    if status_completed == 200 and completed_trades.get("data"):
        for trade_id in completed_trades["data"]:
            self.all_processed_trades.append(trade_id['id'])

    inactive_trades, status_inactive = await scrape_trades_completed_inactive(self, "inactive")
    if status_inactive == 200 and inactive_trades.get("data"):
        for trade_id in inactive_trades["data"]:
            self.all_processed_trades.append(trade_id['id'])

    while True:
        try:
            for scrape_type in ["completed", "inactive"]:
                scraped_trades, status = await scrape_trades_completed_inactive(self, scrape_type)
                if status != 200:
                    continue

                for trade_id in scraped_trades.get("data", []):
                    if trade_id['id'] not in self.all_processed_trades:
                        self.all_processed_trades.append(trade_id['id'])
                        async with aiohttp.ClientSession() as session:
                            async with session.get(f"https://trades.roblox.com/v1/trades/{trade_id['id']}", cookies={".ROBLOSECURITY": self.cookie}) as resp:
                                if resp.status == 200:
                                    json_data = await resp.json()
                                    await self.send_webhook_notification(await generate_trade_content(self, json_data))

                if scrape_type == "completed":
                    try:
                        await self.update_limiteds()
                        if not getattr(self, 'rolimons_working', True):
                            self.rolimons_working = True
                            logging.info("✅ Rolimons data fetching has recovered.")
                    except Exception as e:
                        if getattr(self, 'rolimons_working', True):
                            self.rolimons_working = False
                            logging.error(f"❌ Failed to update limiteds, likely a Rolimons issue: {e}")
                            error_embed = await generate_error_embed("rolimons_failure")
                            await self.send_webhook_notification(error_embed)

        except Exception as e:
            logging.error(f"An error occurred in trades_watcher loop: {e}")
        finally:
            await asyncio.sleep(20)

async def scrape_trades_completed_inactive(self, scrape_type):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"https://trades.roblox.com/v1/trades/{scrape_type}?cursor=&limit=10&sortOrder=Desc", cookies={".ROBLOSECURITY": self.cookie}) as response:
                if response.status in [401, 403] and getattr(self, 'roblox_cookie_working', True):
                    self.roblox_cookie_working = False
                    logging.error(f"🚨 Roblox cookie is invalid. Pausing {scrape_type} trade scraper.")
                    error_embed = await generate_error_embed("roblox_cookie")
                    await self.send_webhook_notification(error_embed)
                    await asyncio.sleep(86400)

                elif response.status == 200 and not getattr(self, 'roblox_cookie_working', True):
                    self.roblox_cookie_working = True
                    logging.info("✅ Roblox cookie authentication has recovered.")

                return await response.json(), response.status
        except Exception as e:
            logging.error(f"Exception while scraping {scrape_type} trades: {e}")
            return {}, 0

async def generate_trade(self, user_id, counter=False):
    all_my_items_raw = [item for sublist in self.limiteds.values() for item in sublist]

    if len(all_my_items_raw) == 1 and all_my_items_raw[0].get("isOnHold", False):
        if not getattr(self, 'is_paused_on_hold', False):
            self.is_paused_on_hold = True
            item_on_hold = all_my_items_raw[0]
            logging.info("⏸️ Inventory contains only one item on hold. Pausing trade search and sending notification.")
            pause_embed = await generate_holding_period_embed("paused", item_on_hold.get("name"))
            await self.send_webhook_notification(pause_embed)

        while len(all_my_items_raw) == 1 and all_my_items_raw[0].get("isOnHold", False):
            logging.info("🔄 Item on hold. Waiting before re-checking...")
            await asyncio.sleep(10800)
            await self.update_limiteds()
            all_my_items_raw = [item for sublist in self.limiteds.values() for item in sublist]

        if getattr(self, 'is_paused_on_hold', False):
            self.is_paused_on_hold = False
            logging.info("✅ Item no longer on hold or new items acquired. Resuming trade search.")
            resume_embed = await generate_holding_period_embed("resumed")
            await self.send_webhook_notification(resume_embed)

    receiver_items = await user.scrape_collectibles(self.cookie, user_id)
    giver_items = self.limiteds.copy()
    if not receiver_items or not giver_items:
        logging.warning(f"⚠️ No items available for trade with user {user_id}.")
        return {}

    receiver_items = [item for sublist in receiver_items.values() for item in sublist if not item["isOnHold"]]
    giver_items = [item for sublist in giver_items.values() for item in sublist if not item["isOnHold"]]

    giver_limiteds_rolimon = [
        self.all_limiteds[str(item["assetId"])]
        for item in giver_items
        if str(item["assetId"]) in self.all_limiteds
        and self.all_limiteds[str(item["assetId"])][7]
        and not (self.algorithm["modes"]["value_only"] and self.all_limiteds[str(item["assetId"])][3] == 1)
        and int(item["assetId"]) not in self.item_ids_not_for_trade
    ]

    receiver_limiteds_rolimon = [
        self.all_limiteds[str(item["assetId"])]
        for item in receiver_items
        if str(item["assetId"]) in self.all_limiteds
        and self.all_limiteds[str(item["assetId"])][7] != 1
        and not (self.algorithm["modes"]["value_only"] and self.all_limiteds[str(item["assetId"])][3] == 1)
        and int(item["assetId"]) not in self.item_ids_not_accepting
    ]
    mode = random.choice(self.algorithm["modes"]["trade_methods"])
    if mode == "upgrade":
        receiver_min = self.algorithm["downgrade"]["min_items"]
        receiver_max = self.algorithm["downgrade"]["max_items"]
        giver_min = self.algorithm["upgrade"]["min_items"]
        giver_max = self.algorithm["upgrade"]["max_items"]
    else:
        receiver_min = self.algorithm["upgrade"]["min_items"]
        receiver_max = self.algorithm["upgrade"]["max_items"]
        giver_min = self.algorithm["downgrade"]["min_items"]
        giver_max = self.algorithm["downgrade"]["max_items"]

    best_trade = await algorithm.find_best_trade(
        giver_items=giver_limiteds_rolimon,
        receiver_items=receiver_limiteds_rolimon,
        settings=self.algorithm,
        giver_max=giver_max,
        giver_min=giver_min,
        receiver_min=receiver_min,
        receiver_max=receiver_max,
        allow_edge=True,
        batch_size=self.algorithm["performance"]["batch_size"],
        max_pairs=self.algorithm["performance"]["max_pairs"],
        mode=mode,
        min_trade_send_value_total=self.algorithm["thresholds"]["min_trade_send_value_total"] if not counter else 0
    )

    if best_trade:
        logging.info(f"✅ Best trade found for user {user_id}. Preparing trade data.")
        giving_item_uaids = []
        receiving_item_uaids = []

        for _item in giver_items.copy():
            for item in best_trade["giving_items"].copy():
                if item[0] == _item["name"]:
                    giving_item_uaids.append(_item["userAssetId"])
                    best_trade["giving_items"].remove(item)
                    break
        for _item in receiver_items:
            for item in best_trade["receiving_items"].copy():
                if item[0] == _item["name"]:
                    receiving_item_uaids.append(_item["userAssetId"])
                    best_trade["receiving_items"].remove(item)
                    break

        if not receiving_item_uaids or not giving_item_uaids:
            return {}

        data_json = {
            "offers": [
                {
                    "userId": self.user_id,
                    "userAssetIds": giving_item_uaids,
                    "robux": 0
                },
                {
                    "userId": user_id,
                    "userAssetIds": receiving_item_uaids,
                    "robux": 0
                }
            ]
        }
        return data_json
    else:
        return {}

async def send_trade(self, user_id):
    # Check rate limit status before proceeding
    now = time.time()
    self.trade_timestamps = [ts for ts in self.trade_timestamps if now - ts < self.TRADE_LIMIT_WINDOW]

    if now < self.rate_limit_until:
        logging.warning(f"🕒 Rate limited. Cannot send trade. Next attempt possible in {int((self.rate_limit_until - now)/60)} minutes.")
        return

    if len(self.trade_timestamps) >= self.TRADE_LIMIT_COUNT:
        self.rate_limit_until = self.trade_timestamps[0] + self.TRADE_LIMIT_WINDOW
        logging.warning(f"🕒 Daily trade limit of {self.TRADE_LIMIT_COUNT} reached. Cannot send trade.")
        return

    logging.info(f"🔄 Generating possible trades with user {user_id}")
    trade_data = await generate_trade(self, user_id, False)
    if trade_data:
        logging.info(f"✉️ Sending trade to user {user_id}.")
        response = await self.authenticator_client.send_trade(TAG=self.cookie[-10:], TRADE_DATA=trade_data)

        if response.status == 200:
            self.trade_timestamps.append(time.time()) # Record successful trade
            trade_id = str((await response.json())['id'])
            logging.info(f"✅ Trade sent successfully. Trade ID: {trade_id}")
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://trades.roblox.com/v1/trades/{trade_id}", cookies={".ROBLOSECURITY": self.cookie}) as resp:
                    if resp.status == 200:
                        json_data = await resp.json()
                        await self.send_webhook_notification(await generate_trade_content(self, json_data))

        elif response.status == 429: # Rate limited
            logging.error("❌ Failed to send trade: Rate limited by Roblox (429).")
            now = time.time()
            self.trade_timestamps = [ts for ts in self.trade_timestamps if now - ts < self.TRADE_LIMIT_WINDOW]

            if len(self.trade_timestamps) >= self.TRADE_LIMIT_COUNT:
                # We have enough local data to calculate the exact wait time
                self.rate_limit_until = self.trade_timestamps[0] + self.TRADE_LIMIT_WINDOW
            else:
                # Cold start scenario: We hit a limit but don't have 100 trades logged.
                logging.warning("🕒 Rate limited on a cold start or with incomplete data. Waiting 24 hours as a precaution.")
                self.rate_limit_until = now + self.TRADE_LIMIT_WINDOW

            # Send embed notification
            rate_limit_embed = await generate_rate_limit_embed(self.rate_limit_until)
            await self.send_webhook_notification(rate_limit_embed)

        else:
            logging.error(f"❌ Failed to send trade to user {user_id}. Response status: {response.status}. Response json {str(await response.json())}")
            await self.send_webhook_notification({"content": f"Failed to send trade to user: {str(user_id)}. Response status: {response.status} . Response json {str(await response.json())}"})

async def generate_rate_limit_embed(rate_limit_until_timestamp):
    """Generates a Discord embed for a 429 rate limit error."""
    embed = {
        "embeds": [{
            "title": "🚨 Trade Rate Limit Reached",
            "color": 0xFFCC00,
            "description": "The bot has been temporarily paused from sending trades after hitting the Roblox rate limit (Error 429).",
            "fields": [
                {
                    "name": "Resuming On",
                    "value": f"<t:{int(rate_limit_until_timestamp)}:F>",
                    "inline": True
                },
                {
                    "name": "Time Remaining",
                    "value": f"<t:{int(rate_limit_until_timestamp)}:R>",
                    "inline": True
                }
            ],
            "footer": {"text": "No action is needed. The bot will resume automatically."},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }]
    }
    return embed

async def generate_error_embed(error_type):
    """Generates a Discord embed for critical errors like expired cookies."""
    if error_type == "roblox_cookie":
        title = "🚨 CRITICAL ERROR: Roblox Cookie Invalid"
        description = "The bot failed to authenticate with the Roblox API. The `.ROBLOSECURITY` cookie has likely expired or is invalid."
        footer_text = "The bot will pause operations to avoid errors. Please update the cookie."
    elif error_type == "rolimons_failure":
        title = "⚠️ WARNING: Rolimons Data Failure"
        description = "The bot failed to fetch the latest item data from Rolimons. This could be due to an expired cookie, an API change, or a temporary outage."
        footer_text = "The bot will use outdated data. Please check your Rolimons cookie/config."
    else:
        return {}

    embed = {
        "embeds": [{
            "title": title,
            "color": 0xFF0000,
            "description": description,
            "fields": [
                {"name": "Action Required", "value": "Manual intervention is needed to fix this issue.", "inline": False},
                {"name": "Timestamp", "value": f"<t:{int(datetime.now(timezone.utc).timestamp())}:F>", "inline": False}
            ],
            "footer": {"text": footer_text}
        }]
    }
    return embed

async def generate_holding_period_embed(status, item_name=None):
    """Generates a Discord embed for holding period status updates."""
    if status == "paused":
        embed = {
            "embeds": [{
                "title": "⏸️ Trade Search Paused",
                "color": 0xFFCC00,
                "description": "The bot has paused searching for new trades because the only item in the inventory is currently on hold.",
                "fields": [
                    {"name": "Item on Hold", "value": f"`{item_name}`" if item_name else "N/A", "inline": False},
                    {"name": "Action", "value": "Will automatically resume when the hold period ends or new items are acquired.", "inline": False},
                ],
                "footer": {"text": "No action is needed. The bot will resume automatically."},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }]
        }
    elif status == "resumed":
        embed = {
            "embeds": [{
                "title": "✅ Trade Search Resumed",
                "color": 0x00FF7F,
                "description": "The bot is now actively searching for trades again.",
                "fields": [
                    {"name": "Reason", "value": "The item hold period has ended or new items were added to the inventory.", "inline": False}
                ],
                "footer": {"text": "Trade operations are back to normal."},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }]
        }
    else:
        return {}

    return embed

async def generate_trade_content(self, data):
    offers = data["offers"]
    user_id = data["user"]["id"]

    receiving = next(o for o in offers if o["user"]["id"] == user_id)
    giving = next(o for o in offers if o["user"]["id"] != user_id)

    given_items = giving["userAssets"]
    received_items = receiving["userAssets"]

    given_rap = sum(self.all_limiteds[str(item["assetId"])][3] if self.all_limiteds[str(item["assetId"])][3] != -1 else self.all_limiteds[str(item["assetId"])][2] for item in given_items)
    received_rap = sum(self.all_limiteds[str(item["assetId"])][3] if self.all_limiteds[str(item["assetId"])][3] != -1 else self.all_limiteds[str(item["assetId"])][2] for item in received_items)
    profit = received_rap - given_rap

    if len(received_items) < len(given_items):
        trade_type = "Upgrade ☝️"
        color = 0x00FF00
    elif len(received_items) > len(given_items):
        trade_type = "Downgrade 👎"
        color = 0xFF0000
    else:
        trade_type = "Sidegrade ➖"
        color = 0xFFFF00

    given_names = "\n".join(
        f"{item['name']} ({self.all_limiteds[str(item['assetId'])][3]:,})" if self.all_limiteds[str(item["assetId"])][3] != -1
        else f"{item['name']} ({self.all_limiteds[str(item['assetId'])][2]:,})"
        for item in given_items
    )
    received_names = "\n".join(
        f"{item['name']} ({self.all_limiteds[str(item['assetId'])][3]:,})" if self.all_limiteds[str(item["assetId"])][3] != -1
        else f"{item['name']} ({self.all_limiteds[str(item['assetId'])][2]:,})"
        for item in received_items
    )

    try:
        dt = datetime.strptime(data["created"], "%Y-%m-%dT%H:%M:%S.%f%z")
    except ValueError:
        dt = datetime.strptime(data["created"], "%Y-%m-%dT%H:%M:%S%z")

    timestamp = f"<t:{int(dt.timestamp())}:F>"

    embed = {
        "embeds": [
            {
                "title": f"{data['status']} Trade ({trade_type})",
                "color": color,
                "url": f"https://www.roblox.com/trades#{data['id']}",
                "fields": [
                    { "name": "Giving", "value": given_names or "None", "inline": True },
                    { "name": "Receiving", "value": received_names or "None", "inline": True },
                    { "name": "Profit (RAP)", "value": f"**Given:** {given_rap:,}\n**Received:** {received_rap:,}\n**Profit:** {profit:,}", "inline": False },
                    { "name": "Created", "value": timestamp, "inline": False }
                ]
            }
        ]
    }

    return embed
