import aiohttp
import asyncio
import random
import time
from datetime import datetime, timezone
from collections import defaultdict

from . import algorithm
from . import user
from . import rolimon

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
                                    partner_info = trade['user']
                                    partner_id = partner_info['id']
                                    
                                    logging.info(f"🔍 [Outbound] Checking ad count for partner {partner_id}...")
                                    ad_count = await rolimon.get_player_ad_count(partner_id)

                                    if ad_count > self.max_trade_ads:
                                        logging.info(f"🚫 [Outbound] Auto-declining trade {trade['id']}. User {partner_id} has {ad_count} ads (Limit: {self.max_trade_ads}).")
                                        await decline(self, trade["id"])
                                        continue
                                    
                                    logging.info(f"✅ [Outbound] User {partner_id} passed ad check ({ad_count} ads). Evaluating trade...")

                                    giving_items, receiving_items, item_ids_giver, item_ids_receiver, trade_json = await trade_info(self, trade["id"])

                                    if not trade_json:
                                        continue

                                    if not giving_items or not receiving_items:
                                        continue

                                    keep, giving_score, receiving_score = await algorithm.evaluate_trade(giving_items, receiving_items, self.algorithm, allow_edge=True)
                                    if not keep or any(int(item_id) in self.item_ids_not_for_trade for item_id in item_ids_giver) or any(int(item_id) in self.item_ids_not_accepting for item_id in item_ids_receiver):
                                        message, status = await decline(self, trade["id"])
                                        if status == 200:
                                            logging.info(f"🚫 Declined losing outbound trade {trade['id']}")
                                            giver_raw_items = next(offer for offer in trade_json["offers"] if offer["user"]["id"] == self.user_id)['userAssets']
                                            receiver_raw_items = next(offer for offer in trade_json["offers"] if offer["user"]["id"] == partner_info['id'])['userAssets']
                                            reason = f"Cancelled as it's no longer favorable. Profit Score: `{receiving_score - giving_score:.2f}`."
                                            webhook_payload = await generate_decision_webhook(self, "Cancelled Outbound", trade['id'], partner_info, giver_raw_items, receiver_raw_items, giving_score, receiving_score, reason)
                                            await self.send_webhook_notification(webhook_payload)
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
                                    # check ad count
                                    partner_info = trade['user']
                                    partner_id = partner_info['id']

                                    logging.info(f"🔍 [Inbound] Checking ad count for partner {partner_id}...")
                                    ad_count = await rolimon.get_player_ad_count(partner_id)

                                    if ad_count > self.max_trade_ads:
                                        logging.info(f"🚫 [Inbound] Auto-declining trade {trade['id']}. User {partner_id} has {ad_count} ads (Limit: {self.max_trade_ads}).")
                                        await decline(self, trade["id"])
                                        continue

                                    logging.info(f"✅ [Inbound] User {partner_id} passed ad check ({ad_count} ads). Evaluating trade...")

                                    giving_items, receiving_items, item_ids_giver, item_ids_receiver, trade_json = await trade_info(self, trade["id"])

                                    if not trade_json:
                                        continue

                                    giver_raw_items = next(offer for offer in trade_json["offers"] if offer["user"]["id"] == self.user_id)['userAssets']
                                    receiver_raw_items = next(offer for offer in trade_json["offers"] if offer["user"]["id"] == partner_info['id'])['userAssets']

                                    if not giving_items or not receiving_items or any(int(item_id) in self.item_ids_not_for_trade for item_id in item_ids_giver) or any(int(item_id) in self.item_ids_not_accepting for item_id in item_ids_receiver):
                                        continue

                                    keep, giving_score, receiving_score = await algorithm.evaluate_trade(giving_items, receiving_items, self.algorithm, allow_edge=False)
                                    if keep:
                                        if (await self.authenticator_client.accept_trade(TAG=self.cookie[-10:], TRADE_ID=trade["id"])).status == 200:
                                            logging.info(f"✅ Successfully accepted inbound trade {trade['id']}")
                                            reason = f"Accepted due to favorable score. Profit Score: `{receiving_score - giving_score:.2f}`."
                                            webhook_payload = await generate_decision_webhook(self, "Accepted", trade['id'], partner_info, giver_raw_items, receiver_raw_items, giving_score, receiving_score, reason)
                                            await self.send_webhook_notification(webhook_payload)
                                        else:
                                            logging.warning(f"⚠️ Failed to accept inbound trade {trade['id']}")
                                    else:
                                        logging.info(f"🔄 Searching for counter trade for trade {trade['id']}")
                                        
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

                                        trade_info_dict = None
                                        if can_send_trade:
                                            trade_info_dict = await generate_trade(self, trade['user']['id'], True)

                                        if trade_info_dict:
                                            logging.info(f"✉️ Sending counter trade to user {trade['user']['id']}.")
                                            response_counter = await self.authenticator_client.counter_trade(TAG=self.cookie[-10:], TRADE_DATA=trade_info_dict['trade_data'], TRADE_ID = trade["id"])

                                            if response_counter.status == 200:
                                                self.trade_timestamps.append(time.time())
                                                json_data_response = await response_counter.json()
                                                counter_trade_id = json_data_response['id']
                                                logging.info(f"✅ Successfully countered inbound trade {trade['id']} with new trade {counter_trade_id}")

                                                decline_reason = f"Original trade was unfavorable (Profit Score: `{receiving_score - giving_score:.2f}`). Sent counter-offer instead."
                                                decline_webhook = await generate_decision_webhook(self, "Declined", trade['id'], partner_info, giver_raw_items, receiver_raw_items, giving_score, receiving_score, decline_reason)
                                                await self.send_webhook_notification(decline_webhook)

                                                counter_reason = f"Sent as a counter-offer. Profit Score: `{trade_info_dict['receiving_score'] - trade_info_dict['giving_score']:.2f}`."
                                                counter_webhook = await generate_decision_webhook(self, "Countered", counter_trade_id, partner_info, trade_info_dict['giving_items_raw'], trade_info_dict['receiving_items_raw'], trade_info_dict['giving_score'], trade_info_dict['receiving_score'], counter_reason)
                                                await self.send_webhook_notification(counter_webhook)
                                                
                                                continue
                                        
                                        reason_for_decline = f"Declined due to unfavorable score. Profit Score: `{receiving_score - giving_score:.2f}`."
                                        message, status = await decline(self, trade["id"])
                                        if status == 200:
                                            logging.info(f"✅ Successfully declined trade {trade['id']}.")
                                            webhook_payload = await generate_decision_webhook(self, "Declined", trade['id'], partner_info, giver_raw_items, receiver_raw_items, giving_score, receiving_score, reason_for_decline)
                                            await self.send_webhook_notification(webhook_payload)
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
                            
                            item_data = self.all_limiteds[str(item["assetId"])]
                            
                            item_name = item_data[0]
                            item_value = item_data[3] if item_data[3] != -1 else item_data[2]

                            if "egg" in item_name.lower() and item_value < 680:
                                logging.info(f"🥚 Applying egg rule to '{item_name}' (value: {item_value}). Treating as 0 Robux.")
                                modified_item_data = list(item_data)
                                modified_item_data[2] = 0
                                modified_item_data[3] = 0
                                receiving_items.append(modified_item_data)
                            else:
                                receiving_items.append(item_data)

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

    receiver_items_dict = await user.scrape_collectibles(self.cookie, user_id)
    giver_items_dict = self.limiteds.copy()
    if not receiver_items_dict or not giver_items_dict:
        logging.warning(f"⚠️ No items available for trade with user {user_id}.")
        return None

    receiver_items = [item for sublist in receiver_items_dict.values() for item in sublist if not item["isOnHold"]]
    giver_items = [item for sublist in giver_items_dict.values() for item in sublist if not item["isOnHold"]]

    giver_limiteds_rolimon = [
        self.all_limiteds[str(item["assetId"])]
        for item in giver_items
        if str(item["assetId"]) in self.all_limiteds
        and self.all_limiteds[str(item["assetId"])][7]
        and not (self.algorithm["modes"]["value_only"] and self.all_limiteds[str(item["assetId"])][3] == 1)
        and int(item["assetId"]) not in self.item_ids_not_for_trade
    ]

    receiver_limiteds_rolimon_filtered = [
        self.all_limiteds[str(item["assetId"])]
        for item in receiver_items
        if str(item["assetId"]) in self.all_limiteds
        and self.all_limiteds[str(item["assetId"])][7] != 1
        and not (self.algorithm["modes"]["value_only"] and self.all_limiteds[str(item["assetId"])][3] == 1)
        and int(item["assetId"]) not in self.item_ids_not_accepting
    ]
    
    receiver_limiteds_rolimon = []
    for item_data in receiver_limiteds_rolimon_filtered:
        item_name = item_data[0]
        item_value = item_data[3] if item_data[3] != -1 else item_data[2]

        if "egg" in item_name.lower() and item_value < 680:
            logging.info(f"🥚 Applying egg rule to '{item_name}' (value: {item_value}) in trade generation. Treating as 0 Robux.")
            modified_item_data = list(item_data)
            modified_item_data[2] = 0
            modified_item_data[3] = 0
            receiver_limiteds_rolimon.append(modified_item_data)
        else:
            receiver_limiteds_rolimon.append(item_data)

    mode = random.choice(self.algorithm["modes"]["trade_methods"])
    if mode == "upgrade":
        receiver_min, receiver_max = self.algorithm["downgrade"]["min_items"], self.algorithm["downgrade"]["max_items"]
        giver_min, giver_max = self.algorithm["upgrade"]["min_items"], self.algorithm["upgrade"]["max_items"]
    else:
        receiver_min, receiver_max = self.algorithm["upgrade"]["min_items"], self.algorithm["upgrade"]["max_items"]
        giver_min, giver_max = self.algorithm["downgrade"]["min_items"], self.algorithm["downgrade"]["max_items"]

    best_trade_info = await algorithm.find_best_trade(
        giver_items=giver_limiteds_rolimon,
        receiver_items=receiver_limiteds_rolimon,
        settings=self.algorithm,
        giver_max=giver_max, giver_min=giver_min,
        receiver_min=receiver_min, receiver_max=receiver_max,
        allow_edge=True,
        batch_size=self.algorithm["performance"]["batch_size"],
        max_pairs=self.algorithm["performance"]["max_pairs"],
        mode=mode,
        min_trade_send_value_total=self.algorithm["thresholds"]["min_trade_send_value_total"] if not counter else 0
    )

    if best_trade_info:
        logging.info(f"✅ Best trade found for user {user_id}. Preparing trade data.")
        best_trade = best_trade_info['trade']
        
        giving_uaids_map = defaultdict(list)
        for item in giver_items:
            giving_uaids_map[item['name']].append(item)
            
        receiving_uaids_map = defaultdict(list)
        for item in receiver_items:
            receiving_uaids_map[item['name']].append(item)

        giving_item_uaids, giving_items_raw_list = [], []
        for item in best_trade["giving_items"]:
            item_name = item[0]
            if giving_uaids_map[item_name]:
                raw_item = giving_uaids_map[item_name].pop(0)
                giving_item_uaids.append(raw_item['userAssetId'])
                giving_items_raw_list.append(raw_item)
                
        receiving_item_uaids, receiving_items_raw_list = [], []
        for item in best_trade["receiving_items"]:
            item_name = item[0]
            if receiving_uaids_map[item_name]:
                raw_item = receiving_uaids_map[item_name].pop(0)
                receiving_item_uaids.append(raw_item['userAssetId'])
                receiving_items_raw_list.append(raw_item)

        if not receiving_item_uaids or not giving_item_uaids:
            return None

        data_json = {
            "offers": [
                {"userId": self.user_id, "userAssetIds": giving_item_uaids, "robux": 0},
                {"userId": user_id, "userAssetIds": receiving_item_uaids, "robux": 0}
            ]
        }
        return {
            'trade_data': data_json,
            'giving_items_raw': giving_items_raw_list,
            'receiving_items_raw': receiving_items_raw_list,
            'giving_score': best_trade_info['giving_score'],
            'receiving_score': best_trade_info['receiving_score']
        }
    else:
        return None


