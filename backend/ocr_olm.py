# ocr_olm.py -
from io import BytesIO
import base64, os, warnings, json, asyncio
from typing import AsyncGenerator

from PIL import Image
from PyPDF2 import PdfReader
import torch
from transformers import AutoProcessor, Qwen2VLForConditionalGeneration

# Optional direct PDF → image converter
try:
    from pdf2image import convert_from_bytes
    PDF2IMAGE = True
except ImportError:
    PDF2IMAGE = False
    from local_proc.renderpdf import render_pdf_to_base64png

# Environment & model paths
warnings.filterwarnings("ignore", message=".*preprocessor.json.*")

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
MODEL_PATH = "./models/olmOCR-7B-0225-preview"
PROCESSOR_PATH = "./models/Qwen2-VL-7B-Instruct"

if not os.path.isdir(MODEL_PATH):
    raise FileNotFoundError(f"[OCR] model dir missing: {MODEL_PATH}")
if not os.path.isdir(PROCESSOR_PATH):
    raise FileNotFoundError(f"[OCR] processor dir missing: {PROCESSOR_PATH}")

PROCESSOR = AutoProcessor.from_pretrained(
    PROCESSOR_PATH, use_fast=True, local_files_only=True
)
print(f"[OCR] processor loaded from {PROCESSOR_PATH}")

MODEL = Qwen2VLForConditionalGeneration.from_pretrained(
    MODEL_PATH,
    torch_dtype=torch.bfloat16,
    device_map="auto",
    local_files_only=True,
).eval()
print(f"[OCR] model loaded from {MODEL_PATH} (device_map=auto)")

# Helper utilities
def _is_pdf(buf: bytes) -> bool:
    return buf[:4] == b"%PDF"

def _get_enhanced_prompt(kind: str = "document") -> str:
    """Enhanced prompts for better text extraction, especially for chat and conversational content."""
    if kind == "image":
        return (
            "You are an expert OCR system. Extract ALL visible text from this image exactly as it appears. "
            "Include every word, number, symbol, timestamp, username, and message. "
            "If this is a chat conversation, preserve the conversation flow with timestamps and usernames. "
            "If this is a document, maintain original formatting, line breaks, and structure. "
            "Preserve original capitalization, spacing, and punctuation. "
            "Do not add explanations, analysis, or interpretations. "
            "Return only the raw extracted text content."
        )
    return (
        "You are a professional OCR system specialized in document text extraction. "
        "Extract ALL visible text from this document page exactly as it appears. "
        "Include headers, body text, tables, lists, timestamps, usernames, messages, and any other readable content. "
        "If this contains chat messages or conversations, preserve the chronological order and speaker identification. "
        "If this contains structured data like tables or forms, maintain the structure. "
        "Preserve original formatting, capitalization, punctuation, and line breaks. "
        "Do not summarize, interpret, or add commentary. "
        "Return only the complete extracted text content."
    )

def _extract_actual_text(raw: str) -> str:
    """Enhanced text extraction with better cleaning and formatting."""
    import re
    
    try:
        raw = raw.strip()
        
        # Try to parse as JSON first
        if raw.startswith('{') or raw.startswith('['):
            try:
                json_data = json.loads(raw)
                if isinstance(json_data, dict):
                    # Extract text content from common keys
                    for key in ('text', 'content', 'ocr_text', 'extracted_text', 'natural_text'):
                        if key in json_data and json_data[key]:
                            return str(json_data[key]).strip()
                    # Fallback: get all string values from the JSON
                    text_parts = [str(v).strip() for v in json_data.values() if isinstance(v, str) and str(v).strip()]
                    return '\n'.join(text_parts) if text_parts else str(json_data)
                elif isinstance(json_data, list):
                    return '\n'.join([str(item).strip() for item in json_data if str(item).strip()])
            except json.JSONDecodeError:
                pass  # Fall through to treat as plain text

        # Clean up common formatting issues
        cleaned_text = raw
        cleaned_text = re.sub(r'^\s*[\{\[\"\']|[\}\]\"\']\s*$', '', cleaned_text)  # Remove JSON-like wrapping
        cleaned_text = cleaned_text.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"')  # Un-escape characters

        # Normalize whitespace while preserving structure
        lines = cleaned_text.split('\n')
        cleaned_lines = []
        for line in lines:
            line = line.strip()
            if line:  # Only add non-empty lines
                cleaned_lines.append(line)
        
        result = '\n'.join(cleaned_lines)
        
        # If result is still empty or very short, return original cleaned raw output
        return raw.strip() if len(result) < 10 else result
        
    except Exception as e:
        print(f"[WARN] Error cleaning text output: {e}")
        return raw.strip()  # Return the raw text on error

