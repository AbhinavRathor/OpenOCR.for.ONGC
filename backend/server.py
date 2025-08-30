# server.py with WebSocket support for real-time processing
from fastapi import FastAPI, File, UploadFile, Form, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os, traceback, uuid, pathlib, json, asyncio
import torch
from datetime import datetime

from ocr_olm import extract_text_from_pdf, stream_ocr_bytes

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Standard upload endpoint (existing)
@app.post("/upload/")
async def upload_file(file: UploadFile = File(...), lang: str = Form(...)):
    temp_file_path = None
    try:
        safe_name = pathlib.Path(file.filename).name.replace(" ", "_")
        temp_file_path = f"temp_{uuid.uuid4().hex}_{safe_name}"
        
        with open(temp_file_path, "wb") as f:
            f.write(await file.read())
        
        print(f"[INFO] File saved: {temp_file_path}")
        print(f"[INFO] Language: {lang}")
        
        ocr_result = extract_text_from_pdf(temp_file_path, lang)
        
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        
        if ocr_result["success"]:
            # Process text to maintain original formatting
            if len(ocr_result["pages"]) == 1:
                extracted_text = ocr_result["pages"][0]["text"]
            else:
                text_parts = []
                for page_info in ocr_result["pages"]:
                    if page_info["error"]:
                        text_parts.append(f"Page {page_info['page']}: ERROR - {page_info['error']}")
                    else:
                        page_text = page_info["text"]
                        if page_text and page_text.strip():
                            text_parts.append(f"Page {page_info['page']}:\n{page_text}")
                        else:
                            text_parts.append(f"Page {page_info['page']}: No readable text found")
                
                extracted_text = "\n\n".join(text_parts)
            
            return {
                "success": True,
                "filename": file.filename,
                "lang": lang,
                "text": extracted_text,
                "pages": ocr_result["pages"],
                "total_pages": ocr_result["total_pages"]
            }
        else:
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": f"OCR failed: {ocr_result['error']}", 
                    "filename": file.filename
                }
            )
        
    except Exception as e:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except:
                pass
        
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": f"Server error: {str(e)}", 
                "filename": file.filename
            }
        )

# Real-time streaming endpoint
@app.websocket("/ws/upload/")
async def websocket_upload(websocket: WebSocket):
    await websocket.accept()
    print("[WebSocket] Client connected")
    
    try:
        # Receive file data
        data = await websocket.receive_text()
        request_data = json.loads(data)
        
        file_data = request_data.get("file_data")  # Base64 encoded file
        filename = request_data.get("filename")
        lang = request_data.get("lang", "eng")
        
        print(f"[WebSocket] Processing file: {filename}")
        
        # Decode file data
        import base64
        file_bytes = base64.b64decode(file_data)
        
        # Stream OCR results
        async for result in stream_ocr_bytes(file_bytes):
            print(f"[WebSocket] Sending result: {result.get('type', 'unknown')} - Page {result.get('page', 'N/A')}")
            await websocket.send_text(json.dumps(result))
            
            # Small delay to ensure proper message ordering
            await asyncio.sleep(0.1)
        
        print("[WebSocket] Processing completed")
        
    except WebSocketDisconnect:
        print("[WebSocket] Client disconnected")
    except Exception as e:
        print(f"[WebSocket] Error: {str(e)}")
        try:
            await websocket.send_text(json.dumps({
                "type": "error",
                "error": str(e)
            }))
        except:
            pass  # Connection might be closed

