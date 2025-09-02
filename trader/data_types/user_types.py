from typing import TypedDict, Literal, Optional, Dict, List, NotRequired, Tuple

class WishList(TypedDict):
    asset_ids: List[int]
    last_updated: int

class NFTList(TypedDict):
    asset_ids: List[int]
    last_updated: int


class AssetFlags(TypedDict, total=False):
    nft: Literal[True]
    upgrade: Literal[True]
    downgrade: Literal[True]
    equal: Literal[True]
    overpay: Literal[True]
    lowball: Literal[True]
    value: NotRequired[int]  # value may be present or absent
    
class Asset(AssetFlags):
    id: int

class AskingList(TypedDict):
    assets: List[Asset]
    last_updated: int
    
ScannedPlayerAssets = Dict[str, 
    List[Tuple[
        int,           # uaid
        Optional[int], # serial
        int,           # created since
        int,           # owned since        
    ]]
]

class PlayerDetailsData(TypedDict):
    player_id: int
    player_name: str
    thumb_url_lg: str
    bc_type: Literal[0]
    last_roblox_activity_ts: int
    rank: Optional[int]
    trade_ad_count: int
    staff_role: Optional[str]
    dev_staff_role: Optional[str]
    wishlist: WishList
    nft_list: NFTList
    asking_list: AskingList

class ChartData(TypedDict):
    num_points: int
    nominal_scan_time: List[int]
    value: List[int]
    rap: List[int]
    num_limiteds: List[int]
