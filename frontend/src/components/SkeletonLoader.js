import React from 'react';
import './SkeletonLoader.css';

export const ResultSkeleton = () => (
  <div className="skeleton-result">
    <div className="skeleton-header">
      <div className="skeleton-title"></div>
      <div className="skeleton-actions">
        <div className="skeleton-button"></div>
        <div className="skeleton-button"></div>
      </div>
    </div>
    <div className="skeleton-content">
      <div className="skeleton-lines">
        <div className="skeleton-line"></div>
        <div className="skeleton-line"></div>
        <div className="skeleton-line"></div>
      </div>
    </div>
  </div>
);

export const PreviewSkeleton = () => (
  <div className="skeleton-preview">
    <div className="skeleton-image"></div>
    <div className="skeleton-info">
      <div className="skeleton-filename"></div>
      <div className="skeleton-metadata"></div>
    </div>
  </div>
);
