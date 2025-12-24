import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import './style.css' // Ensure this file exists, or remove this line if you use Tailwind only

ReactDOM.createRoot(document.getElementById('app')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
