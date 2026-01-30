from typing import TypedDict, Literal, Optional, Tuple, Dict, List, Union

DemandLevel = Literal[0, 1, 2, 3, 4]
TrendLevel = Literal[0, 1, 2, 3, 4]


class ItemDetailsData(TypedDict):
    item_name: str
    asset_type_id: int
    original_price: int
    created: int
    first_timestamp: int
    best_price: int
    favorited: int
    num_sellers: int
    rap: int
    owners: int
    bc_owners: int
    copies: int
    deleted_copies: int
    bc_copies: int
    hoarded_copies: int
    acronym: Optional[str]
    value: Optional[int]
    demand: Optional[DemandLevel]
    trend: Optional[TrendLevel]
    projected: Optional[Literal[1]]
    hyped: Optional[Literal[1]]
    rare: Optional[Literal[1]]
    thumbnail_url_lg: str


ItemTuple = Tuple[
    str,                  # 0: item_name
    int,                  # 1: asset_type_id
    int,                  # 2: original_price
    int,                  # 3: created (timestamp)
    int,                  # 4: first_timestamp
    int,                  # 5: best_price
    int,                  # 6: favorited (count)
    int,                  # 7: num_sellers
    int,                  # 8: rap (recent average price)
    int,                  # 9: owners (number of owners)
    int,                  # 10: bc_owners (Builders Club owners)
    int,                  # 11: copies (total copies)
    int,                  # 12: deleted_copies (copies removed)
    int,                  # 13: bc_copies (BC copies)
    int,                  # 14: hoarded_copies
    Optional[str],        # 15: acronym (optional short code or tag)
    Optional[int],        # 16: value (optional price estimate)
    Optional[DemandLevel],# 17: demand level (enum or custom type)
    Optional[TrendLevel], # 18: trend level (enum or custom type)
    Optional[Literal[1]], # 19: projected (flag, e.g., 1 if projected)
    Optional[Literal[1]], # 20: hyped (flag, e.g., 1 if hyped)
    Optional[Literal[1]], # 21: rare (flag, e.g., 1 if rare)
    int,                  # 22: value if avaible else rap
    str                   # 23: thumbnail_url_lg (URL to large thumbnail image)
]

ItemDetails = Dict[str, ItemTuple]

class HistoryData(TypedDict):
    num_points: int
    timestamp: List[int]
    favorited: List[int]
    rap: List[int]
    best_price: List[int]
    num_sellers: List[int]
    
class SalesData(TypedDict):
    num_points: int
    timestamp: List[int]
    avg_daily_sales_price: List[int]
    sales_volume: List[int]
    
class OwnershipData(TypedDict):
    id: int
    num_points: int
    timestamps: List[int]
    owners: List[int]
    bc_owners: List[int]
    copies: List[int]
    serialized_copies: List[Optional[int]]
    deleted_copies: List[int]
    bc_copies: List[int]
    hoarded_copies: List[int]
    own_two: List[int]
    own_three: List[int]
    own_five: List[int]
    own_ten: List[int]
    own_twenty: List[int]
    own_fifty: List[int]
    own_one_hundred: List[int]
    own_two_fifty: List[int]
    
class HoardsData(TypedDict):
    num_hoards: int
    owner_ids: List[str]
    owner_names: List[str]
    quantities: List[int]

class BCCopiesData(TypedDict):
    num_bc_copies: int
    owner_ids: List[int]
    owner_names: List[str]
    quantities: List[int]
    owner_bc_levels: List[Literal[450]]
    bc_uaids: List[str]
    bc_serials: List[Optional[int]]
    bc_updated: List[int]
    bc_presence_update_time: List[int]
    bc_last_online: List[int]
    
class AllCopiesData(TypedDict):
    num_copies: int
    owner_ids: List[Optional[int]]
    owner_names: List[Optional[str]]
    quantities: List[int]
    owner_bc_levels: List[Optional[Literal[450]]]
    uaids: List[str]
    serials: List[Optional[int]]
    updated: List[int]
    presence_update_time: List[Optional[int]]
    last_online: List[Optional[int]]

ChangeType = Literal[0, 1, 2, 3]

ValueChanges = List[
    Tuple[
        int, # Timestamp
        ChangeType, # Change type
        Optional[Union[str, int]], # Old value
        Optional[Union[str, int]]  # New value
    ]
]
