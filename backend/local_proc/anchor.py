from PyPDF2 import PdfReader

def get_anchor_text(pdf_stream, page_number=1, mode="pdfreport", max_length=4000):
    try:
        # Reset stream position
        pdf_stream.seek(0)
        reader = PdfReader(pdf_stream)
        
        if page_number > len(reader.pages):
            return ""
            
        text = reader.pages[page_number-1].extract_text() or ""
        return ' '.join(text.split())[:max_length]
        
    except Exception as e:
        print(f"Anchor text error: {str(e)}")
        return ""
