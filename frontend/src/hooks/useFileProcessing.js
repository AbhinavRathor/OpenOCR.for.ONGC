import { useState, useCallback } from 'react';

export const useFileProcessing = () => {
  const [files, setFiles] = useState([]);
  const [currentProcessing, setCurrentProcessing] = useState(null);
  const [pageResults, setPageResults] = useState([]);
  const [processingProgress, setProcessingProgress] = useState({});
  const [globalProcessing, setGlobalProcessing] = useState(false);
  const [processingStage, setProcessingStage] = useState('');
  const [totalPages, setTotalPages] = useState(0);
  const [processedPages, setProcessedPages] = useState(0);

  const resetProcessing = useCallback(() => {
    setFiles([]);
    setPageResults([]);
    setProcessingProgress({});
    setCurrentProcessing(null);
    setGlobalProcessing(false);
    setProcessingStage('');
    setTotalPages(0);
    setProcessedPages(0);
  }, []);

  const updateProgress = useCallback((current, total) => {
    setProcessingProgress(prev => ({
      ...prev,
      current,
      total,
      percentage: Math.round((current / total) * 100)
    }));
  }, []);

  return {
    files,
    setFiles,
    currentProcessing,
    setCurrentProcessing,
    pageResults,
    setPageResults,
    processingProgress,
    setProcessingProgress,
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
  };
};
