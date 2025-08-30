import { useState, useCallback } from 'react';
import axios from 'axios';

export const useOCRService = (apiUrl) => {
  const [loading, setLoading] = useState(false);

  const processFile = useCallback(async (file, onProgress) => {
    setLoading(true);
    
    const formData = new FormData();
    formData.append("file", file);
    formData.append("lang", "eng"); // Your backend expects 'lang' not 'language'

    try {
      const response = await axios.post(apiUrl, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        timeout: 300000, // 5 minutes for large files
        onUploadProgress: (progressEvent) => {
          const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          if (onProgress) onProgress(progress);
        }
      });

      // Handle your backend's specific response format
      if (response.data?.success) {
        // Convert your backend format to what frontend expects
        const results = response.data.pages.map((pageData) => ({
          pageNumber: pageData.page,
          text: pageData.text || '',
          extractedText: pageData.text || '',
          tokenCount: pageData.text ? pageData.text.split(/\s+/).length : 0,
          error: pageData.error,
          confidence: null, // Your backend doesn't provide confidence scores
          preview: pageData.preview || null // Include preview image data
        }));

        return results;
      } else {
        throw new Error(response.data?.error || 'Processing failed');
      }
      
    } catch (error) {
      console.error('OCR Service Error:', error);
      if (error.response) {
        throw new Error(`Server error: ${error.response.status} - ${error.response.data?.error || 'Unknown error'}`);
      } else if (error.request) {
        throw new Error('Network error: Could not connect to OCR service');
      } else {
        throw new Error(error.message || 'Unknown processing error');
      }
    } finally {
      setLoading(false);
    }
  }, [apiUrl]);

  return {
    processFile,
    loading
  };
};
