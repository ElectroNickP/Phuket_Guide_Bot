from utils.time import get_phuket_now

NP_PROGRAM_MAP: list[tuple[str, list[str]]] = [
    ("pp bamboo",         ["PP"]),
    ("pp ovn",            ["PP"]),
    ("pp sunrise",        ["PP"]),
    ("11 island",         ["PP", "JB", "HG"]),
    ("11 остров",         ["PP", "JB", "HG"]),
    ("4 pearl",           ["PP", "JB"]),
    ("4 жемчуж",          ["PP", "JB"]),
    ("5 pearl",           ["PP", "JB", "HG"]),
    ("5 жемчуж",          ["PP", "JB", "HG"]),
    ("krabi tropical",    ["HG"]),
    ("phi phi",           ["PP"]),
    ("james bond",        ["JB"]),
    ("phang nga",         ["JB"]),
    ("hong island",       ["HG"]),
    ("hong",              ["HG"]),
    ("4 island",          ["PP"]),
]

NP_FEES = {
    "PP": {
        "emoji": "🏝",
        "name": "Phi Phi (PP)",
        "adult": 350,
        "child": 200,
        "parking_flat": 100,  # flat per visit
        "free_per_10": 0,     # optional ("can cut"), not applied by default
        "sunday_note": None,
    },
    "JB": {
        "emoji": "🗿",
        "name": "James Bond (JB)",
        "adult": 300,
        "child": 150,
        "parking_flat": 100,
        "free_per_10": 2,     # every 10 pax -> 2 free (pay 8)
        "sunday_note": "⚠️ Воскресенье: полная оплата, без бесплатных!",
    },
    "HG": {
        "emoji": "🌊",
        "name": "Hong Island (HG)",
        "adult": 300,
        "child": 150,
        "parking_flat": 0,
        "free_per_10": 1,     # every 10 pax -> 1 free
        "sunday_note": None,
    },
}

def detect_nps(program_name: str) -> list[str]:
    """Returns list of NP codes for the given program name (may be multiple)."""
    lower = program_name.lower()
    for keyword, codes in NP_PROGRAM_MAP:
        if keyword in lower:
            return codes
    return []

def np_fee_line(code: str) -> str:
    fee = NP_FEES[code]
    now = get_phuket_now()
    is_sunday = now.weekday() == 6
    lines = []
    # Price line
    price = f"{fee['emoji']} взр. {fee['adult']}฿ / реб. {fee['child']}฿"
    if fee["parking_flat"]:
        price += f" + {fee['parking_flat']}฿ паркинг (за заход)"
    else:
        price += " (без парковки)"
    lines.append(f"  💵 {price}")
    # Free rule
    if fee["free_per_10"] and not (code == "JB" and is_sunday):
        lines.append(f"  🎫 Бесплатно: каждые 10 — {fee['free_per_10']} бесплатно")
    if fee["sunday_note"] and is_sunday:
        lines.append(f"  {fee['sunday_note']}")
    elif fee["sunday_note"] and not is_sunday:
        lines.append(f"  ℹ️ {fee['sunday_note']}")
    return "\n".join(lines)

def calc_envelope(code: str, adults: int, children: int, is_sunday: bool) -> tuple[int, str]:
    """
    Returns (total_thb, explanation_str).
    Rules:
      PP : A×350 + C×200 + 100 flat parking (no auto-free)
      JB weekday: (A - floor(A/10)×2)×300 + (C - floor(C/10)×2)×150 + 100 parking
      JB Sunday : A×300 + C×150 + 100 parking (full price, no free)
      HG : (A - floor(A/10))×300 + (C - floor(C/10))×150 (no parking)
    """
    fee = NP_FEES[code]
    parking = fee["parking_flat"]
    lines = []

    if code == "PP":
        pay_a = adults
        pay_c = children
        total = pay_a * 350 + pay_c * 200 + parking
        if pay_a:
            lines.append(f"{pay_a}×350฿")
        if pay_c:
            lines.append(f"{pay_c}×200฿ (дет)")
        if parking:
            lines.append(f"+{parking}฿ паркинг")

    elif code == "JB":
        if is_sunday:
            pay_a, pay_c = adults, children
            free_a = free_c = 0
            lines.append("⚠️ Воскресенье — все платят")
        else:
            free_a = (adults // 10) * 2
            free_c = (children // 10) * 2
            pay_a = adults - free_a
            pay_c = children - free_c
        total = pay_a * 300 + pay_c * 150 + parking
        if pay_a:
            lines.append(f"{pay_a}×300฿")
        if not is_sunday and (free_a or free_c):
            lines.append(f"(-{free_a} беспл.)")
        if pay_c:
            lines.append(f"{pay_c}×150฿ (дет)")
        if parking:
            lines.append(f"+{parking}฿ паркинг")

    else:  # HG
        free_a = adults // 10
        free_c = children // 10
        pay_a = adults - free_a
        pay_c = children - free_c
        total = pay_a * 300 + pay_c * 150  # no parking
        if pay_a:
            lines.append(f"{pay_a}×300฿")
        if free_a:
            lines.append(f"(-{free_a} беспл.)")
        if pay_c:
            lines.append(f"{pay_c}×150฿ (дет)")

    formula = " ".join(lines) + f" = {total}฿"
    return total, formula
