import sys
with open('core/gemini_live_voice.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# We are going to fix from line 1546 (1-indexed) to the end.
# Convert to 0-indexed: line 1546 -> index 1545.
start_index = 1545

prefix = lines[:start_index]

corrected_lines = [
    "    async def _emit_state(self, state: str) -> None:\n",
    "        if state == self._last_state:\n",
    "            return\n",
    "        self._last_state = state\n",
    "        await self._call(self.on_state, state)\n",
    "\n",
    "    async def _emit_level(self, level: float, speaking: bool) -> None:\n",
    "        await self._call(self.on_level, max(0.0, min(1.0, float(level))), speaking)\n",
    "\n",
    "    async def _emit_error(self, exc: Exception) -> None:\n",
    "        await self._call(self.on_error, str(exc))\n",
    "\n",
    "    @staticmethod\n",
    "    async def _call(callback: AsyncCallback | None, *args: Any) -> None:\n",
    "        if callback is None:\n",
    "            return\n",
    "        result = callback(*args)\n",
    "        if asyncio.iscoroutine(result):\n",
    "            await result\n",
    "\n",
    "    def detect_emotion_from_text(self, text: str) -> str:\n",
    "        \"\"\"Detect emotion from text using simple keyword matching.\n",
    "        Returns one of: 'frustrated', 'happy', 'neutral'.\n",
    "        \"\"\"\n",
    "        if not text:\n",
    "            return 'neutral'\n",
    "        text_lower = text.lower()\n",
    "        frustrated_keywords = ['frustrado', 'irritado', 'chateado', 'puto', 'puta', 'merda', 'caralho', 'foda', 'odesseio']\n",
    "        happy_keywords = ['feliz', 'contente', 'alegre', 'bom', 'ótimo', 'excelente', 'maravilhoso', 'felicidade', 'alegria']\n",
    "        for word in frustrated_keywords:\n",
    "            if word in text_lower:\n",
    "                return 'frustrated'\n",
    "        for word in happy_keywords:\n",
    "            if word in text_lower:\n",
    "                return 'happy'\n",
    "        return 'neutral'\n",
    "\n",
    "    def _adjust_response_for_emotion(self, response: str, emotion: str) -> str:\n",
    "        \"\"\"Adjust the response text based on detected emotion.\n",
    "        Returns adjusted response string.\n",
    "        \"\"\"\n",
    "        if not response or emotion == 'neutral':\n",
    "            return response\n",
    "        if emotion == 'frustrated':\n",
    "            return f\"Entendo sua frustração. {response}\"\n",
    "        elif emotion == 'happy':\n",
    "            return f\"Que ótimo que você está feliz! {response}\"\n",
    "        # fallback\n",
    "        return response\n",
]

new_lines = prefix + corrected_lines

with open('core/gemini_live_voice.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('File fixed.')