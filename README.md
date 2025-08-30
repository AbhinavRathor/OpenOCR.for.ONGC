# Real-Time, Offline Document Intelligence Platform with Embedded AI Analysis
### Vision-Language Model-Based Text Extraction

An advanced OCR system leveraging Vision-Language Models (VLMs) for high-accuracy document text extraction with real-time processing capabilities, built during summer internship at ONGC.

## Team & Acknowledgments

**Mentor:**
- Dr. Santosh Kumar Sahu, Sr. Programming Officer, GEOPIC, ONGC, Dehradun – Thank you for your guidance and support.

**Team Members:**
- Abhinav Singh Rathor
- Kaushik Dutt  
- Sankalp Awasthi

**Acknowledgments:**
- GEOPIC, ONGC, for providing technical infrastructure such as workstation.
- Open-source community, for tools and models.

## Technology Stack & Models

### Note on Model Files

**Large model files (~28GB total) are not included in this repository** due to their large size.

**📋 Model Setup Required:** See [MODELS.md](OCRproject/models/MODELS.md) for detailed download and installation instructions.

**Required Models:**
- olmOCR-7B-0225-preview (~13GB)  
- Qwen2-VL-7B-Instruct (~15GB)

### Vision-Language Models
- **Primary OCR Model**: olmOCR-7B-0225-preview
  - Custom fine-tuned for document layout understanding
  - Optimized for multi-page PDF processing
- **Secondary VLM**: Qwen2-VL-7B-Instruct
  - Enhanced for conversational AI and document Q&A
  - Custom prompt engineering for better text extraction

### Backend Technologies
- FastAPI (Python) - REST API and WebSocket server
- PyTorch & Transformers - Model inference
- pdf2image, PyPDF2 - Document processing
- WebSocket - Real-time streaming

### Frontend Technologies
- React.js - Interactive user interface
- lucide-react - Icon components
- WebSocket client - Real-time updates

## Key Features

### 🚀 Real-Time Processing
- **WebSocket Streaming**: Live page-by-page processing for multi-page documents
- **Progress Tracking**: Visual progress indicators with page counters
- **Instant Results**: See extracted text as each page completes

### 🛡️ Secure Local Deployment
- **Offline Operation**: Models run entirely on local servers without internet dependency
- **Data Privacy**: Sensitive documents never leave the organization's infrastructure
- **Zero Cloud Dependency**: Complete processing pipeline operates offline for maximum security
- **Enterprise Ready**: Designed for deployment on GEOPIC's secure local servers

### 🎯 Advanced OCR Capabilities
- **Vision-Language Models**: Custom-trained models for superior accuracy
- **Layout Awareness**: Preserves document structure and formatting
- **Multi-format Support**: PDF, PNG, JPG, GIF, BMP

### 💡 User Experience
- **Drag & Drop Interface**: Intuitive file upload
- **Side-by-side Layout**: Image preview alongside extracted text
- **Bulk Operations**: Copy all, download all functionality
- **AI Assistant**: Document Q&A capabilities

### 🔧 Technical Excellence
- **Scalable Architecture**: FastAPI backend with React frontend
- **Error Handling**: Graceful fallbacks and error recovery
- **Performance Optimized**: Efficient processing with 300 DPI quality

## System Architecture



The system follows a three-tier architecture:
1. **Frontend (React)**: User interface with real-time updates
2. **Backend (FastAPI)**: API server with WebSocket support
3. **ML Engine**: Custom VLM models for text extraction

## Project Impact & Results

- **Security**: 100% offline operation ensuring sensitive data never leaves local infrastructure
- **Accuracy**: Achieved ≥95% accuracy with significant improvement over traditional OCR methods
- **Speed**: Real-time processing with efficient page-by-page streaming
- **User Experience**: Seamless drag-and-drop interface with Embedded AI assistant for real-time queries based on extracted text.
- **Scalability**: Designed for enterprise deployment at ONGC

## 🎬 Project Demonstrations

To view real-time functionality and user experience of the OCR project, please refer to the following demonstration videos:

**Google Drive Links:**

https://drive.google.com/file/d/1RWx5Tpyfdh6D_6jK4YF1_7i2CsLfrJU_/view?usp=sharing

https://drive.google.com/file/d/18WOW4XNrQtiZyvZz32kqSoxk_OXdFTOc/view?usp=sharing