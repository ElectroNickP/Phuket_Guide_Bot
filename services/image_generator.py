import os
import re
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from typing import List, Union
import datetime
from database.dto import SeaPlanDTO, LandPlanDTO, GuestDTO

class JobOrderGenerator:
    def __init__(self):
        self.width = 1000
        self.bg_color = (255, 255, 255)
        self.primary_color = (220, 50, 50)  # Red like the logo
        self.secondary_color = (50, 50, 50)
        self.accent_color = (240, 240, 240)
        self.text_color = (30, 30, 30)
        
        # Paths
        self.assets_dir = os.path.join(os.getcwd(), "assets")
        self.logo_path = os.path.join(self.assets_dir, "logo.png")
        
        # Font loading (fallback to default)
        try:
            # Try to find professional fonts (preferring ones we installed in Docker)
            font_paths = [
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"
            ]
            medium_font_paths = [
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            ]
            
            self.font_bold = None
            for p in font_paths:
                if os.path.exists(p):
                    self.font_bold = ImageFont.truetype(p, 40)
                    self.font_medium_bold = ImageFont.truetype(p, 30)
                    self.font_small_bold = ImageFont.truetype(p, 24)
                    break
            
            self.font_medium = None
            for p in medium_font_paths:
                if os.path.exists(p):
                    self.font_medium = ImageFont.truetype(p, 30)
                    self.font_small = ImageFont.truetype(p, 24)
                    self.font_tiny = ImageFont.truetype(p, 18)
                    break

            if not self.font_bold:
                self.font_bold = ImageFont.load_default()
                self.font_medium_bold = ImageFont.load_default()
                self.font_small_bold = ImageFont.load_default()
            if not self.font_medium:
                self.font_medium = ImageFont.load_default()
                self.font_small = ImageFont.load_default()
                self.font_tiny = ImageFont.load_default()
        except:
            self.font_bold = ImageFont.load_default()
            self.font_medium = ImageFont.load_default()
            self.font_small = ImageFont.load_default()
            self.font_tiny = ImageFont.load_default()

    def generate_sea_job_order(self, plan: SeaPlanDTO, guests: List[GuestDTO]) -> BytesIO:
        # Calculate dynamic height
        guest_rows = len(guests)
        base_height = 600
        row_height = 80
        total_height = base_height + (guest_rows * row_height) + 100
        
        img = Image.new('RGB', (self.width, total_height), self.bg_color)
        draw = ImageDraw.Draw(img)
        
        # 1. Header Area
        draw.rectangle([0, 0, self.width, 180], fill=self.accent_color)
        
        # Logo
        if os.path.exists(self.logo_path):
            try:
                logo = Image.open(self.logo_path).convert("RGBA")
                logo.thumbnail((150, 150))
                img.paste(logo, (30, 15), logo)
            except:
                draw.text((30, 60), "BEST", fill=self.primary_color, font=self.font_bold)
        else:
            draw.text((30, 60), "BEST", fill=self.primary_color, font=self.font_bold)
            
        draw.text((200, 50), "JOB ORDER: SEA TRIP", fill=self.secondary_color, font=self.font_bold)
        draw.text((200, 100), f"DATE: {plan.date}", fill=self.secondary_color, font=self.font_medium)
        
        # 2. Main Details
        y = 210
        draw.text((30, y), "TRIP DETAILS", fill=self.primary_color, font=self.font_medium)
        y += 50
        
        draw.rectangle([30, y, self.width-30, y+120], fill=self.accent_color, outline=self.secondary_color)
        details_y = y + 15
        draw.text((50, details_y), f"BOAT: {plan.boat}", fill=self.text_color, font=self.font_medium)
        draw.text((50, details_y + 45), f"PIER: {plan.pier or '---'}", fill=self.text_color, font=self.font_medium)
        
        # Extract @username for Thai Guide
        thai_guide_display = plan.thai_guide or '---'
        if thai_guide_display != '---':
            match = re.search(r'(@\w+)', thai_guide_display)
            if match:
                thai_guide_display = match.group(1)
        draw.text((50, details_y + 85), f"THAI GUIDE: {thai_guide_display}", fill=self.text_color, font=self.font_small)
        
        # 3. Programs
        y += 150
        draw.text((30, y), "PROGRAMS", fill=self.primary_color, font=self.font_medium)
        y += 50
        
        for prog in plan.programs:
            prog_text = f"• {prog.name} ({prog.pax} pax)"
            if prog.guide:
                # Apply username-only filter to program guide
                program_guide_display = prog.short_guide
                match = re.search(r'(@\w+)', program_guide_display)
                if match:
                    program_guide_display = match.group(1)
                prog_text += f" - Guide: {program_guide_display}"
            draw.text((40, y), prog_text, fill=self.text_color, font=self.font_small)
            y += 35
            
        # 4. Guest List
        y += 30
        draw.text((30, y), f"GUEST LIST ({len(guests)} groups)", fill=self.primary_color, font=self.font_medium)
        y += 50
        
        # Table Header
        draw.rectangle([30, y, self.width-30, y+50], fill=self.secondary_color)
        headers = ["Voucher", "Hotel / Room", "Name", "Pax", "COT"]
        cols = [35, 200, 450, 750, 880]
        for i, h in enumerate(headers):
            draw.text((cols[i] + 5, y + 10), h, fill=(255, 255, 255), font=self.font_tiny)
        
        y += 50
        # Rows
        for i, g in enumerate(guests):
            bg = (255, 255, 255) if i % 2 == 0 else (245, 245, 245)
            draw.rectangle([30, y, self.width-30, y+row_height], fill=bg)
            
            draw.text((cols[0] + 5, y + 10), g.voucher[:15], fill=self.text_color, font=self.font_tiny)
            draw.text((cols[1] + 5, y + 10), f"{g.hotel[:20]}\nRM: {g.room}", fill=self.text_color, font=self.font_tiny)
            draw.text((cols[2] + 5, y + 10), f"{g.name[:30]}\n{g.phone}", fill=self.text_color, font=self.font_tiny)
            draw.text((cols[3] + 5, y + 10), g.pax, fill=self.text_color, font=self.font_tiny)
            draw.text((cols[4] + 5, y + 10), g.cot, fill=self.primary_color, font=self.font_tiny)
            
            # Remarks if any
            if g.remarks and g.remarks != "-":
                draw.text((cols[0] + 5, y + 50), f"Note: {g.remarks[:100]}", fill=(100, 100, 100), font=self.font_tiny)
                
            y += row_height
            
        # Final formatting
        output = BytesIO()
        img.save(output, format='PNG')
        output.seek(0)
        return output

    def generate_land_job_order(self, plan: LandPlanDTO) -> BytesIO:
        # Land Plan structure is different
        guest_rows = len(plan.guests)
        base_height = 500
        row_height = 80
        total_height = base_height + (guest_rows * row_height) + 100
        
        img = Image.new('RGB', (self.width, total_height), self.bg_color)
        draw = ImageDraw.Draw(img)
        
        # 1. Header
        draw.rectangle([0, 0, self.width, 180], fill=self.accent_color)
        if os.path.exists(self.logo_path):
            try:
                logo = Image.open(self.logo_path).convert("RGBA")
                logo.thumbnail((150, 150))
                img.paste(logo, (30, 15), logo)
            except:
                draw.text((30, 60), "BEST", fill=self.primary_color, font=self.font_bold)
        else:
            draw.text((30, 60), "BEST", fill=self.primary_color, font=self.font_bold)
            
        draw.text((200, 50), "JOB ORDER: LAND TRIP", fill=self.secondary_color, font=self.font_bold)
        draw.text((200, 100), f"PROGRAM: {plan.program}", fill=self.secondary_color, font=self.font_medium)
        
        # 2. Details
        y = 210
        draw.rectangle([30, y, self.width-30, y+100], fill=self.accent_color, outline=self.secondary_color)
        draw.text((50, y+15), f"BUS: {plan.bus or '---'}", fill=self.text_color, font=self.font_medium)
        draw.text((50, y+55), f"DRIVER: {plan.driver or '---'}", fill=self.text_color, font=self.font_medium)
        
        # 3. Guides
        y += 130
        draw.text((30, y), "GUIDE ASSIGNMENTS", fill=self.primary_color, font=self.font_medium)
        y += 50
        for g in plan.guides:
            # Apply username-only filter to guide
            guide_display = g.full_info
            match = re.search(r'(@\w+)', guide_display)
            if match:
                guide_display = match.group(1)
            
            me_tag = " (YOU)" if g.is_me else ""
            draw.text((40, y), f"• {guide_display}{me_tag}", fill=self.text_color, font=self.font_small)
            draw.text((60, y+30), f"P/U: {g.pickup_time} @ {g.pickup_location}", fill=self.secondary_color, font=self.font_tiny)
            y += 60
            
        # 4. Guest List
        y += 20
        draw.text((30, y), f"GUEST LIST ({len(plan.guests)} groups)", fill=self.primary_color, font=self.font_medium)
        y += 50
        
        # Table Header
        draw.rectangle([30, y, self.width-30, y+50], fill=self.secondary_color)
        headers = ["Voucher", "Hotel / Room", "Name", "Pax", "COT"]
        cols = [35, 200, 450, 750, 880]
        for i, h in enumerate(headers):
            draw.text((cols[i] + 5, y + 10), h, fill=(255, 255, 255), font=self.font_tiny)
        
        y += 50
        for i, g in enumerate(plan.guests):
            bg = (255, 255, 255) if i % 2 == 0 else (245, 245, 245)
            draw.rectangle([30, y, self.width-30, y+row_height], fill=bg)
            
            draw.text((cols[0] + 5, y + 10), g.voucher[:15], fill=self.text_color, font=self.font_tiny)
            draw.text((cols[1] + 5, y + 10), f"{g.hotel[:20]}\nRM: {g.room}", fill=self.text_color, font=self.font_tiny)
            draw.text((cols[2] + 5, y + 10), f"{g.name[:30]}\n{g.phone}", fill=self.text_color, font=self.font_tiny)
            draw.text((cols[3] + 5, y + 10), g.pax, fill=self.text_color, font=self.font_tiny)
            draw.text((cols[4] + 5, y + 10), g.cot, fill=self.primary_color, font=self.font_tiny)
            
            if g.remarks and g.remarks != "-":
                draw.text((cols[0] + 5, y + 50), f"Note: {g.remarks[:100]}", fill=(100, 100, 100), font=self.font_tiny)
            y += row_height
            
        output = BytesIO()
        img.save(output, format='PNG')
        output.seek(0)
        return output

    def generate_general_schedule(self, date_str: str, sea_plans: List[SeaPlanDTO], land_plans: List[LandPlanDTO], master_schedule: dict = None) -> BytesIO:
        # One row per guide
        items = []
        master_schedule = master_schedule or {}
        
        for p in sea_plans:
            # Sea plan might have multiple guides
            for g_info in p.guides:
                uname = g_info.full_info
                match = re.search(r'(@\w+)', uname)
                if match:
                    uname = match.group(1)
                
                u_key = uname.replace("@", "").lower()
                prog_details = f"{p.boat} | {', '.join([prog.name for prog in p.programs])}"
                items.append({
                    "uname": uname,
                    "type": "SEA",
                    "details": prog_details,
                    "pickup": f"{g_info.pickup_time or '---'}",
                    "master_sched": master_schedule.get(u_key, "---")
                })
        
        for p in land_plans:
            # Land plan guides
            for g in p.guides:
                uname = g.full_info
                match = re.search(r'(@\w+)', uname)
                if match:
                    uname = match.group(1)
                
                u_key = uname.replace("@", "").lower()
                items.append({
                    "uname": uname,
                    "type": "LAND",
                    "details": p.program,
                    "pickup": g.pickup_time,
                    "master_sched": master_schedule.get(u_key, "---")
                })
        
        # Sort by username
        items.sort(key=lambda x: x['uname'])
        
        row_height = 80
        header_height = 200
        total_height = header_height + (len(items) * row_height) + 100
        
        img = Image.new('RGB', (self.width, max(800, total_height)), self.bg_color)
        draw = ImageDraw.Draw(img)
        
        # Header
        draw.rectangle([0, 0, self.width, 180], fill=self.accent_color)
        if os.path.exists(self.logo_path):
            try:
                logo = Image.open(self.logo_path).convert("RGBA")
                logo.thumbnail((150, 150))
                img.paste(logo, (30, 15), logo)
            except: pass
            
        draw.text((200, 50), f"GENERAL SCHEDULE: {date_str}", fill=self.primary_color, font=self.font_bold)
        draw.text((200, 100), f"Total Guides with Work: {len(items)}", fill=self.secondary_color, font=self.font_medium)
        
        y = 200
        # Table Header
        draw.rectangle([20, y, self.width-20, y+50], fill=self.secondary_color)
        headers = ["Guide", "Type", "Boat / Program", "Master Sched", "Pickup"]
        cols = [30, 200, 310, 620, 870] # Adjusted cols
        for i, h in enumerate(headers):
            draw.text((cols[i] + 5, y + 10), h, fill=(255, 255, 255), font=self.font_small_bold)
            
        y += 50
        # Rows
        for i, item in enumerate(items):
            bg = (255, 255, 255) if i % 2 == 0 else (245, 245, 245)
            draw.rectangle([20, y, self.width-20, y+row_height], fill=bg)
            
            draw.text((cols[0] + 5, y + 25), item['uname'], fill=self.text_color, font=self.font_small)
            draw.text((cols[1] + 5, y + 25), item['type'], fill=self.primary_color if item['type'] == 'SEA' else (50, 150, 50), font=self.font_small_bold)
            draw.text((cols[2] + 5, y + 15), item['details'][:50], fill=self.text_color, font=self.font_tiny)
            draw.text((cols[3] + 5, y + 15), item['master_sched'][:50], fill=self.secondary_color, font=self.font_tiny)
            draw.text((cols[4] + 5, y + 25), item['pickup'], fill=self.text_color, font=self.font_small)
            
            y += row_height
            
        output = BytesIO()
        img.save(output, format='PNG')
        output.seek(0)
        return output

job_order_generator = JobOrderGenerator()