async def send_trade(self, user_id):
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
    trade_info_dict = await generate_trade(self, user_id, False)
    if trade_info_dict:
        trade_data = trade_info_dict['trade_data']
        logging.info(f"✉️ Sending trade to user {user_id}.")
        response = await self.authenticator_client.send_trade(TAG=self.cookie[-10:], TRADE_DATA=trade_data)

        if response.status == 200:
            self.trade_timestamps.append(time.time())
            trade_id = (await response.json())['id']
            logging.info(f"✅ Trade sent successfully. Trade ID: {trade_id}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://users.roblox.com/v1/users/{user_id}") as user_resp:
                    partner_info = {'id': user_id, 'name': 'N/A'}
                    if user_resp.status == 200:
                        user_data = await user_resp.json()
                        partner_info = {'id': user_data['id'], 'name': user_data['name']}
            
            reason = f"Sent a new outbound trade. Profit Score: `{trade_info_dict['receiving_score'] - trade_info_dict['giving_score']:.2f}`."
            webhook_payload = await generate_decision_webhook(
                self, "Sent", trade_id, partner_info, 
                trade_info_dict['giving_items_raw'], trade_info_dict['receiving_items_raw'],
                trade_info_dict['giving_score'], trade_info_dict['receiving_score'], reason
            )
            await self.send_webhook_notification(webhook_payload)

        elif response.status == 429:
            logging.error("❌ Failed to send trade: Rate limited by Roblox (429).")
            now = time.time()
            
            # This corrects the flaw. The rate limit pause should always be set 
            # for 24 hours *from now* when a 429 error occurs.
            self.rate_limit_until = now + self.TRADE_LIMIT_WINDOW

            # Clean the timestamp list to accurately check the reason for the log
            self.trade_timestamps = [ts for ts in self.trade_timestamps if now - ts < self.TRADE_LIMIT_WINDOW]
            
            if len(self.trade_timestamps) >= self.TRADE_LIMIT_COUNT:
                logging.warning(f"🕒 Daily trade limit of {self.TRADE_LIMIT_COUNT} was hit. Pausing for 24 hours.")
            else:
                logging.warning("🕒 Rate limited by Roblox (429) on a cold start. Pausing for 24 hours as a precaution.")
            
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

