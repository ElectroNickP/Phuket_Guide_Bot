"""Tests for NP envelope calculator (_calc_envelope, _detect_nps) from pier_manager.py"""
import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.np_calculator import calc_envelope, detect_nps


# ─── _detect_nps tests ───────────────────────────────────────────────────────

class TestDetectNps:
    def test_phi_phi_basic(self):
        assert detect_nps("Phi Phi Bamboo") == ["PP"]

    def test_phi_phi_ovn(self):
        assert detect_nps("PP OVN Sunrise") == ["PP"]

    def test_james_bond(self):
        assert detect_nps("James Bond by Longtail") == ["JB"]

    def test_hong_island(self):
        assert detect_nps("Hong Island Sunset") == ["HG"]

    def test_11_island_all_three(self):
        assert detect_nps("11 Island Adventure") == ["PP", "JB", "HG"]

    def test_4_pearl_two_nps(self):
        assert detect_nps("4 Pearl Luxury") == ["PP", "JB"]

    def test_5_pearl_three_nps(self):
        assert detect_nps("5 Pearl Classic") == ["PP", "JB", "HG"]

    def test_krabi_tropical(self):
        assert detect_nps("Krabi Tropical Morning") == ["HG"]

    def test_no_np(self):
        assert detect_nps("City Tour Bangkok") == []

    def test_no_np_random(self):
        assert detect_nps("Cooking Class") == []

    def test_case_insensitive(self):
        assert detect_nps("PHI PHI Bamboo") == ["PP"]

    def test_phang_nga(self):
        assert detect_nps("Phang Nga Bay Tour") == ["JB"]

    def test_4_island(self):
        assert detect_nps("4 Island Tour") == ["PP"]


# ─── _calc_envelope tests ────────────────────────────────────────────────────

class TestCalcEnvelopePP:
    """Phi Phi: adult×350 + child×200 + 100 parking. No free."""

    def test_adults_only(self):
        total, _ = calc_envelope("PP", 20, 0, False)
        assert total == 20 * 350 + 100  # 7100

    def test_mixed_pax(self):
        total, _ = calc_envelope("PP", 10, 5, False)
        assert total == 10 * 350 + 5 * 200 + 100  # 4600

    def test_zero_pax(self):
        total, _ = calc_envelope("PP", 0, 0, False)
        assert total == 100  # parking only

    def test_sunday_no_difference(self):
        total_wd, _ = calc_envelope("PP", 15, 3, False)
        total_sun, _ = calc_envelope("PP", 15, 3, True)
        assert total_wd == total_sun  # PP has same rules on Sunday


class TestCalcEnvelopeJB:
    """James Bond: every 10 pax → 2 free (weekday). Sunday = full price."""

    def test_weekday_10_adults(self):
        """10 adults → 2 free → pay 8 × 300 + 100 parking = 2500"""
        total, _ = calc_envelope("JB", 10, 0, False)
        assert total == 8 * 300 + 100  # 2500

    def test_weekday_20_adults(self):
        """20 adults → 4 free → pay 16 × 300 + 100 = 4900"""
        total, _ = calc_envelope("JB", 20, 0, False)
        assert total == 16 * 300 + 100

    def test_weekday_9_adults(self):
        """9 adults → 0 free → 9 × 300 + 100 = 2800"""
        total, _ = calc_envelope("JB", 9, 0, False)
        assert total == 9 * 300 + 100

    def test_sunday_no_free(self):
        """Sunday: 20 adults → ALL pay → 20 × 300 + 100 = 6100"""
        total, _ = calc_envelope("JB", 20, 0, True)
        assert total == 20 * 300 + 100

    def test_weekday_children(self):
        """10 children → 2 free → 8 × 150 + 100 = 1300"""
        total, _ = calc_envelope("JB", 0, 10, False)
        assert total == 8 * 150 + 100

    def test_sunday_children(self):
        """Sunday: 10 children → ALL pay → 10 × 150 + 100 = 1600"""
        total, _ = calc_envelope("JB", 0, 10, True)
        assert total == 10 * 150 + 100


class TestCalcEnvelopeHG:
    """Hong Island: every 10 pax → 1 free. No parking."""

    def test_10_adults(self):
        """10 adults → 1 free → 9 × 300 = 2700"""
        total, _ = calc_envelope("HG", 10, 0, False)
        assert total == 9 * 300

    def test_20_adults(self):
        """20 adults → 2 free → 18 × 300 = 5400"""
        total, _ = calc_envelope("HG", 20, 0, False)
        assert total == 18 * 300

    def test_9_adults(self):
        """9 adults → 0 free → 9 × 300 = 2700"""
        total, _ = calc_envelope("HG", 9, 0, False)
        assert total == 9 * 300

    def test_no_parking(self):
        """HG has no parking fee"""
        total, _ = calc_envelope("HG", 5, 0, False)
        assert total == 5 * 300  # 1500, no +100

    def test_children(self):
        """10 children → 1 free → 9 × 150 = 1350"""
        total, _ = calc_envelope("HG", 0, 10, False)
        assert total == 9 * 150

    def test_mixed(self):
        """15 adults, 12 children → 1 free adult, 1 free child → 14×300 + 11×150"""
        total, _ = calc_envelope("HG", 15, 12, False)
        assert total == 14 * 300 + 11 * 150

    def test_zero(self):
        total, _ = calc_envelope("HG", 0, 0, False)
        assert total == 0


class TestCalcEnvelopeFormula:
    """Verify formula strings contain readable info."""

    def test_formula_includes_total(self):
        total, formula = calc_envelope("PP", 10, 2, is_sunday=False)
        assert f"{total}฿" in formula

    def test_jb_sunday_warning(self):
        _, formula = calc_envelope("JB", 10, 0, True)
        assert "воскресенье" in formula.lower() or "все платят" in formula.lower()
