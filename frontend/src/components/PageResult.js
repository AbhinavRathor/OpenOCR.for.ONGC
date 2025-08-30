import React, { useState } from 'react';
import { Copy, Download, CheckCircle } from 'lucide-react';

const PageResult = ({ result, isLatest }) => {
  const [copyStatus, setCopyStatus] = useState('idle'); // 'idle', 'copying', 'copied'

  const handleCopy = async () => {
    try {
      setCopyStatus('copying');
      await navigator.clipboard.writeText(result.extractedText);
      setCopyStatus('copied');
      
      // Reset status after 2 seconds
      setTimeout(() => {
        setCopyStatus('idle');
      }, 2000);
    } catch (error) {
      console.error('Copy failed:', error);
      setCopyStatus('idle');
    }
  };

  const handleDownload = () => {
    const blob = new Blob([result.extractedText], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${result.fileName.replace(/\.[^/.]+$/, "")}_page_${result.pageNumber}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className={`page-result ${isLatest ? 'latest-page' : ''}`}>
      {/* CLEAN: Single header with page info - no redundancy */}
      <div className="page-header">
        <div className="page-info">
          <h4>Page {result.pageNumber}</h4>
          <span className="file-name">{result.fileName}</span>
          {result.tokenCount > 0 && (
            <span className="token-count">{result.tokenCount} words processed</span>
          )}
          {result.pageType && (
            <span className="page-type">{result.pageType}</span>
          )}
        </div>
        
        <div className="page-actions">
          <button
            onClick={handleCopy}
            className={`action-btn copy-btn ${copyStatus}`}
            title="Copy text"
            disabled={copyStatus === 'copying' || !result.extractedText || result.extractedText.trim() === ""}
            aria-label={`Copy text from page ${result.pageNumber}`}
          >
            {copyStatus === 'copied' ? (
              <CheckCircle size={14} />
            ) : (
              <Copy size={14} />
            )}
            {copyStatus === 'idle' && 'Copy'}
            {copyStatus === 'copying' && 'Copying...'}
            {copyStatus === 'copied' && 'Copied!'}
          </button>
          
          <button
            onClick={handleDownload}
            className="action-btn download-btn"
            title="Download text file"
            disabled={!result.extractedText || result.extractedText.trim() === ""}
            aria-label={`Download text from page ${result.pageNumber}`}
          >
            <Download size={14} />
            Download
          </button>
        </div>
      </div>

      <div className="page-content">
        {result.error ? (
          <div className="error-content" role="alert">
            <span className="error-icon">⚠️</span>
            <span>Error: {result.error}</span>
          </div>
        ) : (
          <div className="page-content-grid">
            {/* ENHANCED: Larger image preview without redundant text */}
            <div className="page-preview-container">
              {result.preview ? (
                <img
                  src={result.preview}
                  alt={`Page ${result.pageNumber} preview`}
                  className="page-preview-image"
                  loading="lazy"
                />
              ) : (
                <div className="no-preview-placeholder">
                  <div className="placeholder-icon">📄</div>
                  <div className="placeholder-text">
                    <div>No Preview Available</div>
                    <div className="placeholder-filename">Image processing...</div>
                  </div>
                </div>
              )}
            </div>
            
            {/* CLEAN: Simplified text header without redundant page info */}
            <div className="extracted-content">
              <div className="text-header">
                <h5>Extracted Text</h5>
                <div className="text-stats">
                  {result.extractedText ? result.extractedText.split('\n').length : 0} lines | {result.extractedText ? result.extractedText.trim().split(/\s+/).filter(word => word.length > 0).length : 0} words
                </div>
              </div>
              <pre className="extracted-text">{result.extractedText}</pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default PageResult;
