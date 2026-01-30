import aiohttp
import re
import json
from dataclasses import dataclass, field
from functools import wraps
from typing import Dict, List, Optional, Tuple, Any, Literal, cast, Callable, Coroutine

from trader.models.item import HistoryData, SaleData, OwnershipData, HoardData, BCCopyData, CopyData, ValueChange
from trader.models.user import ScannedPlayerAsset, WishList, NFTList, AskingList, Asking, ChartData
from trader.data_types import item_types, user_types

def pass_session(func: Callable[..., Coroutine[Any, Any, Any]]) -> Callable[..., Coroutine[Any, Any, Any]]:
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        if 'session' in kwargs and kwargs['session'] is not None:
            return await func(*args, **kwargs)
        
        async with aiohttp.ClientSession() as session:
            kwargs['session'] = session
            return await func(*args, **kwargs)
    return wrapper

@dataclass
class JSVariable:
    name: str
    value: Any

@dataclass
class JSVariableExtractor:
    html_text: str
    variables: Dict[str, JSVariable] = field(default_factory=dict)

    def extract(self) -> Dict[str, JSVariable]:
        script_blocks: List[str] = self._extract_script_blocks(self.html_text)
        for script in script_blocks:
            self._extract_from_script(script)
        return self.variables

    def _extract_script_blocks(self, html: str) -> List[str]:
        pattern = re.compile(r"<script[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE)
        return [m.strip() for m in pattern.findall(html)]

    def _extract_from_script(self, script: str) -> None:
        decl_pattern = re.compile(r'\b(var|let|const)\s+([a-zA-Z_$][\w$]*)\s*=\s*', re.DOTALL)
        for match in decl_pattern.finditer(script):
            var_name: str = match.group(2)
            start_index: int = match.end()

            value, _ = self._read_until_semicolon(script, start_index)
            if value is not None:
                parsed_value: Any = self._clean_value(value)
                self.variables[var_name] = JSVariable(name=var_name, value=parsed_value)

    def _read_until_semicolon(self, script: str, start_index: int) -> Tuple[Optional[str], int]:
        i: int = start_index
        depth: int = 0
        in_str: Optional[str] = None
        escape: bool = False

        while i < len(script):
            char: str = script[i]

            if escape:
                escape = False
            elif char == '\\':
                escape = True
            elif in_str:
                if char == in_str:
                    in_str = None
            elif char in ('"', "'"):
                in_str = char
            elif char in '{[(':
                depth += 1
            elif char in '}])':
                depth -= 1
            elif char == ';' and depth <= 0:
                return script[start_index:i].strip(), i
            i += 1

        return None, len(script)

    def _clean_value(self, raw: str) -> Any:
        raw = raw.strip()
        try:
            if raw.startswith(("'", '"')):
                return json.loads(raw.replace("'", '"'))
            elif raw.startswith('{') or raw.startswith('['):
                return json.loads(raw)
            elif raw.lower() in ('true', 'false'):
                return raw.lower() == 'true'
            elif raw == 'null':
                return None
            elif re.match(r'^-?\d+$', raw):
                return int(raw)
        except Exception:
            pass
        return raw

class Parse:
    class Item:
        @staticmethod
        def history_data(history: item_types.HistoryData) -> List[HistoryData]:
            num_points = history["num_points"]
            
            return [
                HistoryData(
                    timestamp = history["timestamp"][i],
                    favorited = history["favorited"][i],
                    rap = history["rap"][i],
                    best_price = history["best_price"][i],
                    num_sellers = history["num_sellers"][i],
                )
                for i in range(num_points)
            ]
        
        @staticmethod
        def sales_data(sales: item_types.SalesData) -> List[SaleData]:
            num_points = sales["num_points"]
            return [
                SaleData(
                    timestamp = sales["timestamp"][i],
                    avg_daily_sales_price = sales["avg_daily_sales_price"][i],
                    sales_volume = sales["sales_volume"][i],
                )
                for i in range(num_points)
            ]
        
        @staticmethod
        def ownership_data(ownership: item_types.OwnershipData) -> List[OwnershipData]:
            num_points = ownership["num_points"]
            return [
                OwnershipData(
                    timestamp = ownership["timestamps"][i],
                    owners = ownership["owners"][i],
                    bc_owners = ownership["bc_copies"][i],
                    copies = ownership["copies"][i],
                    deleted_copies = ownership["deleted_copies"][i],
                    bc_copies = ownership["bc_copies"][i],
                    hoarded_copies = ownership["hoarded_copies"][i],
                    own_two = ownership["own_two"][i],
                    own_three = ownership["own_three"][i],
                    own_five = ownership["own_five"][i],
                    own_ten = ownership["own_ten"][i],
                    own_twenty = ownership["own_twenty"][i],
                    own_fifty = ownership["own_fifty"][i],
                    own_one_hundred = ownership["own_one_hundred"][i],
                    own_two_fifty = ownership["own_two_fifty"][i],
                )
                for i in range(num_points)
            ]

        @staticmethod
        def hoards_data(hoards: item_types.HoardsData) -> List[HoardData]:
            num_hoards = hoards["num_hoards"]
            return [
                HoardData(
                    owner_id = int(hoards["owner_ids"][i]),
                    owner_name = hoards["owner_names"][i],
                    quantity = hoards["quantities"][i],
                )
                for i in range(num_hoards)
            ]
        
        @staticmethod
        def bc_copies_data(bc_copies: item_types.BCCopiesData) -> List[BCCopyData]:
            num_bc_copies = bc_copies["num_bc_copies"]
            return [
                BCCopyData(
                    owner_id = bc_copies["owner_ids"][i],
                    owner_name = bc_copies["owner_names"][i],
                    quantity = bc_copies["quantities"][i],
                    owner_bc_level = bc_copies["owner_bc_levels"][i],
                    bc_uaid = int(bc_copies["bc_uaids"][i]),
                    bc_serial = bc_copies["bc_serials"][i],
                    bc_updated = bc_copies["bc_updated"][i],
                    bc_precense_update_time = bc_copies["bc_presence_update_time"][i],
                    bc_last_online = bc_copies["bc_last_online"][i]                
                )
                for i in range(num_bc_copies)
            ]
        
        @staticmethod
        def all_copies_data(all_copies: item_types.AllCopiesData) -> List[CopyData]:
            num_copies = all_copies["num_copies"]
            return [
                CopyData(
                    owner_id = all_copies["owner_ids"][i],
                    owner_name = all_copies["owner_names"][i],
                    quantity = all_copies["quantities"][i],
                    owner_bc_level = all_copies["owner_bc_levels"][i],
                    uaid = int(all_copies["uaids"][i]),
                    serial = all_copies["serials"][i],
                    updated = all_copies["updated"][i],
                    presence_update_time = all_copies["presence_update_time"][i],
                    last_online = all_copies["last_online"][i], 
                )
                for i in range(num_copies)
            ]
        
        @staticmethod
        def value_changes(values_changes: item_types.ValueChanges) -> List[ValueChange]:
            return [
                ValueChange(
                    timestamp = data[0],
                    change_type = data[1],
                    old_value = data[2],
                    new_value = data[3]
                )
                for data in values_changes
            ]
    
    class User:
        @staticmethod
        def scanned_player_assets(scanned_assets: user_types.ScannedPlayerAssets) -> Dict[str, List[List[ScannedPlayerAsset]]]:
            return {item_id: [[
                ScannedPlayerAsset(
                    uaid = sub_item[0],
                    serial = sub_item[1],
                    created = sub_item[2]
                ) for sub_item in item]]
                for item_id, item in scanned_assets.items()
            }
        
        @staticmethod
        def wish_list(wish_list: user_types.WishList) -> WishList:
            if wish_list:
                return WishList(
                    asset_ids = wish_list["asset_ids"],
                    last_updated = wish_list["last_updated"]
                )
            else:
                return WishList(
                    asset_ids = [],
                    last_updated = None
                )
        
        @staticmethod
        def nft_list(nft_list: user_types.NFTList) -> NFTList:
            if nft_list:
                return NFTList(
                    asset_ids = nft_list["asset_ids"],
                    last_updated = nft_list["last_updated"]
                )
            else:
                return NFTList(
                    asset_ids = [],
                    last_updated = None
                )
            
        @staticmethod
        def asking_list(asking_list: user_types.AskingList) -> AskingList:
            if asking_list:
                return AskingList(
                    assets = [    
                        Asking(
                                id = item["id"],
                                value = item.get("value"),
                                asking = cast(Literal["nft", "upgrade", "downgrade", "equal", "overpay", "lowball", "value"], next((k for k, v in item.items() if k in ["nft", "upgrade", "downgrade", "equal", "overpay", "lowball", "value"] and v), "downgrade"))
                            )
                    for item in asking_list["assets"]],
                    last_updated = asking_list["last_updated"]
                )
            else:
                return AskingList(
                    assets = [],
                    last_updated = None
                )
            
        @staticmethod
        def chart_data(chart_data: user_types.ChartData) -> List[ChartData]:
            if chart_data:
                return [
                    ChartData(
                        nominal_scan_time = chart_data["nominal_scan_time"][i],
                        value = chart_data["value"][i],
                        rap = chart_data["value"][i],
                        num_limiteds = chart_data["num_limiteds"][i]
                    )
                    for i in range(chart_data["num_points"])
                ]
            else:
                return []
