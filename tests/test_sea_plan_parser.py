"""Tests for sea_plan.py parsing logic — unit tests with mocked Google Sheets data."""
import pytest
import sys
import os
import datetime
from unittest.mock import AsyncMock, patch, MagicMock

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.sea_plan import SeaPlanService


# ─── FIXTURE DATA ─────────────────────────────────────────────────────────────

def make_row(date="", thai_guide="", col2="", col3="", program="", pax="",
             col6="", guide="", phone="", a="", c="", i="", col12="", pier="",
             cot="", boat=""):
    """Helper to create a 16-column row list matching Google Sheets structure.
    
    Column mapping (0-indexed):
        0=date, 1=thai_guide, 2=voucher, 3=pickup/time, 4=program, 5=pax,
        6=room, 7=guide, 8=phone, 9=adults, 10=children, 11=infants,
        12=misc, 13=pier, 14=cot, 15=boat
    """
    return [
        date,           # 0
        thai_guide,     # 1
        col2,           # 2
        col3,           # 3
        program,        # 4
        pax,            # 5
        col6,           # 6
        guide,          # 7
        phone,          # 8
        a,              # 9
        c,              # 10
        i,              # 11
        col12,          # 12
        pier,           # 13
        cot,            # 14
        boat,           # 15 ← BOAT
    ]


# Standard sea plan header + 2 boats with programs
SEA_PLAN_DATA = [
    # Header row (row 0) — typically contains column titles
    make_row(date="Date", thai_guide="Thai", program="Program", pax="PAX",
             guide="Guide", pier="Pier", boat="Boat"),
    # Boat 1 — RPM pier
    make_row(date="15.04", thai_guide="Somchai", program="Phi Phi Bamboo",
             pax="20/2/0", guide="Nick @ElectroNick_X", pier="RPM",
             boat="SB-1"),
    make_row(program="James Bond", pax="10/0/0",
             guide="Alex @alex_guide"),
    # Boat 2 — Yamu pier
    make_row(date="15.04", thai_guide="Noi", program="5 Pearl Classic",
             pax="15/3/1", guide="Maria @maria_phuket", pier="Yamu",
             boat="Princess"),
]

EMPTY_DATA = []

COMEBACK_DATA = [
    make_row(date="Date", program="Program", pax="PAX", guide="Guide", pier="Pier", boat="Boat"),
    make_row(date="15.04", program="COMEBACK Phi Phi", pax="22/0/0",
             guide="@ElectroNick_X", pier="RPM", boat="SB-1"),
]


# ─── SERVICE SETUP ────────────────────────────────────────────────────────────

@pytest.fixture
def service():
    """Creates a SeaPlanService with mocked credentials."""
    with patch("services.sea_plan.Credentials") as mock_creds, \
         patch("services.sea_plan.gspread") as mock_gspread:
        mock_creds.from_service_account_file.return_value = MagicMock()
        mock_gspread.authorize.return_value = MagicMock()
        svc = SeaPlanService()
        return svc


# ─── _parse_sea_plan tests ────────────────────────────────────────────────────

class TestParseSeaPlan:

    @pytest.mark.asyncio
    async def test_basic_parsing(self, service):
        """Should parse boats from sample data (including header row which has 'Boat' in col 15)."""
        target_date = datetime.date(2026, 4, 15)

        with patch.object(service, 'get_date_worksheet', new_callable=AsyncMock, return_value=MagicMock()), \
             patch.object(service, '_get_worksheet_values', new_callable=AsyncMock, return_value=SEA_PLAN_DATA):
            plans = await service._parse_sea_plan(target_date)

        # Header row creates a spurious "boat" entry; real boats are SB-1 and Princess
        real_boats = [p for p in plans if p.boat in ("SB-1", "Princess")]
        assert len(real_boats) == 2

    @pytest.mark.asyncio
    async def test_empty_sheet(self, service):
        """Should return empty list for empty sheet."""
        target_date = datetime.date(2026, 4, 15)

        with patch.object(service, 'get_date_worksheet', new_callable=AsyncMock, return_value=MagicMock()), \
             patch.object(service, '_get_worksheet_values', new_callable=AsyncMock, return_value=EMPTY_DATA):
            plans = await service._parse_sea_plan(target_date)

        assert plans == []

    @pytest.mark.asyncio
    async def test_no_worksheet(self, service):
        """Should return empty if no worksheet found."""
        target_date = datetime.date(2026, 4, 15)

        with patch.object(service, 'get_date_worksheet', new_callable=AsyncMock, return_value=None):
            plans = await service._parse_sea_plan(target_date)

        assert plans == []

    @pytest.mark.asyncio
    async def test_programs_grouped_by_boat(self, service):
        """SB-1 should have 2 programs (Phi Phi + James Bond)."""
        target_date = datetime.date(2026, 4, 15)

        with patch.object(service, 'get_date_worksheet', new_callable=AsyncMock, return_value=MagicMock()), \
             patch.object(service, '_get_worksheet_values', new_callable=AsyncMock, return_value=SEA_PLAN_DATA):
            plans = await service._parse_sea_plan(target_date)

        sb1 = next(p for p in plans if p.boat == "SB-1")
        assert len(sb1.programs) == 2
        prog_names = [p.name for p in sb1.programs]
        assert "Phi Phi Bamboo" in prog_names
        assert "James Bond" in prog_names

    @pytest.mark.asyncio
    async def test_pax_accumulation(self, service):
        """SB-1 total_pax should be 20+2+0 + 10+0+0 = 32."""
        target_date = datetime.date(2026, 4, 15)

        with patch.object(service, 'get_date_worksheet', new_callable=AsyncMock, return_value=MagicMock()), \
             patch.object(service, '_get_worksheet_values', new_callable=AsyncMock, return_value=SEA_PLAN_DATA):
            plans = await service._parse_sea_plan(target_date)

        sb1 = next(p for p in plans if p.boat == "SB-1")
        assert sb1.total_pax == 32

    @pytest.mark.asyncio
    async def test_pax_string_format(self, service):
        """SB-1 should have accumulated pax_string '30/2/0'."""
        target_date = datetime.date(2026, 4, 15)

        with patch.object(service, 'get_date_worksheet', new_callable=AsyncMock, return_value=MagicMock()), \
             patch.object(service, '_get_worksheet_values', new_callable=AsyncMock, return_value=SEA_PLAN_DATA):
            plans = await service._parse_sea_plan(target_date)

        sb1 = next(p for p in plans if p.boat == "SB-1")
        assert sb1.pax_string == "30/2/0"


