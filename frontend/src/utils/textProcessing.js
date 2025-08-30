export const parseOCRResponse = (responseData) => {
  try {
    if (responseData?.natural_text) {
      return processExtractedText(responseData.natural_text);
    }

    if (typeof responseData === 'string') {
      if (responseData.trim().startsWith('{') && responseData.trim().endsWith('}')) {
        try {
          const parsed = JSON.parse(responseData);
          const textFields = ['natural_text', 'text', 'content', 'ocr_text', 'extracted_text'];
          for (const field of textFields) {
            if (parsed[field] && typeof parsed[field] === 'string' && parsed[field].trim()) {
              return processExtractedText(parsed[field]);
            }
          }
          return processExtractedText(responseData);
        } catch (jsonError) {
          return processExtractedText(responseData);
        }
      }
      return processExtractedText(responseData);
    }
    
    if (typeof responseData === 'object' && responseData !== null) {
      const textFields = ['natural_text', 'text', 'content', 'ocr_text', 'extracted_text'];
      for (const field of textFields) {
        if (responseData[field] && typeof responseData[field] === 'string' && responseData[field].trim()) {
          return processExtractedText(responseData[field]);
        }
      }
      return processExtractedText(JSON.stringify(responseData));
    }
    
    return responseData || "No text extracted";
  } catch (error) {
    console.error('Response parsing error:', error);
    return responseData || "Parsing error occurred";
  }
};
