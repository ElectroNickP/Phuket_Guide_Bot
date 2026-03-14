import sys
import os
import datetime
from io import BytesIO

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd())))

from services.image_generator import job_order_generator
from database.dto import SeaPlanDTO, LandPlanDTO, GuestDTO, ProgramDTO, GuideDTO

def test_gen():
    print("Testing Sea Job Order generation...")
    mock_plan = SeaPlanDTO(
        boat="PIMCHAN 3 eng",
        pier="RPM",
        date="15.03",
        thai_guide="Guide Smile",
        programs=[
            ProgramDTO(name="5 Pearls comfort", pax="38", guide="VIACHESLAV LERNER", short_guide="LV_Viacheslav")
        ],
        guides=[GuideDTO(full_info="VIACHESLAV LERNER @LV_Viacheslav", is_me=True)],
        total_pax=38,
        is_assigned=True
    )
    
    mock_guests = [
        GuestDTO(program="5 Pearls comfort", agent="Best", voucher="V123", pickup="08:00", hotel="Hilton", room="101", name="John Doe", phone="123", pax="2/1/0", cot="0", remarks="No spicy"),
        GuestDTO(program="5 Pearls comfort", agent="Best", voucher="V124", pickup="08:15", hotel="Marriott", room="202", name="Jane Smith", phone="456", pax="2/1/0", cot="1000", remarks="-")
    ]
    
    try:
        output = job_order_generator.generate_sea_job_order(mock_plan, mock_guests)
        with open("test_sea_jo.png", "wb") as f:
            f.write(output.getvalue())
        print("✅ Sea Job Order generated: test_sea_jo.png")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ Sea Job Order failed: {e}")

    print("\nTesting Land Job Order generation...")
    mock_land = LandPlanDTO(
        program="Similans",
        date="15.03",
        bus="Bus 1",
        driver="Somchai",
        guides=[GuideDTO(full_info="VIACHESLAV LERNER @LV_Viacheslav", is_me=True)],
        guests=[
            GuestDTO(voucher="V777", pickup="07:00", hotel="Amanpuri", room="Villa 1", name="Elon Musk", phone="001", pax="1/0/0", cot="0")
        ],
        is_assigned=True
    )
    
    try:
        output = job_order_generator.generate_land_job_order(mock_land)
        with open("test_land_jo.png", "wb") as f:
            f.write(output.getvalue())
        print("✅ Land Job Order generated: test_land_jo.png")
    except Exception as e:
        print(f"❌ Land Job Order failed: {e}")

if __name__ == "__main__":
    test_gen()