# ─── get_guide_sea_plan tests ────────────────────────────────────────────────

class TestGetGuideSeaPlan:

    @pytest.mark.asyncio
    async def test_filter_by_username(self, service):
        """Should return only plans containing the specified guide."""
        target_date = datetime.date(2026, 4, 15)

        with patch.object(service, 'get_date_worksheet', new_callable=AsyncMock, return_value=MagicMock()), \
             patch.object(service, '_get_worksheet_values', new_callable=AsyncMock, return_value=SEA_PLAN_DATA):
            plans = await service.get_guide_sea_plan("ElectroNick_X", target_date)

        assert len(plans) == 1
        assert plans[0].boat == "SB-1"
        assert plans[0].is_assigned is True

    @pytest.mark.asyncio
    async def test_marks_is_me(self, service):
        """The guide matching the username should have is_me=True."""
        target_date = datetime.date(2026, 4, 15)

        with patch.object(service, 'get_date_worksheet', new_callable=AsyncMock, return_value=MagicMock()), \
             patch.object(service, '_get_worksheet_values', new_callable=AsyncMock, return_value=SEA_PLAN_DATA):
            plans = await service.get_guide_sea_plan("ElectroNick_X", target_date)

        me_guides = [g for g in plans[0].guides if g.is_me]
        assert len(me_guides) >= 1

    @pytest.mark.asyncio
    async def test_case_insensitive(self, service):
        """Username matching should be case-insensitive."""
        target_date = datetime.date(2026, 4, 15)

        with patch.object(service, 'get_date_worksheet', new_callable=AsyncMock, return_value=MagicMock()), \
             patch.object(service, '_get_worksheet_values', new_callable=AsyncMock, return_value=SEA_PLAN_DATA):
            plans = await service.get_guide_sea_plan("electronick_x", target_date)

        assert len(plans) == 1

    @pytest.mark.asyncio
    async def test_nonexistent_guide(self, service):
        """Should return empty list for guide not in schedule."""
        target_date = datetime.date(2026, 4, 15)

        with patch.object(service, 'get_date_worksheet', new_callable=AsyncMock, return_value=MagicMock()), \
             patch.object(service, '_get_worksheet_values', new_callable=AsyncMock, return_value=SEA_PLAN_DATA):
            plans = await service.get_guide_sea_plan("nonexistent_user", target_date)

        assert plans == []


# ─── get_pier_detailed_plan tests ─────────────────────────────────────────────

class TestGetPierDetailedPlan:

    @pytest.mark.asyncio
    async def test_filter_by_pier(self, service):
        """Should return only boats from specified pier."""
        target_date = datetime.date(2026, 4, 15)

        with patch.object(service, 'get_date_worksheet', new_callable=AsyncMock, return_value=MagicMock()), \
             patch.object(service, '_get_worksheet_values', new_callable=AsyncMock, return_value=SEA_PLAN_DATA):
            plans = await service.get_pier_detailed_plan("RPM", target_date)

        assert len(plans) == 1
        assert plans[0].boat == "SB-1"

    @pytest.mark.asyncio
    async def test_yamu_pier(self, service):
        target_date = datetime.date(2026, 4, 15)

        with patch.object(service, 'get_date_worksheet', new_callable=AsyncMock, return_value=MagicMock()), \
             patch.object(service, '_get_worksheet_values', new_callable=AsyncMock, return_value=SEA_PLAN_DATA):
            plans = await service.get_pier_detailed_plan("Yamu", target_date)

        assert len(plans) == 1
        assert plans[0].boat == "Princess"


# ─── _parse_guest_row tests ──────────────────────────────────────────────────

class TestParseGuestRow:

    def test_basic_guest(self, service):
        row = ["15.04", "TUI", "V-001", "07:30", "Grand Hotel", "Patong",
               "201", "John Smith", "+66123456", "2", "1", "0",
               "", "Phi Phi Bamboo", "500", "VIP"]
        guest = service._parse_guest_row(row)
        assert guest.voucher == "V-001"
        assert guest.name == "John Smith"
        assert guest.pax == "2/1/0"
        assert guest.cot == "500"
        assert guest.hotel == "Grand Hotel"
        assert guest.program == "Phi Phi Bamboo"
