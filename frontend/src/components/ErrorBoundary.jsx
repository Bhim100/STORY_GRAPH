import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
    this.props.onReset?.();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div
          className="dossier-card"
          style={{
            padding: '1.25rem',
            borderLeft: '4px solid #ef4444',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.75rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#f87171' }}>
            <AlertTriangle size={18} />
            <h4 style={{ fontSize: '0.875rem', fontWeight: 600 }}>Panel Rendering Notice</h4>
          </div>
          <p style={{ fontSize: '0.775rem', color: 'var(--text-ivory-secondary)', lineHeight: 1.45 }}>
            An unexpected error occurred while rendering this panel: {this.state.error?.message || 'Unknown error'}
          </p>
          <button
            type="button"
            className="btn"
            onClick={this.handleReset}
            style={{
              alignSelf: 'flex-start',
              fontSize: '0.75rem',
              padding: '0.35rem 0.65rem',
              gap: '0.35rem',
            }}
          >
            <RefreshCw size={12} />
            <span>Retry Panel</span>
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