async def generate_decision_webhook(self, decision: str, trade_id: int, partner_info: dict, giving_items: list, receiving_items: list, giving_score: float, receiving_score: float, reason: str):
    """Generates a comprehensive webhook embed explaining a trade decision."""
    
    decision_map = {
        "Accepted": {"color": 0x4CAF50, "title": f"✅ Accepted Inbound Trade"},
        "Declined": {"color": 0xF44336, "title": f"🚫 Declined Trade"},
        "Countered": {"color": 0xFF9800, "title": f"🔄 Sent Counter-Offer"},
        "Sent": {"color": 0x2196F3, "title": f"✉️ Sent Outbound Trade"},
        "Cancelled Outbound": {"color": 0xF44336, "title": f"❌ Cancelled Outbound Trade"},
    }
    
    config = decision_map.get(decision, {"color": 0x9E9E9E, "title": f"Trade Action: {decision}"})
    
    given_value = sum(self.all_limiteds[str(item["assetId"])][3] if self.all_limiteds[str(item["assetId"])][3] != -1 else self.all_limiteds[str(item["assetId"])][2] for item in giving_items)
    received_value = sum(self.all_limiteds[str(item["assetId"])][3] if self.all_limiteds[str(item["assetId"])][3] != -1 else self.all_limiteds[str(item["assetId"])][2] for item in receiving_items)
    profit = received_value - given_value

    given_names = "\n".join([
        f"[{item['name']}](https://www.rolimons.com/item/{item['assetId']}) "
        f"({(self.all_limiteds[str(item['assetId'])][3] if self.all_limiteds[str(item['assetId'])][3] != -1 else self.all_limiteds[str(item['assetId'])][2]):,})"
        for item in giving_items
    ]) or "None"

    received_names = "\n".join([
        f"[{item['name']}](https://www.rolimons.com/item/{item['assetId']}) "
        f"({(self.all_limiteds[str(item['assetId'])][3] if self.all_limiteds[str(item['assetId'])][3] != -1 else self.all_limiteds[str(item['assetId'])][2]):,})"
        for item in receiving_items
    ]) or "None"

    embed = {
        "embeds": [
            {
                "title": config["title"],
                "color": config["color"],
                "url": f"https://www.roblox.com/trades#{trade_id}",
                "description": f"**Reason:** {reason}",
                "fields": [
                    {"name": "Partner", "value": f"[{partner_info['name']}](https://www.roblox.com/users/{partner_info['id']}/profile) (`{partner_info['id']}`)", "inline": False},
                    {"name": "Giving", "value": given_names, "inline": True},
                    {"name": "Receiving", "value": received_names, "inline": True},
                    {
                        "name": "Algorithm Analysis",
                        "value": f"Giving Score: `{giving_score:.2f}`\nReceiving Score: `{receiving_score:.2f}`\n**Profit Score:** `{receiving_score - giving_score:.2f}`",
                        "inline": False
                    },
                    {
                        "name": "Value Analysis (Rolimon's)",
                        "value": f"Giving Value: `{given_value:,}`\nReceiving Value: `{received_value:,}`\n**Profit:** `{profit:,}`",
                        "inline": False
                    }
                ],
                "footer": {"text": f"Trade ID: {trade_id}"},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        ]
    }
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
