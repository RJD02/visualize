import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import TestDiagramPage from './__test__/TestDiagramPage.jsx';
import IconInjectionTestPage from './__test__/IconInjectionTestPage.jsx';

// If running the deterministic test page route, render that page directly to avoid
// App mounting which would replace the test DOM. This keeps the /__test/diagram
// route stable for Cypress and local debugging.
if (typeof window !== 'undefined' && window.location && window.location.pathname === '/__test/diagram') {
    ReactDOM.createRoot(document.getElementById('root')).render(
        <React.StrictMode>
            <TestDiagramPage />
        </React.StrictMode>
    );
} else if (typeof window !== 'undefined' && window.location && window.location.pathname === '/__test/icon-injection') {
    ReactDOM.createRoot(document.getElementById('root')).render(
        <React.StrictMode>
            <IconInjectionTestPage />
        </React.StrictMode>
    );
} else {
    import('./App.jsx').then(({ default: App }) => {
        ReactDOM.createRoot(document.getElementById('root')).render(
            <React.StrictMode>
                <App />
            </React.StrictMode>
        );
    });
}
