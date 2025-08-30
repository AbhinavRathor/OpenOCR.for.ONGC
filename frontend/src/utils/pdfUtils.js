import * as pdfjsLib from 'pdfjs-dist';

// Configure PDF.js worker to use local file
pdfjsLib.GlobalWorkerOptions.workerSrc = '/pdf.worker.min.js';

export const getPdfThumbnail = async (file, scale = 0.4) => {
  try {
    const data = await file.arrayBuffer();
    const pdf = await pdfjsLib.getDocument({ data }).promise;
    const page = await pdf.getPage(1);
    const viewport = page.getViewport({ scale });
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');

    canvas.width = viewport.width;
    canvas.height = viewport.height;

    await page.render({ canvasContext: ctx, viewport }).promise;
    return canvas.toDataURL();
  } catch (error) {
    console.error('PDF thumbnail generation failed:', error);
    return null;
  }
};

export const getPDFPageCount = async (file) => {
  try {
    const data = await file.arrayBuffer();
    const pdf = await pdfjsLib.getDocument({ data }).promise;
    return pdf.numPages;
  } catch (error) {
    console.error('PDF page count failed:', error);
    return null; // Return null instead of random number
  }
};

export const processExtractedText = (rawText) => {
  if (!rawText) return "";
  
  return rawText
    .split(/[\n\r]+/)
    .map(line => line.trim())
    .filter(line => line.length > 0)
    .join('\n')
    .replace(/([.!?])\s*([A-Z])/g, '$1\n\n$2')
    .replace(/([a-z])\s*([A-Z][a-z]*:)/g, '$1\n\n$2')
    .trim();
};