def _preprocess_image(img: Image.Image) -> Image.Image:
    """Enhanced image preprocessing for better OCR results."""
    # Convert to RGB if needed
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    # Resize if too small (minimum 800px on shortest side)
    width, height = img.size
    min_dim = min(width, height)
    if min_dim < 800:
        scale_factor = 800 / min_dim
        new_width = int(width * scale_factor)
        new_height = int(height * scale_factor)
        img = img.resize((new_width, new_height), Image.LANCZOS)
        print(f"[DEBUG] Upscaled image to {new_width}x{new_height}")
    
    return img

def _run_ocr_on_image(img: Image.Image, prompt: str) -> str:
    """Enhanced OCR with optimized generation parameters for better text extraction."""
    img = _preprocess_image(img)
    
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {"type": "image", "image": img}
        ]
    }]
    
    text_for_model = PROCESSOR.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = PROCESSOR(text=text_for_model, images=img, return_tensors="pt").to(DEVICE)

    with torch.no_grad():
        out_ids = MODEL.generate(
            **inputs,
            temperature=0.8,              # Higher temperature for more natural text
            do_sample=True,               # Enable sampling for better coverage
            max_new_tokens=3072,          # Increased token limit for longer documents
            top_p=0.95,                   # Higher top_p for more diverse output
            repetition_penalty=1.1,       # Reduce repetition
            pad_token_id=PROCESSOR.tokenizer.pad_token_id,
        )

    new_ids = out_ids[:, inputs["input_ids"].shape[1]:]
    decoded = PROCESSOR.batch_decode(new_ids, skip_special_tokens=True)[0]
    print(f"[DEBUG] Raw model output: {decoded[:200]}...")
    
    extracted = _extract_actual_text(decoded)
    print(f"[DEBUG] Extracted text length: {len(extracted)} chars")
    return extracted

# ENHANCED: Streaming OCR for real-time results - FORCED for all PDF sizes
async def stream_ocr_bytes(buf: bytes) -> AsyncGenerator[dict, None]:
    """Stream OCR results page by page for real-time processing - OPTIMIZED for ALL PDF sizes."""
    if _is_pdf(buf):
        async for result in _stream_pdf(buf):
            yield result
    else:
        result = _run_single_image(buf)
        yield result

async def _stream_pdf(buf: bytes) -> AsyncGenerator[dict, None]:
    """Stream PDF pages one by one - OPTIMIZED for ALL PDF sizes with FORCED real-time processing."""
    if PDF2IMAGE:
        print("[INFO] FORCED real-time streaming PDF with pdf2image (page-by-page mode)")
        
        try:
            # ENHANCED: Get total page count first WITHOUT loading all pages
            from PyPDF2 import PdfReader
            reader = PdfReader(BytesIO(buf))
            total_pages = len(reader.pages)
            print(f"[STREAM] FORCED processing {total_pages} pages individually (no batching)")
            
            # CRITICAL: Process pages one by one WITHOUT loading all in memory
            for page_num in range(1, total_pages + 1):
                try:
                    # Yield page start notification IMMEDIATELY
                    yield {
                        "type": "page_start",
                        "page": page_num,
                        "total_pages": total_pages,
                        "status": "processing"
                    }
                    print(f"[STREAM] Starting page {page_num}/{total_pages}")
                    
                    # Convert SINGLE page (memory efficient - no bulk loading)
                    images = convert_from_bytes(
                        buf, 
                        dpi=300, 
                        first_page=page_num, 
                        last_page=page_num  # Process ONLY this page
                    )
                    
                    if images:
                        img = images[0]  # Should be only one image
                        txt = _run_ocr_on_image(img, _get_enhanced_prompt("document"))
                        
                        # Generate preview image
                        preview_img = img.copy()
                        preview_img.thumbnail((400, 600), Image.LANCZOS)
                        preview_buffer = BytesIO()
                        preview_img.save(preview_buffer, format='JPEG', quality=85)
                        preview_b64 = base64.b64encode(preview_buffer.getvalue()).decode('utf-8')
                        preview_url = f"data:image/jpeg;base64,{preview_b64}"
                        
                        # Yield completed page result IMMEDIATELY - NO BUFFERING
                        yield {
                            "type": "page_complete",
                            "page": page_num,
                            "text": txt,
                            "error": None,
                            "total_pages": total_pages,
                            "status": "completed",
                            "preview": preview_url
                        }
                        
                        print(f"[STREAM] Page {page_num}/{total_pages} completed and IMMEDIATELY streamed")
                    
                except Exception as e:
                    print(f"[STREAM] Error processing page {page_num}: {e}")
                    yield {
                        "type": "page_complete",
                        "page": page_num,
                        "text": "",
                        "error": str(e),
                        "total_pages": total_pages,
                        "status": "error",
                        "preview": None
                    }
            
            # Send final completion signal
            yield {
                "type": "processing_complete",
                "status": "finished",
                "total_pages": total_pages
            }
            print(f"[STREAM] FORCED real-time processing completed for all {total_pages} pages")
            
        except Exception as e:
            print(f"[STREAM] PDF processing error: {e}")
            yield {
                "type": "error",
                "error": str(e)
            }
    else:
        # Fallback implementation for systems without pdf2image
        print("[INFO] FORCED real-time streaming with fallback renderer")
        stream = BytesIO(buf)
        total = len(PdfReader(stream).pages)
        
        for idx in range(1, total + 1):
            try:
                yield {
                    "type": "page_start",
                    "page": idx,
                    "total_pages": total,
                    "status": "processing"
                }
                
                stream.seek(0)
                b64 = render_pdf_to_base64png(stream, page_number=idx, resolution=1800)
                img = Image.open(BytesIO(base64.b64decode(b64)))
                txt = _run_ocr_on_image(img, _get_enhanced_prompt("document"))
                
                yield {
                    "type": "page_complete",
                    "page": idx,
                    "text": txt,
                    "error": None,
                    "total_pages": total,
                    "status": "completed"
                }
                print(f"[STREAM] Fallback: Page {idx}/{total} completed and streamed")
                
            except Exception as e:
                yield {
                    "type": "page_complete",
                    "page": idx,
                    "text": "",
                    "error": str(e),
                    "total_pages": total,
                    "status": "error"
                }
        
        # Send final completion signal
        yield {
            "type": "processing_complete",
            "status": "finished",
            "total_pages": total
        }

