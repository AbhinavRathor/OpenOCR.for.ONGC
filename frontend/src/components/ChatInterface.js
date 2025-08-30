import React, { useState, useRef, useEffect, useCallback } from 'react';
import { 
  Send, 
  Bot, 
  User, 
  Sparkles,
  Copy,
  RotateCcw,
  X
} from 'lucide-react';
import './ChatInterface.css';

const ChatInterface = ({ extractedText, isVisible, onClose, documentName = "" }) => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Auto-analysis when document is loaded
  const performAutoAnalysis = useCallback(async () => {
    if (!extractedText) return;
    
    try {
      console.log('[Chat] Starting auto-analysis...');
      const formData = new FormData();
      formData.append('extracted_text', extractedText);
      formData.append('document_name', documentName);
      formData.append('analysis_type', 'summary');

      const response = await fetch('http://localhost:8000/analyze/', {
        method: 'POST',
        body: formData
      });

      console.log('[Chat] Auto-analysis response status:', response.status);
      const result = await response.json();
      console.log('[Chat] Auto-analysis result:', result);
      
      if (result.success) {
        const autoMessage = {
          id: Date.now() + 1,
          sender: 'ai',
          text: `📄 **Quick Analysis**:\n\n${result.analysis}`,
          timestamp: new Date()
        };
        setMessages(prev => [...prev, autoMessage]);
      }
    } catch (error) {
      console.error('Auto-analysis error:', error);
    }
  }, [extractedText, documentName]);

  // Initialize chat with welcome message and auto-analysis
  useEffect(() => {
    if (isVisible && extractedText && messages.length === 0) {
      console.log('[Chat] Initializing chat interface...');
      setMessages([{
        id: Date.now(),
        sender: 'ai',
        text: `Hi! I've analyzed your document content. I can help you with summaries, explanations, questions, or any analysis of the extracted text. What would you like to know?`,
        timestamp: new Date()
      }]);
      
      // Auto-generate initial analysis
      performAutoAnalysis();
    }
  }, [isVisible, extractedText, messages.length, performAutoAnalysis]);

  // Updated sendMessage function that connects to your backend
  const sendMessage = async (message, extractedTextContent = null) => {
    if (!message.trim()) return;

    const userMessage = {
      id: Date.now(),
      sender: 'user',
      text: message.trim(),
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    setIsLoading(true);

    try {
      console.log('[Chat] Sending message to backend:', message);
      const formData = new FormData();
      formData.append('message', message);
      formData.append('extracted_text', extractedTextContent || extractedText || '');
      formData.append('document_name', documentName);
      
      // Convert messages to the format expected by backend
      const conversationHistory = messages.map(msg => ({
        role: msg.sender === 'user' ? 'user' : 'assistant',
        content: msg.text
      }));
      formData.append('conversation_history', JSON.stringify(conversationHistory));

      const response = await fetch('http://localhost:8000/chat/', {
        method: 'POST',
        body: formData
      });

      console.log('[Chat] Response status:', response.status);
      const result = await response.json();
      console.log('[Chat] Response result:', result);
      
      if (result.success) {
        const aiMessage = {
          id: Date.now() + 1,
          sender: 'ai',
          text: result.response,
          timestamp: new Date()
        };
        setMessages(prev => [...prev, aiMessage]);
      } else {
        throw new Error(result.error || 'Chat request failed');
      }
    } catch (error) {
      console.error('Chat error:', error);
      const errorMessage = {
        id: Date.now() + 1,
        sender: 'ai',
        text: "I'm experiencing some technical difficulties connecting to the AI service. Please check if the backend server is running and try again.",
        timestamp: new Date()
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSend = async () => {
    if (!input.trim()) return;
    const message = input.trim();
    setInput('');
    await sendMessage(message);
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const copyMessage = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch (error) {
      console.error('Copy failed:', error);
    }
  };

  const clearChat = () => {
    setMessages([]);
    // Reinitialize with welcome message
    if (extractedText) {
      setMessages([{
        id: Date.now(),
        sender: 'ai',
        text: `Hi! I've analyzed your document content. I can help you with summaries, explanations, questions, or any analysis of the extracted text. What would you like to know?`,
        timestamp: new Date()
      }]);
    }
  };

  // Quick action buttons for common requests
  const quickActions = [
    { label: "Summarize Document", prompt: "Please provide a comprehensive summary of this document." },
    { label: "Key Points", prompt: "What are the main key points or important information in this document?" },
    { label: "Find Dates", prompt: "Extract all dates mentioned in this document." },
    { label: "Find Numbers", prompt: "List all important numbers, amounts, or quantities mentioned." },
    { label: "Ask Questions", prompt: "What questions can I ask about this document?" }
  ];

  const handleQuickAction = (prompt) => {
    setInput(prompt);
  };

  if (!isVisible) return null;

  return (
    <div className="chat-interface">
      <div className="chat-header">
        <div className="chat-title">
          <Sparkles size={20} />
          <h3>AI Document Assistant</h3>
          {documentName && <span className="document-name">{documentName}</span>}
        </div>
        <div className="chat-controls">
          <button onClick={clearChat} className="control-btn" title="Clear chat">
            <RotateCcw size={16} />
          </button>
          <button onClick={onClose} className="control-btn close-btn" title="Close chat">
            <X size={16} />
          </button>
        </div>
      </div>

      <div className="chat-messages">
        {messages.map((message) => (
          <div key={message.id} className={`message ${message.sender}`}>
            <div className="message-avatar">
              {message.sender === 'user' ? <User size={16} /> : <Bot size={16} />}
            </div>
            <div className="message-content">
              <div className="message-bubble">
                <p style={{ whiteSpace: 'pre-wrap' }}>{message.text}</p>
                <button 
                  onClick={() => copyMessage(message.text)}
                  className="copy-message-btn"
                  title="Copy message"
                >
                  <Copy size={12} />
                </button>
              </div>
              <span className="message-time">
                {message.timestamp.toLocaleTimeString([], { 
                  hour: '2-digit', 
                  minute: '2-digit' 
                })}
              </span>
            </div>
          </div>
        ))}
        
        {isLoading && (
          <div className="message ai">
            <div className="message-avatar">
              <Bot size={16} />
            </div>
            <div className="message-content">
              <div className="message-bubble loading">
                <div className="typing-indicator">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              </div>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Quick Actions - show when there are few messages */}
      {messages.length <= 2 && (
        <div className="suggested-questions">
          <p>Quick actions:</p>
          <div className="suggestions">
            {quickActions.map((action, index) => (
              <button
                key={index}
                onClick={() => handleQuickAction(action.prompt)}
                className="suggestion-btn"
                title={action.prompt}
              >
                {action.label}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="chat-input-container">
        <div className="chat-input">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Ask about the document content..."
            disabled={isLoading}
            rows={input.split('\n').length}
            style={{ minHeight: '20px', maxHeight: '100px' }}
          />
          <button 
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="send-btn"
          >
            <Send size={18} />
          </button>
        </div>
        {extractedText && (
          <div className="input-status">
            <span>✅ Document loaded ({extractedText.length} characters)</span>
          </div>
        )}
      </div>
    </div>
  );
};

export default ChatInterface;

