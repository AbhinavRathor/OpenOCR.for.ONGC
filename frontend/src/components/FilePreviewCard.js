import React, { useState, useEffect } from 'react';
import { FileText, Eye, Loader2, CheckCircle, AlertCircle } from 'lucide-react';
import { getPdfThumbnail, getPDFPageCount } from '../utils/pdfUtils';
import './FilePreviewCard.css';

const FilePreviewCard = ({ file }) => {
  const [previewUrl, setPreviewUrl] = useState(null);
  const [showPopup, setShowPopup] = useState(false);
  const [imageLoaded, setImageLoaded] = useState(false);
  const [processingState, setProcessingState] = useState('');
  const [pageCount, setPageCount] = useState(null);

  useEffect(() => {
    let cleanup;
    
    const generatePreview = async () => {
      setProcessingState('loading');
      
      if (file.type === 'application/pdf') {
        const thumbnailUrl = await getPdfThumbnail(file);
        const count = await getPDFPageCount(file);
        setPreviewUrl(thumbnailUrl);
        setPageCount(count);
        setProcessingState('ready');
      } else if (file.type.startsWith('image/')) {
        const url = URL.createObjectURL(file);
        setPreviewUrl(url);
        setProcessingState('ready');
        cleanup = () => URL.revokeObjectURL(url);
      }
    };

    generatePreview();
    return () => cleanup && cleanup();
  }, [file]);

  const handleImageLoad = () => {
    setImageLoaded(true);
  };

  return (
    <div className={`file-preview-card ${processingState}`}>
      <div className="file-preview-content">
        {previewUrl ? (
          <div 
            className="image-preview-container"
            onMouseEnter={() => setShowPopup(true)}
            onMouseLeave={() => setShowPopup(false)}
          >
            <img 
              src={previewUrl} 
              alt={file.name} 
              className={file.type === 'application/pdf' ? 'preview-pdf' : 'preview-image'}
              loading="lazy"
              onLoad={handleImageLoad}
            />
            <div className="image-overlay">
              <Eye size={20} />
              <span>Hover to enlarge</span>
            </div>
            
            {showPopup && imageLoaded && (
              <div className="image-popup-overlay" onClick={() => setShowPopup(false)}>
                <div className="image-popup" onClick={(e) => e.stopPropagation()}>
                  <img 
                    src={previewUrl} 
                    alt={`${file.name} - Enlarged`}
                    className="popup-image"
                  />
                  <div className="popup-info">
                    <span className="popup-filename">{file.name}</span>
                    <span className="popup-size">
                      {(file.size / 1024 / 1024).toFixed(2)} MB
                      {pageCount && ` • ${pageCount} pages`}
                    </span>
                  </div>
                  <button 
                    className="popup-close"
                    onClick={() => setShowPopup(false)}
                    title="Close"
                    aria-label="Close preview"
                  >
                    ×
                  </button>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="pdf-preview-container">
            {processingState === 'loading' ? (
              <Loader2 size={32} className="spinning" />
            ) : (
              <FileText size={48} className="pdf-icon" />
            )}
            <div className="pdf-preview-info">
              <span className="pdf-pages">
                {file?.type === 'application/pdf' ? 'PDF Document' : 'Document'}
                {pageCount && ` • ${pageCount} pages`}
              </span>
              <span className="pdf-size">
                {file ? (file.size / 1024 / 1024).toFixed(2) : '0'} MB
              </span>
            </div>
          </div>
        )}
      </div>
      
      <div className="file-metadata">
        <p className="file-name" title={file?.name}>{file?.name}</p>
        <div className="file-stats">
          <span>Size: {(file.size / 1024 / 1024).toFixed(2)} MB</span>
          <span>Type: {file.type.split('/')[1]?.toUpperCase()}</span>
          {pageCount && <span>Pages: {pageCount}</span>}
          <span>Modified: {new Date(file.lastModified).toLocaleDateString()}</span>
        </div>
        
        {processingState && (
          <div className="processing-badge" role="status">
            {processingState === 'loading' && <Loader2 className="spinning" size={14} />}
            {processingState === 'ready' && <CheckCircle size={14} />}
            {processingState === 'error' && <AlertCircle size={14} />}
            {processingState}
          </div>
        )}
      </div>
    </div>
  );
};

export default FilePreviewCard;
