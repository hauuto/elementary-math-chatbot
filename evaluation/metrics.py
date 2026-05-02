import re

def extract_answer(text: str) -> str:
    """
    Extract the final numeric answer from model output.
    """
    # 1. Look for explicit answer keywords
    match = re.search(r'(?:Đáp số|Kết quả|Vậy)(?:[\s:]*)([0-9.,]+)', text, re.IGNORECASE)
    if match:
        num_str = match.group(1)
    else:
        # 2. Look for the last number
        numbers = re.findall(r'[0-9.,]+', text)
        if not numbers:
            return ""
        num_str = numbers[-1]

    # 3. Normalize
    num_str = num_str.rstrip('.') # remove trailing period if any
    num_str = num_str.replace(',', '.') # standardize decimal separator
    # If the format was like 30,651 and meant thousands, handling it properly is complex without context,
    # but basic normalization is replacing commas.
    # To strip leading zeros:
    if '.' in num_str:
        num_str = num_str.lstrip('0')
        if num_str.startswith('.'):
            num_str = '0' + num_str
    else:
        num_str = num_str.lstrip('0')

    return num_str if num_str else "0"
