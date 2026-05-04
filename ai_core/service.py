import os
import json
from loguru import logger
from config import config

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

class AICoreService:
    def __init__(self):
        self.api_key = config.OPENAI_API_KEY.get_secret_value() if config.OPENAI_API_KEY else None
        self.client = AsyncOpenAI(api_key=self.api_key) if self.api_key and AsyncOpenAI else None
        
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.knowledge_dir = os.path.join(self.base_dir, "knowledge")
        self.prompts_dir = os.path.join(self.base_dir, "prompts")

        if not self.client:
            logger.warning("OPENAI_API_KEY is missing or openai package not installed. AI features limited.")

    def _load_knowledge(self, filename: str) -> str:
        path = os.path.join(self.knowledge_dir, filename)
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return f.read().strip()
        except Exception as e:
            logger.error(f"Error loading knowledge {filename}: {e}")
        return ""

    def _load_prompt(self, filename: str) -> str:
        path = os.path.join(self.prompts_dir, filename)
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return f.read().strip()
        except Exception as e:
            logger.error(f"Error loading prompt {filename}: {e}")
        return ""

    async def get_conversational_response(self, text: str, user_name: str) -> str:
        """
        Enhanced conversational response using project knowledge base and real-time tools.
        """
        if not self.client:
            return "Извините, сейчас мой мозг (ИИ) не подключен. Разработчики скоро это исправят!"

        from ai_core.tools import TOOLS_SCHEMA, TOOLS_MAP

        # Load knowledge components
        company_info = self._load_knowledge("company.txt")
        bot_features = self._load_knowledge("bot_features.txt")
        np_fees = self._load_knowledge("np_fees.txt")
        tech_manual = self._load_knowledge("technical_manual.txt")
        
        # Load and format prompt
        system_template = self._load_prompt("conversational.txt")
        if not system_template:
            system_template = "You are a professional assistant for Best Sea Phuket."

        system_prompt = system_template.format(
            company_info=company_info,
            bot_features=bot_features,
            np_fees=np_fees,
            technical_manual=tech_manual,
            user_name=user_name
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ]

        try:
            # Multi-turn tool execution loop
            for _ in range(5): # Limit recursion
                response = await self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    tools=TOOLS_SCHEMA,
                    tool_choice="auto",
                    temperature=0.7
                )
                
                msg = response.choices[0].message
                messages.append(msg)

                if msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        func_name = tool_call.function.name
                        func_to_call = TOOLS_MAP.get(func_name)
                        
                        if func_to_call:
                            logger.info(f"AI Calling Tool: {func_name}")
                            tool_result = await func_to_call()
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "name": func_name,
                                "content": str(tool_result),
                            })
                        else:
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "name": func_name,
                                "content": "Error: Tool not found.",
                            })
                    continue # Go to next iteration for model to process tool results
                else:
                    return msg.content.strip()
            
            return "Я совершил слишком много попыток получить данные. Пожалуйста, уточните запрос."
            
        except Exception as e:
            logger.error(f"Error in AICore conversational response with tools: {e}")
            return "Ой, что-то пошло не так при обращении к моим инструментам. Попробуйте позже!"

    async def parse_operational_report(self, text: str) -> dict:
        """
        Parses free-form reports into structured JSON.
        (Logic migrated from legacy ai_service)
        """
        if not self.client:
            raise ValueError("AI Service is not configured.")

        system_prompt = """You are an AI assistant for 'Best Sea' Phuket.
Extract operational data and return strict JSON:
{
    "type": "fuel" | "defect" | "general_note",
    "boat_name": "extracted boat name or null",
    "fuel_liters": integer (refilled liters or null),
    "defects": ["list of strings"] or [],
    "comment": "summary"
}"""

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                temperature=0.0
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"AI parsing error: {e}")
            raise

# Singleton instance
ai_core = AICoreService()
