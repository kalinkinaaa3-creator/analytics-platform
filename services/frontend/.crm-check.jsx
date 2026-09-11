import React from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { CrmWorkspace } from './src/dashboards/crmAnalytics/CrmWorkspace';
createRoot(document.getElementById('root')).render(<BrowserRouter><CrmWorkspace /></BrowserRouter>);
