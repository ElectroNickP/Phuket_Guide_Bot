import asyncio
from database.db import AsyncSessionLocal
from database.models import User
from sqlalchemy import select

async def check_users():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User.username))
        usernames = [u.lower() for u in result.scalars().all() if u]
        
        # List from debug_wakeup.py output
        active_guides = [
            'ag_ali777', 'dp_dianaa', 'ia_ilia', 'ik_ivan', 'ko_kseniia', 
            'la_liubov', 'll_julia', 'ls_liudmila', 'ms_maksim', 'nb_nataliia', 
            'nk_nikolai', 'nv_nataliia', 'oa_olesia', 'ov_olga', 'pa_polina', 
            'sa_svetlana', 'se_egor13', 'tm_mikhail1', 'uo_oleg', 'vm_valeriia', 
            'vm_vugi13', 'vovlove', 'vz_valeriia'
        ]
        
        print(f"Total users in DB: {len(usernames)}")
        for g in active_guides:
            if g in usernames:
                print(f"  [OK] @{g} is in DB")
            else:
                print(f"  [!!] @{g} is NOT in DB")

if __name__ == '__main__':
    asyncio.run(check_users())
