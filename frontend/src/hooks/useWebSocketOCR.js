import { useState } from 'react';

export const useWebSocketOCR = (wsUrl) => {
  const [isProcessing, setIsProcessing] = useState(false);

  const processFileStream = async (file, onPageResult, onProgress) => {
    return new Promise((resolve, reject) => {
      setIsProcessing(true);
      console.log(`[WebSocketOCR] Starting FORCED real-time processing for ${file.name}`);
      
      const ws = new WebSocket(wsUrl);
      let totalPages = 0;
      let processedPages = 0;

      ws.onopen = () => {
        console.log('[WebSocketOCR] Connected for real-time streaming');
        
        // Convert file to base64
        const reader = new FileReader();
        reader.onload = () => {
          const base64Data = reader.result.split(',')[1];
          const request = {
            file_data: base64Data,
            filename: file.name,
            lang: 'eng'
          };
          
          console.log(`[WebSocketOCR] Sending ${file.name} for page-by-page processing`);
          ws.send(JSON.stringify(request));
        };
        reader.readAsDataURL(file);
      };

      ws.onmessage = (event) => {
        try {
          const result = JSON.parse(event.data);
          console.log(`[WebSocketOCR] IMMEDIATE receive: ${result.type} - Page ${result.page || 'N/A'}`);
          
          if (result.type === 'page_start') {
            totalPages = result.total_pages;
            console.log(`[WebSocketOCR] Started processing page ${result.page}/${totalPages}`);
            onProgress({
              totalPages,
              currentPage: result.page,
              percentage: 0
            });
          } else if (result.type === 'page_complete') {
            processedPages++;
            const percentage = (processedPages / totalPages) * 100;
            
            console.log(`[WebSocketOCR] IMMEDIATELY displaying page ${result.page}/${totalPages}`);
            
            // Call page result handler IMMEDIATELY - no delays
            onPageResult({
              pageNumber: result.page,
              extractedText: result.text,
              error: result.error,
              confidence: result.confidence,
              preview: result.preview
            });
            
            // Update progress IMMEDIATELY
            onProgress({
              totalPages,
              currentPage: result.page,
              percentage
            });
            
          } else if (result.type === 'processing_complete') {
            console.log(`[WebSocketOCR] Real-time processing complete for ${file.name}`);
            ws.close();
            resolve();
          } else if (result.type === 'error') {
            console.error(`[WebSocketOCR] Error: ${result.error}`);
            ws.close();
            reject(new Error(result.error));
          }
        } catch (error) {
          console.error('[WebSocketOCR] Parse error:', error);
        }
      };

      ws.onerror = (error) => {
        console.error('[WebSocketOCR] WebSocket error:', error);
        setIsProcessing(false);
        reject(error);
      };

      ws.onclose = () => {
        console.log('[WebSocketOCR] Connection closed');
        setIsProcessing(false);
      };
    });
  };

  return { processFileStream, isProcessing };
};
