import asyncio
from loguru import logger
from tests.e2e.client import TestClient
from tests.e2e.config import TIMEOUT, RETRIES

async def wait_for_response(client: TestClient, text_to_expect: str, check_buttons: bool = False, expect_not: bool = False, timeout: int = TIMEOUT) -> bool:
    for _ in range(timeout * 2): # Check every 0.5s
        messages = await client.get_last_messages(3)
        for msg in messages:
            # Check text
            if msg.text and text_to_expect.lower() in msg.text.lower():
                if expect_not:
                    return False
                return True
            
            # Check buttons
            if check_buttons and msg.buttons:
                all_buttons = [btn for row in msg.buttons for btn in row]
                if any(text_to_expect.lower() in btn.text.lower() for btn in all_buttons):
                    if expect_not:
                        return False
                    return True
                    
        await asyncio.sleep(0.5)
    
    if expect_not:
        return True # Didn't find it, which is the expected outcome
    return False

async def run_flow(flow: list[tuple]):
    client = TestClient()
    await client.connect()
    try:
        for attempt in range(RETRIES):
            try:
                # Optional: Clear chat at the start of the flow to ensure isolated tests
                await client.clear_chat()
                await asyncio.sleep(1) # Give it a moment to clear
                
                for step in flow:
                    action = step[0]
                    
                    if action == "send":
                        text = step[1]
                        await client.send(text)
                        
                    elif action == "expect":
                        text = step[1]
                        logger.debug(f"Expecting text or button: '{text}'...")
                        # We check both message text and button text
                        found = await wait_for_response(client, text, check_buttons=True, expect_not=False)
                        if not found:
                            last_msgs = await client.get_last_messages(2)
                            last_text = [m.text for m in last_msgs]
                            raise AssertionError(f"Expected to find '{text}'. Last messages: {last_text}")
                        logger.debug("✅ Match found")

                    elif action == "expect_not":
                        text = step[1]
                        logger.debug(f"Expecting NOT to see: '{text}'...")
                        not_found = await wait_for_response(client, text, check_buttons=True, expect_not=True, timeout=2)
                        if not not_found:
                            raise AssertionError(f"Expected NOT to find '{text}', but it was found.")
                        logger.debug("✅ Missing as expected")
                        
                    elif action == "click":
                        index = step[1]
                        await client.click(index)
                        
                    elif action == "sleep":
                        seconds = float(step[1])
                        logger.debug(f"Sleeping {seconds}s...")
                        await asyncio.sleep(seconds)
                
                # Flow succeeded, break out of retry loop
                break
                
            except AssertionError as ae:
                logger.error(f"Flow assertion failed on attempt {attempt+1}/{RETRIES}: {ae}")
                if attempt == RETRIES - 1:
                    raise ae
            except Exception as e:
                logger.error(f"Flow unexpected error on attempt {attempt+1}/{RETRIES}: {e}")
                if attempt == RETRIES - 1:
                    raise e
    finally:
        await client.disconnect()