# NEW: AI Document Assistant Chat Endpoint
@app.post("/chat/")
async def chat_with_document(
    message: str = Form(...),
    extracted_text: str = Form(default=""),
    conversation_history: str = Form(default=""),
    document_name: str = Form(default="")
):
    """Chat endpoint for AI Document Assistant - leverages existing OCR model for text analysis"""
    try:
        from ocr_olm import PROCESSOR, MODEL, DEVICE
        
        print(f"[CHAT] Received message: {message[:100]}...")
        print(f"[CHAT] Document context: {len(extracted_text)} characters")
        
        # Build context-aware prompt for document analysis
        context_text = extracted_text[:3000] if extracted_text else "No document content available."
        
        # Parse conversation history
        try:
            history = json.loads(conversation_history) if conversation_history else []
        except:
            history = []
        
        # Build conversation context
        history_text = ""
        if history:
            recent_history = history[-4:]  # Last 4 messages for context
            for msg in recent_history:
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                history_text += f"{role.capitalize()}: {content}\n"
        
        # Create enhanced prompt for document analysis
        system_prompt = f"""You are an AI Document Assistant specialized in analyzing and answering questions about documents. 

Document: {document_name}
Content: {context_text}

Previous conversation:
{history_text}

Current question: {message}

Instructions:
1. Answer based primarily on the document content provided
2. Be specific and cite relevant parts when possible
3. If the answer isn't in the document, clearly state that
4. Provide helpful, accurate, and concise responses
5. For analysis requests, be thorough but organized

Response:"""

        # Use existing model for text analysis (without image input)
        messages = [{
            "role": "user",
            "content": [{"type": "text", "text": system_prompt}]
        }]
        
        text_for_model = PROCESSOR.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        
        # Process without image input - just text
        inputs = PROCESSOR(
            text=text_for_model, 
            images=None,  # No image needed for chat
            return_tensors="pt"
        ).to(DEVICE)
        
        with torch.no_grad():
            out_ids = MODEL.generate(
                **inputs,
                temperature=0.7,              # Balanced creativity
                do_sample=True,               
                max_new_tokens=800,          # Longer responses for detailed analysis
                top_p=0.9,                   
                repetition_penalty=1.1,      
                pad_token_id=PROCESSOR.tokenizer.pad_token_id,
            )
        
        new_ids = out_ids[:, inputs["input_ids"].shape[1]:]
        response = PROCESSOR.batch_decode(new_ids, skip_special_tokens=True)[0]
        
        # Clean up response
        response = response.strip()
        
        # Remove any potential prompt echoing
        if "Response:" in response:
            response = response.split("Response:")[-1].strip()
        
        print(f"[CHAT] Generated response: {response[:200]}...")
        
        return {
            "success": True,
            "response": response,
            "timestamp": datetime.now().isoformat(),
            "model": "olmOCR-7B-0225-preview",
            "document_context": bool(extracted_text)
        }
        
    except Exception as e:
        print(f"[CHAT] Error: {str(e)}")
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": f"Chat processing error: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
        )

# NEW: Quick analysis endpoint for automatic document insights
@app.post("/analyze/")
async def analyze_document(
    extracted_text: str = Form(...),
    document_name: str = Form(default=""),
    analysis_type: str = Form(default="summary")  # summary, key_points, entities, dates
):
    """Quick document analysis endpoint"""
    try:
        from ocr_olm import PROCESSOR, MODEL, DEVICE
        
        analysis_prompts = {
            "summary": "Provide a comprehensive summary of this document, highlighting the main topics and key information.",
            "key_points": "Extract the main key points, important information, and significant details from this document. Present them as a structured list.",
            "entities": "Identify and list all important entities mentioned in this document: names, organizations, locations, dates, amounts, etc.",
            "dates": "Find and list all dates, deadlines, time periods, and temporal information mentioned in this document.",
            "questions": "Based on this document content, suggest 5-7 relevant questions that users might want to ask about it."
        }
        
        prompt = analysis_prompts.get(analysis_type, analysis_prompts["summary"])
        context_text = extracted_text[:3500] if extracted_text else ""
        
        system_prompt = f"""Analyze the following document and {prompt}

Document: {document_name}
Content: {context_text}

Analysis:"""

        messages = [{
            "role": "user",
            "content": [{"type": "text", "text": system_prompt}]
        }]
        
        text_for_model = PROCESSOR.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        
        inputs = PROCESSOR(
            text=text_for_model, 
            images=None,
            return_tensors="pt"
        ).to(DEVICE)
        
        with torch.no_grad():
            out_ids = MODEL.generate(
                **inputs,
                temperature=0.6,
                do_sample=True,
                max_new_tokens=600,
                top_p=0.9,
                repetition_penalty=1.1,
                pad_token_id=PROCESSOR.tokenizer.pad_token_id,
            )
        
        new_ids = out_ids[:, inputs["input_ids"].shape[1]:]
        response = PROCESSOR.batch_decode(new_ids, skip_special_tokens=True)[0]
        
        response = response.strip()
        if "Analysis:" in response:
            response = response.split("Analysis:")[-1].strip()
        
        return {
            "success": True,
            "analysis": response,
            "analysis_type": analysis_type,
            "timestamp": datetime.now().isoformat(),
            "document_name": document_name
        }
        
    except Exception as e:
        print(f"[ANALYSIS] Error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": f"Analysis error: {str(e)}"
            }
        )

@app.get("/")
async def root():
    return {"status": "Enhanced OCR Backend with AI Chat", "model": "olmOCR-7B-0225-preview"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "device": "cuda" if torch.cuda.is_available() else "cpu"}

# NEW: Get available analysis types
@app.get("/analysis-types/")
async def get_analysis_types():
    return {
        "types": [
            {"id": "summary", "name": "Document Summary", "description": "Comprehensive overview of the document"},
            {"id": "key_points", "name": "Key Points", "description": "Main points and important information"},
            {"id": "entities", "name": "Extract Entities", "description": "Names, organizations, dates, amounts"},
            {"id": "dates", "name": "Find Dates", "description": "All temporal information and deadlines"},
            {"id": "questions", "name": "Suggested Questions", "description": "Relevant questions to ask about the document"}
        ]
    }
