// src/App.js
import React, { useState } from "react";
import FileUpload from "./components/FileUpload";
import "./App.css";

import ongcLogo from "./assets/ongcLogo.jpg";

function App() {
  // State for AI Document Assistant
  const [chatVisible, setChatVisible] = useState(false);
  const [currentDocumentText, setCurrentDocumentText] = useState('');
  const [currentDocumentName, setCurrentDocumentName] = useState('');

  // Handler for when OCR processing is complete
  const handleOCRComplete = (ocrResults, fileName) => {
    console.log('[App] OCR Complete:', ocrResults.length, 'pages processed');
    
    // Combine all extracted text from all pages
    const allText = ocrResults
      .filter(page => !page.error && page.extractedText)
      .map(page => `Page ${page.pageNumber}:\n${page.extractedText}`)
      .join('\n\n---\n\n');
    
    if (allText.trim()) {
      setCurrentDocumentText(allText);
      setCurrentDocumentName(fileName || 'Document');
      
      console.log('[App] Document text set for AI Assistant:', allText.length, 'characters');
      console.log('[App] Document name:', fileName);
    }
  };

  return (
    <div className="app-wrapper">
      {/* 🔁 Background Video */}
      <video autoPlay loop muted playsInline className="background-video">
        <source src="video.mp4" type="video/mp4" />
        Your browser does not support the video tag.
      </video>

      {/* 🛡️ Header - CLEAN: No duplicate AI Assistant button */}
      <header className="app-header">
        <div className="header-left">
          <img src={ongcLogo} alt="ONGC logo" className="ongc-logo" />
        </div>
        <div className="header-center">
          <h1>OpenOCR for ONGC</h1>
        </div>
        <div className="header-right">
          {/* REMOVED: Duplicate AI Assistant button - using floating button instead */}
        </div>
      </header>

      {/* 📤 Main Content */}
      <main className="container">
        <FileUpload onOCRComplete={handleOCRComplete} />
      </main>
    </div>
  );
}

export default App;

