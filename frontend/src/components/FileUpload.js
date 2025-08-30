import React, { useState, useEffect, useCallback, lazy, Suspense } from 'react';
import {
  Upload,
  FileText,
  Loader2,
  Eye,
  Clock,
  MessageCircle,
  RotateCcw,
  Copy,
  Download
} from 'lucide-react';
import { useOCRService } from '../hooks/useOCRService';
import { useWebSocketOCR } from '../hooks/useWebSocketOCR';
import { useFileProcessing } from '../hooks/useFileProcessing';
import FilePreviewCard from './FilePreviewCard';
import PageResult from './PageResult';
import './FileUpload.css';

// Lazy load ChatInterface
const ChatInterface = lazy(() => import('./ChatInterface'));

const FileUpload = ({ onOCRComplete }) => {
  const {
    files,
    setFiles,
    currentProcessing,
    setCurrentProcessing,
    pageResults,
    setPageResults,
    processingProgress,
    globalProcessing,
    setGlobalProcessing,
    processingStage,
    setProcessingStage,
    totalPages,
    setTotalPages,
    processedPages,
    setProcessedPages,
    resetProcessing,
    updateProgress
  } = useFileProcessing();

  const apiUrl = process.env.REACT_APP_OCR_API_URL || "http://localhost:8000/upload/";
  const wsUrl = process.env.REACT_APP_OCR_WS_URL || "ws://localhost:8000/ws/upload/";
  const { processFile } = useOCRService(apiUrl);
  const { processFileStream, isProcessing: wsProcessing } = useWebSocketOCR(wsUrl);

  const [showChat, setShowChat] = useState(false);
  const [allExtractedText, setAllExtractedText] = useState('');
  const [currentFileName, setCurrentFileName] = useState('');
  const [useRealTimeProcessing, setUseRealTimeProcessing] = useState(true);
  
  // ADD: State for copy feedback
  const [copyAllStatus, setCopyAllStatus] = useState('idle'); // 'idle', 'copying', 'copied'

  // Update extracted text for chat when results change
  useEffect(() => {
    const combinedText = pageResults
      .filter(result => !result.error && result.extractedText)
      .map(result => `Page ${result.pageNumber} (${result.fileName}):\n${result.extractedText}`)
      .join('\n\n---\n\n');
    setAllExtractedText(combinedText);

    // Trigger parent callback when results are updated and processing is complete
    if (combinedText && !globalProcessing && pageResults.length > 0 && onOCRComplete) {
      const latestFileName = pageResults[pageResults.length - 1]?.fileName || currentFileName;
      console.log('[FileUpload] Triggering onOCRComplete with:', {
        resultsCount: pageResults.length,
        fileName: latestFileName,
        textLength: combinedText.length
      });
      onOCRComplete(pageResults, latestFileName);
    }
  }, [pageResults, globalProcessing, onOCRComplete, currentFileName]);

  // Handle file selection
  const handleFileChange = (e) => {
    const selectedFiles = Array.from(e.target.files);
    setFiles(selectedFiles);
    setPageResults([]);
    setCurrentProcessing(null);
    setAllExtractedText('');
    setCurrentFileName('');
    setShowChat(false);
  };

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    const droppedFiles = Array.from(e.target.files || e.dataTransfer.files);
    setFiles(droppedFiles);
    setPageResults([]);
    setCurrentProcessing(null);
    setAllExtractedText('');
    setCurrentFileName('');
    setShowChat(false);
  }, [setFiles, setPageResults, setCurrentProcessing]);

  const handleDragOver = (e) => e.preventDefault();

  // ENHANCED: Force real-time processing for ALL PDFs regardless of size
  const handleUpload = async () => {
    if (files.length === 0) return;
    
    setGlobalProcessing(true);
    setPageResults([]);
    setShowChat(false);
    
    try {
      for (const [fileIndex, file] of files.entries()) {
        setCurrentFileName(file.name);
        setCurrentProcessing({ fileIndex, fileName: file.name });
        setProcessingStage('processing');
        
        const isPDF = file.type === 'application/pdf';
        
        // FORCE real-time processing for ALL PDFs regardless of size
        if (isPDF && useRealTimeProcessing) {
          try {
            console.log(`[FileUpload] Using FORCED real-time processing for ${file.name}`);
            await processFileStream(
              file,
              (pageResult) => {
                const processedResult = {
                  fileIndex,
                  fileName: file.name,
                  pageNumber: pageResult.pageNumber,
                  extractedText: pageResult.extractedText || '',
                  tokenCount: pageResult.tokenCount || 0,
                  error: pageResult.error || null,
                  processingTime: Date.now(),
                  confidence: pageResult.confidence || null,
                  preview: pageResult.preview || null
                };
                
                console.log(`[FileUpload] IMMEDIATE streaming page ${pageResult.pageNumber} for ${file.name}`);
                setPageResults(prev => [...prev, processedResult]);
              },
              (progress) => {
                console.log(`[FileUpload] Progress update: ${progress.currentPage}/${progress.totalPages} (${progress.percentage}%)`);
                setTotalPages(progress.totalPages);
                setProcessedPages(progress.currentPage);
                updateProgress(progress.percentage, 100);
              }
            );
          } catch (wsError) {
            console.warn('WebSocket processing failed, falling back to standard processing:', wsError);
            await processWithStandardAPI(file, fileIndex);
          }
        } else {
          // Standard HTTP processing for images or when real-time is disabled
          await processWithStandardAPI(file, fileIndex);
        }
      }
    } catch (error) {
      console.error('Processing error:', error);
      const errorResult = {
        fileIndex: 0,
        fileName: files[0]?.name || 'Unknown',
        pageNumber: 1,
        extractedText: "",
        tokenCount: 0,
        error: `Processing failed: ${error.message}`,
        processingTime: Date.now()
      };
      setPageResults(prev => [...prev, errorResult]);
    } finally {
      setCurrentProcessing(null);
      setGlobalProcessing(false);
      setProcessingStage('');
    }
  };

  // Standard API processing function
  const processWithStandardAPI = async (file, fileIndex) => {
    const results = await processFile(file, (progress) => {
      updateProgress(progress, 100);
    });

    if (results && results.length > 0) {
      const processedResults = results.map((pageData, pageIndex) => ({
        fileIndex,
        fileName: file.name,
        pageNumber: pageData.pageNumber || pageIndex + 1,
        extractedText: pageData.text || pageData.extractedText || '',
        tokenCount: pageData.tokenCount || (pageData.text || '').split(/\s+/).length,
        error: pageData.error || null,
        processingTime: Date.now(),
        confidence: pageData.confidence || null,
        preview: pageData.preview || null
      }));

      setPageResults(prev => [...prev, ...processedResults]);
      setTotalPages(results.length);
      setProcessedPages(results.length);
    }
  };

  // Clear all results
  const handleClearAll = () => {
    resetProcessing();
    setAllExtractedText('');
    setCurrentFileName('');
    setShowChat(false);
    setCopyAllStatus('idle'); // Reset copy status
  };

  // ENHANCED: Copy all with "Copied!" feedback
  const handleCopyAll = async () => {
    try {
      setCopyAllStatus('copying');
      
      const allText = pageResults
        .filter(result => !result.error && result.extractedText)
        .map(result => `Page ${result.pageNumber} (${result.fileName}):\n${result.extractedText}`)
        .join('\n\n---\n\n');
      
      await navigator.clipboard.writeText(allText);
      
      setCopyAllStatus('copied');
      console.log('All text copied to clipboard');
      
      // Reset status after 2 seconds
      setTimeout(() => {
        setCopyAllStatus('idle');
      }, 2000);
      
    } catch (error) {
      console.error('Failed to copy text:', error);
      setCopyAllStatus('idle');
    }
  };

  // Download all extracted text as text file
  const handleDownloadAll = () => {
    try {
      const allText = pageResults
        .filter(result => !result.error && result.extractedText)
        .map(result => `Page ${result.pageNumber} (${result.fileName}):\n${result.extractedText}`)
        .join('\n\n---\n\n');
      
      const blob = new Blob([allText], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `extracted_text_${new Date().toISOString().split('T')[0]}.txt`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Failed to download text:', error);
    }
  };

  return (
    <div className="enhanced-ocr-container">
      <div className="upload-panel">
        <div className="section-header">
          <Upload className="section-icon" size={24} />
          <h2>Document Text Extraction</h2>
          <p>Upload PDFs, images, or documents to extract text</p>
        </div>

        <div className="action-controls">
          <div className="processing-options">
            <label className="realtime-toggle">
              <input
                type="checkbox"
                checked={useRealTimeProcessing}
                onChange={(e) => setUseRealTimeProcessing(e.target.checked)}
                disabled={globalProcessing}
              />
              <span className="toggle-text">Real-time processing (PDFs)</span>
            </label>
          </div>
          <button
            onClick={handleClearAll}
            disabled={files.length === 0 && pageResults.length === 0}
            className="clear-btn"
            title="Clear all files and results"
          >
            <RotateCcw size={16} />
            Clear All
          </button>
        </div>

        {/* SINGLE Language Display - Removed duplicate */}
        <div className="language-display">
          <label>OCR Language:</label>
          <span className="language-value">English</span>
        </div>

        <div 
          className="modern-dropzone"
          onDrop={handleDrop}
          onDragOver={handleDragOver}
        >
          <div className="dropzone-content">
            <Upload size={40} className="upload-icon" />
            <h3>Drag & drop your files</h3>
            <p>or</p>
            <label className="file-button">
              Choose Files
              <input
                type="file"
                multiple
                onChange={handleFileChange}
                accept="image/*,application/pdf"
                style={{ display: 'none' }}
              />
            </label>
            <small>Supported: PDF, JPG, PNG, GIF, BMP</small>
          </div>
        </div>

        {files.length > 0 && (
          <div className="preview-container">
            <div className="preview-header">
              <div className="preview-title">
                <h3>Selected Document{files.length !== 1 ? 's' : ''}</h3>
                <span className="file-count">
                  {files.length} file{files.length !== 1 ? 's' : ''} ready for processing
                </span>
              </div>
              {/* REMOVED: Duplicate language info - keeping only file size */}
              <div className="preview-info">
                <span className="info-badge" title="Total size">
                  📁 {(files.reduce((acc, file) => acc + file.size, 0) / (1024 * 1024)).toFixed(2)} MB
                </span>
              </div>
            </div>
            <div className="preview-grid">
              {files.map((file, index) => (
                <FilePreviewCard key={index} file={file} />
              ))}
            </div>
          </div>
        )}

        <button
          className="process-button"
          onClick={handleUpload}
          disabled={files.length === 0 || globalProcessing}
        >
          {globalProcessing ? (
            <>
              <Loader2 size={16} className="spinning" />
              {processingStage === 'uploading' && 'Uploading...'}
              {processingStage === 'processing' && 'Processing with OCR...'}
              {!processingStage && 'Processing...'}
            </>
          ) : (
            <>
              <FileText size={16} />
              Extract Text
            </>
          )}
        </button>

        {currentProcessing && (
          <div className="processing-indicator">
            <div className="processing-header">
              <Clock size={14} />
              <span>Processing: {currentProcessing.fileName}</span>
              {totalPages > 0 && (
                <span className="page-progress">
                  ({processedPages}/{totalPages} pages)
                </span>
              )}
            </div>
            {processingProgress.percentage > 0 && (
              <div className="progress-bar">
                <div 
                  className="progress-fill"
                  style={{ width: `${processingProgress.percentage}%` }}
                />
              </div>
            )}
          </div>
        )}
      </div>

      <div className="results-panel">
        {pageResults.length > 0 ? (
          <>
            <div className="enhanced-results-header">
              <div className="results-title">
                <h2>Extraction Results</h2>
                <div className="results-summary">
                  {pageResults.length} page{pageResults.length !== 1 ? 's' : ''} processed
                </div>
              </div>
              <div className="bulk-actions">
                {/* ENHANCED: Copy All button with "Copied!" feedback */}
                <button
                  onClick={handleCopyAll}
                  className={`bulk-btn copy-all-btn ${copyAllStatus}`}
                  disabled={pageResults.length === 0 || copyAllStatus === 'copying'}
                  title="Copy all extracted text"
                >
                  <Copy size={16} />
                  {copyAllStatus === 'idle' && 'Copy All'}
                  {copyAllStatus === 'copying' && 'Copying...'}
                  {copyAllStatus === 'copied' && 'Copied!'}
                </button>
                <button
                  onClick={handleDownloadAll}
                  className="bulk-btn download-all-btn"
                  disabled={pageResults.length === 0}
                  title="Download all text as file"
                >
                  <Download size={16} />
                  Download All
                </button>
              </div>
            </div>
            <div className="pages-container">
              {pageResults.map((result, index) => (
                <PageResult 
                  key={`${result.fileName}-${result.pageNumber}-${index}`} 
                  result={result} 
                  isLatest={index === pageResults.length - 1 && globalProcessing}
                />
              ))}
            </div>
          </>
        ) : (
          <div className="empty-results">
            <Eye size={48} className="empty-icon" />
            <h3>No results yet</h3>
            <p>Upload documents to see extracted text appear here</p>
          </div>
        )}
      </div>

      {/* CLEAN: Single AI Assistant button without numbering */}
      {pageResults.length > 0 && allExtractedText && (
        <button 
          className="chat-toggle-btn enhanced"
          onClick={() => setShowChat(true)}
          title="Ask AI about the document"
        >
          <MessageCircle size={20} />
          <span>Ask AI Assistant</span>
        </button>
      )}

      <Suspense fallback={<div>Loading chat...</div>}>
        <ChatInterface
          extractedText={allExtractedText}
          documentName={currentFileName}
          isVisible={showChat}
          onClose={() => setShowChat(false)}
        />
      </Suspense>
    </div>
  );
};

export default FileUpload;