# Legacy compatibility functions
def run_ocr_bytes(buf: bytes) -> dict:
    """Standard OCR for backward compatibility."""
    if _is_pdf(buf):
        return _run_pdf(buf)
    return _run_single_image(buf)

def extract_text_from_pdf(path: str, lang: str | None = None) -> dict:
    with open(path, "rb") as fh:
        data = fh.read()
    print(f"[OCR] processing {path}")
    return run_ocr_bytes(data)

def _run_pdf(buf: bytes) -> dict:
    """Enhanced PDF processing with image previews."""
    pages = []
    if PDF2IMAGE:
        print("[INFO] Enhanced pdf2image processing with previews")
        images = convert_from_bytes(buf, dpi=300)  # Higher DPI
        total = len(images)
        for idx, img in enumerate(images, 1):
            try:
                txt = _run_ocr_on_image(img, _get_enhanced_prompt("document"))
                
                # Generate preview image (smaller version for UI)
                preview_img = img.copy()
                preview_img.thumbnail((400, 600), Image.LANCZOS)
                preview_buffer = BytesIO()
                preview_img.save(preview_buffer, format='JPEG', quality=85)
                preview_b64 = base64.b64encode(preview_buffer.getvalue()).decode('utf-8')
                preview_url = f"data:image/jpeg;base64,{preview_b64}"
                
                pages.append({
                    "page": idx,
                    "text": txt,
                    "error": None,
                    "preview": preview_url
                })
            except Exception as e:
                pages.append({
                    "page": idx,
                    "text": "",
                    "error": str(e),
                    "preview": None
                })
    else:
        print("[INFO] Enhanced fallback processing with previews")
        stream = BytesIO(buf)
        total = len(PdfReader(stream).pages)
        for idx in range(1, total + 1):
            try:
                stream.seek(0)
                b64 = render_pdf_to_base64png(stream, page_number=idx, resolution=1800)
                img = Image.open(BytesIO(base64.b64decode(b64)))
                txt = _run_ocr_on_image(img, _get_enhanced_prompt("document"))
                
                # Generate preview (reuse the rendered image but make it smaller)
                preview_img = img.copy()
                preview_img.thumbnail((400, 600), Image.LANCZOS)
                preview_buffer = BytesIO()
                preview_img.save(preview_buffer, format='JPEG', quality=85)
                preview_b64 = base64.b64encode(preview_buffer.getvalue()).decode('utf-8')
                preview_url = f"data:image/jpeg;base64,{preview_b64}"
                
                pages.append({
                    "page": idx,
                    "text": txt,
                    "error": None,
                    "preview": preview_url
                })
            except Exception as e:
                pages.append({
                    "page": idx,
                    "text": "",
                    "error": str(e),
                    "preview": None
                })
    
    return {"success": True, "pages": pages, "total_pages": len(pages), "error": None}

def _run_single_image(buf: bytes) -> dict:
    """Enhanced single image processing with preview."""
    try:
        img = Image.open(BytesIO(buf))
    except Exception as e:
        return {"success": False, "pages": [], "total_pages": 0,
                "error": f"Cannot open image: {e}"}

    txt = _run_ocr_on_image(img, _get_enhanced_prompt("image"))
    
    # Generate preview image
    preview_img = img.copy()
    preview_img.thumbnail((400, 600), Image.LANCZOS)
    preview_buffer = BytesIO()
    preview_img.save(preview_buffer, format='JPEG', quality=85)
    preview_b64 = base64.b64encode(preview_buffer.getvalue()).decode('utf-8')
    preview_url = f"data:image/jpeg;base64,{preview_b64}"
    
    return {
        "success": True,
        "pages": [{"page": 1, "text": txt, "error": None, "preview": preview_url}],
        "total_pages": 1,
        "error": None,
    }
