import base64
import io
from pdf2image import convert_from_bytes
from PIL import Image

def render_pdf_to_base64png(pdf_stream, page_number=1, resolution=1024):
    try:
        # Reset stream position
        pdf_stream.seek(0)
        
        # Convert specific page
        images = convert_from_bytes(
            pdf_stream.read(),
            dpi=resolution,
            first_page=page_number,
            last_page=page_number
        )
        
        if not images:
            raise ValueError("No pages found in PDF")
            
        img = images[0]
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode('utf-8')
        
    except Exception as e:
        print(f"PDF render error: {str(e)}")
        # Create an error image
        img = Image.new('RGB', (800, 200), color=(255, 200, 200))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode('utf-8')
