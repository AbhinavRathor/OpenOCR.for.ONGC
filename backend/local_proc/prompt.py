# In local_proc/prompt.py
def build_finetuning_prompt(anchor_text: str) -> str:
    return "Extract ALL visible text from this document EXACTLY as it appears. Return only the raw text content without any formatting, analysis, or JSON structure. Include every word exactly as shown:"