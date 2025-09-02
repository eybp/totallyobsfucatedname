from dataclasses import dataclass
from typing import Literal, Union, List, Optional, Dict, Tuple

BASE_PLAYER_INFO_URL = "https://www.rolimons.com/player/{ITEMID}"
BASE_PLAYER_DETAILS_VAR_NAME = "player_details_data"
BASE_SCANNED_ASSETS_VAR_NAME = "scanned_player_assets"
BASE_CHART_DATA_VAR_NAME = "chart_data"

@dataclass
class ScannedPlayerAsset:
    uaid: int
    serial: Union[None, int]
    created: int

@dataclass
class ChartData:
    nominal_scan_time: int
    value: int
    rap: int
    num_limiteds: int

@dataclass
class WishList:
    asset_ids: List[int]
    last_updated: Optional[int]

@dataclass
class NFTList:
    asset_ids: List[int]
    last_updated: Optional[int]

@dataclass
class Asking:
    id: int
    value: Optional[int]
    asking: Literal["nft", "upgrade", "downgrade", "equal", "overpay", "lowball", "value", None]
    
    
@dataclass
class AskingList:
    assets: List[Asking]
    last_updated: Optional[int]

@dataclass
class PlayerInfo:
    player_id: int
    player_name: str
    thumb_url_lg: str
    bc_type: Literal[0]
    last_roblox_activity_ts: int
    trade_ad_count: int
    rank: Optional[int]
    staff_role: Optional[str]
    dev_staff_role: Optional[str]
    wishlist: WishList
    nft_list: NFTList
    asking_list: AskingList
    
    scanned_player_assets: Dict[str, List[List[ScannedPlayerAsset]]]
    chart_data: List[ChartData]
