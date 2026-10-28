import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import {CropThemeProvider} from './CropTheme'
import './styles.css'
import './crop-theme.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><CropThemeProvider><App /></CropThemeProvider></React.StrictMode>,
)
