from dataclasses import dataclass
from typing import Union, Literal, Optional, List
from trader.data_types import item_types

BASE_GENERIC_ITEM_URL = "https://www.rolimons.com/catalog"
BASE_GENERIC_ITEM_VAR_NAME = "item_details"

BASE_ITEM_URL = "https://www.rolimons.com/item/{ITEMID}"
BASE_ITEM_DETAILS_VAR_NAME = "item_details_data"
BASE_HISTORY_DATA_VAR_NAME = "history_data"
BASE_SALES_DATA_VAR_NAME = "sales_data"
BASE_OWNERSHIP_DATA_VAR_NAME = "ownership_data"
BASE_HOARDS_DATA_VAR_NAME = "hoards_data"
BASE_BC_COPIES_VAR_NAME = "bc_copies_data"
BASE_ALL_COPIES_VAR_NAME = "all_copies_data"
BASE_VALUE_CHANGES_VAR_NAME = "value_changes"

@dataclass
class HistoryData:
    timestamp: int
    favorited: int
    rap: int
    best_price: int
    num_sellers: int
    
@dataclass
class SaleData:
    timestamp: int
    avg_daily_sales_price: int
    sales_volume: int

@dataclass
class OwnershipData:
    timestamp: int
    owners: int
    bc_owners: int
    copies: int
    deleted_copies: int
    bc_copies: int
    hoarded_copies: int 
    own_two: int
    own_three: int
    own_five: int
    own_ten: int
    own_twenty: int
    own_fifty: int
    own_one_hundred: int
    own_two_fifty: int

@dataclass
class HoardData:
    owner_id: int
    owner_name: str
    quantity: int

@dataclass
class BCCopyData:
    owner_id: int
    owner_name: str
    quantity: int
    owner_bc_level: Literal[450]
    bc_uaid: int
    bc_serial: Optional[int]
    bc_updated: int
    bc_precense_update_time: int
    bc_last_online: int

@dataclass
class CopyData:
    owner_id: Optional[int]
    owner_name: Optional[str]
    quantity: int
    owner_bc_level: Optional[Literal[450]]
    uaid: int
    serial: Optional[int]
    updated: int
    presence_update_time: Optional[int]
    last_online: Optional[int]

@dataclass
class ValueChange:
    timestamp: int
    change_type: Literal[0, 1, 2, 3]
    old_value: Optional[Union[str, int]]
    new_value: Optional[Union[str, int]]

@dataclass
class ItemDetails:
    item_name: str
    acronym: Optional[str]
    asset_type_id: int
    original_price: int
    best_price: int
    rap: int
    value: Optional[int]
    created: int
    first_timestamp: int
    owners: int
    bc_owners: int
    copies: int
    deleted_copies: int
    bc_copies: int
    hoarded_copies: int
    num_sellers: int
    favorited: int
    demand: Optional[item_types.DemandLevel]
    trend: Optional[item_types.TrendLevel]
    projected: Optional[Literal[1]]
    hyped: Optional[Literal[1]]
    rare: Optional[Literal[1]]
    thumbnail_url_lg: str
    
    history_data: Optional[List[HistoryData]] = None
    sales_data: Optional[List[SaleData]] = None
    ownerships_data: Optional[List[OwnershipData]] = None
    hoards_data: Optional[List[HoardData]] = None
    bc_copies_data: Optional[List[BCCopyData]] = None
    all_copies_data: Optional[List[CopyData]] = None
    value_changes: Optional[List[ValueChange]] = None
