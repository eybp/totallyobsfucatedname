import asyncio
import aiohttp
import random
import time
import json
import aiofiles
import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from . import rolimon
from . import user
from . import trades
from . import cookie
from . import errors
from . import database # <-- Import the new database module

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(message)s",
    datefmt="%d-%b-%Y %H:%M:%S",
    handlers=[logging.StreamHandler()]
)

class bot:
    def __init__(self, data, authenticator):

        self.cookie = data["account"]["cookie"]
        self.opt_secret = data["account"]["opt_secret"]
        self.authenticator_client = authenticator
        self.roblox_cookie_working = True
        self.rolimons_working = True
        self.is_paused_on_hold = False
        self.sleep_time_trade_send = data["trade"]["sleep_time"]

        self.roli_verification = data["rolimon"]["roli_verification_token"]
        self.rolimon_ads_sleep_time = data["rolimon"]["ads"]["sleep_time"]
        self.rolimon_ads = data["rolimon"]["ads"]["offers"]
        self.limiteds_value_updater_sleep_time = data["rolimon"]["limiteds_value_updater_sleep_time"]
        self.manual_rolimon_limiteds = data["rolimon"]["manual_rolimon_items"]
        self.item_ids_not_for_trade = data["trade"]["items"]["not_for_trade"]
        self.item_ids_not_accepting = data["trade"]["items"]["not_accepting"]

        self.algorithm = data["trade"]["algorithm"]

        self.webhook = data["webhook"]

        self.limiteds = {}
        self.all_limiteds = {}

        self.user_id = None
        self.xcsrf_token = None
        self.last_generated_time = 0

        self.all_processed_trades = []

        self.item_price = {}
        self.trade_timestamps = []
        self.rate_limit_until = 0
        self.TRADE_LIMIT_COUNT = 100
        self.TRADE_LIMIT_WINDOW = 24 * 60 * 60 # 24 hours in seconds
        self.db_conn = None
        self.scheduler = None

    async def _init_database_and_collector(self):
        """Initializes the database and starts the background data collection tasks."""
        logging.info("Data collector is DISABLED.")
        # logging.info("Initializing data collector...")
        # try:
        #     database.initialize_database()
        #     self.db_conn = database.get_db_connection()
        #     self.scheduler = AsyncIOScheduler()
        #     
        #     # Schedule the collection jobs
        #     self.scheduler.add_job(self.fetch_and_store_market_data, 'interval', minutes=15, id='market_data_job')
        #     self.scheduler.add_job(self.fetch_and_store_trade_history, 'interval', minutes=30, id='trade_history_job')
        #     
        #     self.scheduler.start()
        #     logging.info("✅ Data collector has been scheduled and is running in the background.")
        # except Exception as e:
        #     logging.error(f"❌ Failed to initialize data collector: {e}", exc_info=True)

    async def fetch_and_store_market_data(self):
        """Fetches and stores the latest item market data from Rolimon's."""
        logging.info("COLLECTOR: Starting market data fetch...")
        try:
            items = await rolimon.limiteds()
            if not items:
                logging.warning("COLLECTOR: No item data was returned from Rolimon's. Skipping this run.")
                return

            timestamp = int(time.time())
            records = [
                (timestamp, int(item_id), data[0], data[3], data[2], data[5], data[6], data[7], data[8], data[9])
                for item_id, data in items.items()
            ]
            
            cursor = self.db_conn.cursor()
            cursor.executemany("""
                INSERT OR IGNORE INTO item_market_history 
                (timestamp, item_id, item_name, value, rap, demand, trend, projected, hyped, rare) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, records)
            self.db_conn.commit()
            logging.info(f"COLLECTOR: Successfully stored {cursor.rowcount} new item market snapshots.")
        except Exception as e:
            logging.error(f"COLLECTOR: An error occurred during market data collection: {e}", exc_info=True)

    async def fetch_and_store_trade_history(self):
        """Fetches the bot's completed and inactive trades from Roblox."""
        logging.info("COLLECTOR: Starting trade history fetch...")
        async with aiohttp.ClientSession(cookies={".ROBLOSECURITY": self.cookie}) as session:
            try:
                for trade_type in ["Completed", "Inactive"]:
                    logging.info(f"COLLECTOR: Checking for new '{trade_type}' trades...")
                    url = f"https://trades.roblox.com/v1/trades/{trade_type.lower()}?sortOrder=Desc&limit=100"
                    async with session.get(url) as response:
                        if response.status != 200:
                            logging.error(f"COLLECTOR: Failed to get {trade_type} trades. Status: {response.status}")
                            continue
                        
                        data = await response.json()
                        trades_list = data.get('data', [])
                        if not trades_list:
                            logging.info(f"COLLECTOR: No new '{trade_type}' trades found.")
                            continue
                        
                        logging.info(f"COLLECTOR: Found {len(trades_list)} '{trade_type}' trades to process.")
                        tasks = [self._process_and_store_trade(trade['id'], session) for trade in trades_list]
                        await asyncio.gather(*tasks)

            except Exception as e:
                logging.error(f"COLLECTOR: An error occurred during trade history collection: {e}", exc_info=True)

    async def _process_and_store_trade(self, trade_id: int, session: aiohttp.ClientSession):
        """Fetches details for a single trade and stores it in the database."""
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT 1 FROM trade_history WHERE trade_id = ?", (trade_id,))
        if cursor.fetchone():
            return # Trade already exists in DB

        url = f"https://trades.roblox.com/v1/trades/{trade_id}"
        async with session.get(url) as response:
            if response.status != 200:
                logging.warning(f"COLLECTOR: Could not fetch details for trade {trade_id}. Status: {response.status}")
                return
            
            trade_data = await response.json()
            partner = next((offer['user'] for offer in trade_data['offers'] if offer['user']['id'] != self.user_id), None)
            if not partner:
                logging.warning(f"COLLECTOR: Could not determine partner for trade {trade_id}. Skipping.")
                return

            giving_offer = next(offer for offer in trade_data['offers'] if offer['user']['id'] == self.user_id)
            receiving_offer = next(offer for offer in trade_data['offers'] if offer['user']['id'] == partner['id'])

            given_rap = sum(item.get('recentAveragePrice', 0) or 0 for item in giving_offer['userAssets'])
            received_rap = sum(item.get('recentAveragePrice', 0) or 0 for item in receiving_offer['userAssets'])
            profit = received_rap - given_rap
            
            trade_type = "Sidegrade"
            if len(receiving_offer['userAssets']) < len(giving_offer['userAssets']):
                trade_type = "Upgrade"
            elif len(receiving_offer['userAssets']) > len(giving_offer['userAssets']):
                trade_type = "Downgrade"

            created_ts = int(datetime.fromisoformat(trade_data['created'].replace('Z', '+00:00')).timestamp())
            
            # <-- FIX: Use .get() to provide a fallback to the 'created' timestamp
            updated_timestamp_str = trade_data.get('updated', trade_data['created']) 
            updated_ts = int(datetime.fromisoformat(updated_timestamp_str.replace('Z', '+00:00')).timestamp())

            cursor.execute("INSERT OR IGNORE INTO trade_history VALUES (?, ?, ?, ?, ?, ?, ?)", 
                           (trade_id, partner['id'], trade_data['status'], created_ts, updated_ts, profit, trade_type))

            assets = []
            for item in giving_offer['userAssets']:
                assets.append((trade_id, item['assetId'], item['name'], 1, item.get('value'), item.get('recentAveragePrice')))
            for item in receiving_offer['userAssets']:
                assets.append((trade_id, item['assetId'], item['name'], 0, item.get('value'), item.get('recentAveragePrice')))
            
            cursor.executemany("INSERT INTO trade_assets (trade_id, asset_id, asset_name, is_giving, value, rap) VALUES (?, ?, ?, ?, ?, ?)", assets)
            self.db_conn.commit()
            logging.info(f"COLLECTOR: Successfully stored details for new trade {trade_id}.")

    async def scrape_user_id(self):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://users.roblox.com/v1/users/authenticated", cookies={".ROBLOSECURITY": self.cookie}) as response:
                    if response.status == 200:
                        self.user_id = (await response.json())["id"]
                        logging.info(f"✅ User ID scraped: {self.user_id}")
                    else:
                        raise errors.invalid_cookie("Invalid cookie provided.")
        except Exception as e:
            logging.error(f"❌ Error scraping user ID: {e}")

    async def generate_xcsrf_token(self):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post("https://auth.roblox.com/v2/logout", cookies={".ROBLOSECURITY": self.cookie}) as resp:
                    self.xcsrf_token = resp.headers.get("x-csrf-token")
            self.last_generated_time = time.time()
        except Exception as e:
            logging.error(f"❌ Error generating xcsrf token: {e}")

    async def get_xcsrf_token(self):
        current_time = time.time()
        if current_time - self.last_generated_time >= 120 or self.xcsrf_token is None:
            await self.generate_xcsrf_token()
        return self.xcsrf_token

    async def xcsrf_refresher(self):
        while True:
            try:
                await self.generate_xcsrf_token()
                logging.info("🌀 xcsrf token refreshed.")
            except:
                logging.warning("⚠️ Failed to refresh xcsrf token.")
            await asyncio.sleep(60)

    async def ad_poster(self):
        await asyncio.sleep(10)
        while True:
            try:
                if self.rolimon_ads:
                    ad = random.choice(self.rolimon_ads)
                    offer_items = ad["offer_item_ids"]

                    for item in offer_items:
                        if str(item) not in self.limiteds or item in self.item_ids_not_for_trade:
                            self.rolimon_ads.remove(ad)
                            continue

                    request_item_ids = ad["request_item_ids"]

                    for item in request_item_ids:
                        if item in self.item_ids_not_accepting:
                            self.rolimon_ads.remove(ad)
                            continue

                    request_tags = ad["request_tags"]
                else:
                    offer_items = []
                    limiteds = list(self.limiteds.copy().keys())
                    random.shuffle(limiteds)
                    for item in limiteds:
                        if item in self.item_ids_not_for_trade:
                            continue
                        if any(not i["isOnHold"] for i in self.limiteds[item]):
                            offer_items.append(int(item))
                            continue
                        if len(offer_items) >= 4:
                            break
                    request_item_ids = []
                    request_tags = random.sample(["any", "demand", "rares", "rap", "upgrade"], 4)
                offer_items = offer_items[:4]
                request_tags = request_tags[:4]
                if await rolimon.post_ad(self.roli_verification, self.user_id, offer_items, request_item_ids, request_tags):
                    logging.info("✅ Ad posted successfully.")
                else:
                    logging.error(f"❌ Failed to post ad")
            except Exception as e:
                logging.error(f"❌ Failed to post ad: {e}")
            finally:
                await asyncio.sleep(self.rolimon_ads_sleep_time)

    async def update_limiteds(self):
        self.limiteds = await user.scrape_collectibles(self.cookie, self.user_id)
        limiteds_value = await rolimon.limiteds()
        for item_id, item_data in self.manual_rolimon_limiteds.items():
            limiteds_value[item_id] = item_data
        for limited in self.limiteds:
            limited = str(limited)
            async with aiofiles.open("values.json", "r") as f:
                data = json.loads(await f.read())
                for item_id, value in data.items():
                    if item_id in limiteds_value and int(value) != limiteds_value[item_id][3]:
                        limiteds_value[item_id][3] = int(value)
        if limiteds_value != self.all_limiteds:
            logging.info("✅ Limiteds updated.")
        self.all_limiteds = limiteds_value

    async def update_limiteds_task(self):
        while True:
            try:
                await self.update_limiteds()
            except Exception as e:
                logging.error(f"❌ Error updating limiteds: {e}")
            finally:
                await asyncio.sleep(60)

    async def send_webhook_notification(self, message):
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(self.webhook, json=message)
            logging.info(f"✅ Webhook notification sent")
        except Exception as e:
            logging.error(f"❌ Failed to send webhook: {e}")

    async def start(self):
        self.cookie = cookie.Bypass(self.cookie).start_process()
        if not self.cookie:
            logging.error("❌ Invalid cookie provided. Failed to refresh the cookie.")
            raise errors.invalid_cookie("Invalid cookie provided. Failed to refresh the cookie.")

        await self.scrape_user_id()
        await self.generate_xcsrf_token()
        await self.authenticator_client.add(self.user_id, self.opt_secret, self.cookie, self.cookie[-10:])
        # await self._init_database_and_collector() # <-- DATA COLLECTOR DISABLED
        await self.update_limiteds()

        await asyncio.gather(
            self.update_limiteds_task(),
            self.ad_poster(),
            self.xcsrf_refresher(),
            trades.check_outbound(self),
            trades.trades_watcher(self),
            rolimon.track_trade_ads(self),
            trades.check_inbound(self),
        )
