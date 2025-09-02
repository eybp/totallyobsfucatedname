# collector/service.py
import asyncio
import aiohttp
import time
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .database import get_db_connection
# We need to import from the parent 'trader' directory.
# This requires your project root to be in the Python path.
from trader import rolimon
from trader.helpers import JSVariableExtractor

# --- Configuration ---
# You would load this from your main config file
# For simplicity, we define it here.
ROBLOX_COOKIE = "YOUR_.ROBLOSECURITY_COOKIE_HERE" 
BOT_USER_ID = 12345678 # Your bot's user ID

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ COLLECTOR │ %(levelname)-8s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

class DataCollectionService:
    def __init__(self):
        self.db_conn = get_db_connection()
        self.scheduler = AsyncIOScheduler()
        self.session = aiohttp.ClientSession(cookies={".ROBLOSECURITY": ROBLOX_COOKIE})

    async def fetch_and_store_market_data(self):
        """Fetches and stores the latest item market data from Rolimon's."""
        logging.info("Fetching latest market data from Rolimon's...")
        try:
            items = await rolimon.limiteds()
            if not items:
                logging.warning("No item data was returned from Rolimon's.")
                return

            timestamp = int(time.time())
            records = [
                (
                    timestamp, int(item_id), data[0], data[3], data[2], 
                    data[5], data[6], data[7], data[8], data[9]
                ) for item_id, data in items.items()
            ]
            
            cursor = self.db_conn.cursor()
            cursor.executemany("""
                INSERT OR IGNORE INTO item_market_history 
                (timestamp, item_id, item_name, value, rap, demand, trend, projected, hyped, rare) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, records)
            self.db_conn.commit()
            logging.info(f"Successfully stored {len(records)} item market snapshots.")
        except Exception as e:
            logging.error(f"Failed to fetch market data: {e}", exc_info=True)

    async def fetch_and_store_trade_history(self):
        """Fetches the bot's completed and inactive trades."""
        logging.info("Fetching latest trade history from Roblox...")
        try:
            for trade_type in ["Completed", "Inactive"]:
                url = f"https://trades.roblox.com/v1/trades/{trade_type.lower()}?sortOrder=Desc&limit=100"
                async with self.session.get(url) as response:
                    if response.status != 200:
                        logging.error(f"Failed to get {trade_type} trades. Status: {response.status}")
                        continue
                    
                    data = await response.json()
                    trades = data.get('data', [])
                    for trade in trades:
                        await self._process_and_store_trade(trade['id'])

        except Exception as e:
            logging.error(f"Failed to fetch trade history: {e}", exc_info=True)

    async def _process_and_store_trade(self, trade_id: int):
        """Fetches details for a single trade and stores it in the database."""
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT 1 FROM trade_history WHERE trade_id = ?", (trade_id,))
        if cursor.fetchone():
            return # Trade already exists

        url = f"https://trades.roblox.com/v1/trades/{trade_id}"
        async with self.session.get(url) as response:
            if response.status != 200:
                logging.warning(f"Could not fetch details for trade {trade_id}. Status: {response.status}")
                return
            
            trade_data = await response.json()
            
            partner = next((offer['user'] for offer in trade_data['offers'] if offer['user']['id'] != BOT_USER_ID), None)
            if not partner:
                return

            # Your bot's offer
            giving_offer = next(offer for offer in trade_data['offers'] if offer['user']['id'] == BOT_USER_ID)
            # The other user's offer
            receiving_offer = partner and next(offer for offer in trade_data['offers'] if offer['user']['id'] == partner['id'])

            # Calculate profit and trade type
            given_rap = sum(item['recentAveragePrice'] for item in giving_offer['userAssets'])
            received_rap = sum(item['recentAveragePrice'] for item in receiving_offer['userAssets'])
            profit = received_rap - given_rap
            
            trade_type = "Sidegrade"
            if len(receiving_offer['userAssets']) < len(giving_offer['userAssets']):
                trade_type = "Upgrade"
            elif len(receiving_offer['userAssets']) > len(giving_offer['userAssets']):
                trade_type = "Downgrade"

            # Insert into trade_history
            created_ts = int(time.mktime(time.strptime(trade_data['created'].split('.')[0], "%Y-%m-%dT%H:%M:%S")))
            updated_ts = int(time.mktime(time.strptime(trade_data['updated'].split('.')[0], "%Y-%m-%dT%H:%M:%S")))

            cursor.execute("""
                INSERT OR IGNORE INTO trade_history 
                (trade_id, partner_id, status, created_timestamp, last_updated_timestamp, profit_rap, trade_type) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                trade_id, partner['id'], trade_data['status'], created_ts, updated_ts, profit, trade_type
            ))

            # Insert assets
            assets_to_insert = []
            for item in giving_offer['userAssets']:
                assets_to_insert.append((trade_id, item['assetId'], item['name'], 1, item.get('value'), item['recentAveragePrice']))
            for item in receiving_offer['userAssets']:
                 assets_to_insert.append((trade_id, item['assetId'], item['name'], 0, item.get('value'), item['recentAveragePrice']))
            
            cursor.executemany("""
                INSERT INTO trade_assets (trade_id, asset_id, asset_name, is_giving, value, rap)
                VALUES (?, ?, ?, ?, ?, ?)
            """, assets_to_insert)

            self.db_conn.commit()
            logging.info(f"Stored details for trade {trade_id}.")

    async def start(self):
        """Starts the scheduler and its jobs."""
        logging.info("Starting Data Collection Service...")
        # Schedule jobs to run at regular intervals
        self.scheduler.add_job(self.fetch_and_store_market_data, 'interval', minutes=15)
        self.scheduler.add_job(self.fetch_and_store_trade_history, 'interval', minutes=30)
        self.scheduler.start()
        
        # Keep the script running
        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, SystemExit):
            logging.info("Shutting down Data Collection Service.")
            await self.shutdown()

    async def shutdown(self):
        if self.session and not self.session.closed:
            await self.session.close()
        self.scheduler.shutdown()
        self.db_conn.close()

if __name__ == "__main__":
    # To run the collector: python -m collector.service
    service = DataCollectionService()
    asyncio.run(service.start())
