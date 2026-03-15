from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class ProgramDTO:
    name: str
    pax: str
    guide: str
    short_guide: str

@dataclass
class GuestDTO:
    name: str
    voucher: str = "N/A"
    pickup: str = "-"
    hotel: str = "-"
    area: str = "-"
    room: str = "-"
    phone: str = "-"
    pax: str = "0/0/0"
    cot: str = "0"
    remarks: str = "-"
    agent: str = "-"
    program: str = "-"

@dataclass
class GuideDTO:
    full_info: str
    short_name: Optional[str] = None
    pickup_time: Optional[str] = None
    pickup_location: Optional[str] = None
    pax: str = "0/0/0"
    is_me: bool = False

@dataclass
class LandPlanDTO:
    program: str
    date: str
    guides: List[GuideDTO] = field(default_factory=list)
    guests: List[GuestDTO] = field(default_factory=list)
    bus: Optional[str] = None
    driver: Optional[str] = None
    pax_string: str = "0/0/0"
    is_assigned: bool = False

@dataclass
class SeaPlanDTO:
    boat: str
    pier: str
    date: str
    thai_guide: Optional[str] = None
    programs: List[ProgramDTO] = field(default_factory=list)
    guides: List[GuideDTO] = field(default_factory=list)
    total_pax: int = 0
    pax_string: str = "0/0/0"
    is_assigned: bool = False
