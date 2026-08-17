from fastapi import FastAPI, APIRouter, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
import json
import os
from datetime import datetime
from aws_manager_visivel import AWSManagerVisivel
import requests

app = FastAPI(title="AWS Manager Interface")
router = APIRouter()

aws_manager = AWSManagerVisivel()

@router.get("/aws", response_class=HTMLResponse)
async def aws_home(request: Request):

    html_content = """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AWS Manager - Sistema de Integração</title>
        <style>
            :root {
                /* Tema Claro (Padrão) */
                --bg-primary: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
                --bg-secondary: white;
                --bg-card: white;
                --bg-input: white;
                --bg-modal: white;
                --bg-alert: #f8f9fa;
                --bg-scroll: #f1f1f1;
                --bg-scroll-thumb: #c1c1c1;
                --bg-scroll-thumb-hover: #a8a8a8;
                
                --text-primary: #333;
                --text-secondary: #666;
                --text-muted: #6c757d;
                --text-inverse: white;
                
                --accent-primary: #ff6600;
                --accent-primary-hover: #e55c00;
                --accent-secondary: #6c757d;
                --accent-secondary-hover: #5a6268;
                --accent-success: #28a745;
                --accent-success-hover: #218838;
                --accent-danger: #dc3545;
                --accent-danger-hover: #c82333;
                --accent-info: #17a2b8;
                --accent-warning: #ffc107;
                
                --border-primary: #e1e5e9;
                --border-secondary: #e9ecef;
                --border-focus: #ff6600;
                --border-hover: #ff6600;
                
                --shadow-primary: rgba(0,0,0,0.1);
                --shadow-secondary: rgba(0,0,0,0.15);
                --shadow-accent: rgba(255, 102, 0, 0.2);
                --shadow-accent-hover: rgba(255, 102, 0, 0.3);
                
                /* Cores das pastas */
                --pasta-mab: #ff6600;
                --pasta-mcr: #28a745;
                --pasta-descontos: #17a2b8;
                --pasta-renuncias: #6f42c1;
                --pasta-outros: #6c757d;
            }
            
            [data-theme="dark"] {
                /* Tema Escuro */
                --bg-primary: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);
                --bg-secondary: #2d2d2d;
                --bg-card: #2d2d2d;
                --bg-input: #3d3d3d;
                --bg-modal: #2d2d2d;
                --bg-alert: #3d3d3d;
                --bg-scroll: #3d3d3d;
                --bg-scroll-thumb: #666;
                --bg-scroll-thumb-hover: #888;
                
                --text-primary: #ffffff;
                --text-secondary: #cccccc;
                --text-muted: #999999;
                --text-inverse: #1a1a1a;
                
                --accent-primary: #dc3545;
                --accent-primary-hover: #c82333;
                --accent-secondary: #6c757d;
                --accent-secondary-hover: #5a6268;
                --accent-success: #28a745;
                --accent-success-hover: #218838;
                --accent-danger: #ff4444;
                --accent-danger-hover: #ff2222;
                --accent-info: #17a2b8;
                --accent-warning: #ffc107;
                
                --border-primary: #444;
                --border-secondary: #555;
                --border-focus: #dc3545;
                --border-hover: #dc3545;
                
                --shadow-primary: rgba(0,0,0,0.3);
                --shadow-secondary: rgba(0,0,0,0.4);
                --shadow-accent: rgba(220, 53, 69, 0.3);
                --shadow-accent-hover: rgba(220, 53, 69, 0.4);
                
                /* Cores das pastas no tema escuro */
                --pasta-mab: #dc3545;
                --pasta-mcr: #28a745;
                --pasta-descontos: #17a2b8;
                --pasta-renuncias: #6f42c1;
                --pasta-outros: #6c757d;
            }
            
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: var(--bg-primary);
                min-height: 100vh;
                color: var(--text-primary);
                transition: all 0.3s ease;
            }

            .app-nav {
                background: #1f1f1f;
                padding: 10px 20px;
                display: flex;
                gap: 8px;
                align-items: center;
            }

            .app-nav a {
                color: #ccc;
                text-decoration: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: 600;
                font-size: 14px;
            }

            .app-nav a:hover {
                color: #fff;
                background: #333;
            }

            .app-nav a.active {
                color: #fff;
                background: var(--accent-primary);
            }
            
            .container {
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
            }
            
            .header {
                background: var(--bg-card);
                border-radius: 15px;
                padding: 30px;
                margin-bottom: 30px;
                box-shadow: 0 10px 30px var(--shadow-primary);
                text-align: center;
                border-left: 5px solid var(--accent-primary);
                transition: all 0.3s ease;
            }
            
            .header h1 {
                color: var(--text-primary);
                font-size: 2.5em;
                margin-bottom: 10px;
            }
            
            .header p {
                color: var(--text-secondary);
                font-size: 1.1em;
            }
            
            .status-bar {
                background: var(--bg-card);
                border-radius: 10px;
                padding: 20px;
                margin-bottom: 30px;
                box-shadow: 0 5px 15px var(--shadow-primary);
                display: flex;
                justify-content: space-between;
                align-items: center;
                transition: all 0.3s ease;
            }
            
            .status-indicator {
                display: flex;
                align-items: center;
                gap: 10px;
            }
            
            .status-dot {
                width: 12px;
                height: 12px;
                border-radius: 50%;
                background: #ccc;
            }
            
            .status-dot.connected {
                background: #28a745;
            }
            
            .status-dot.disconnected {
                background: #dc3545;
            }
            
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
                gap: 30px;
                margin-bottom: 30px;
            }
            
            .card {
                background: var(--bg-card);
                border-radius: 15px;
                padding: 25px;
                box-shadow: 0 10px 30px var(--shadow-primary);
                transition: all 0.3s ease;
                border-top: 4px solid var(--accent-primary);
                border: 1px solid var(--border-secondary);
            }
            
            .card:hover {
                transform: translateY(-5px);
                box-shadow: 0 15px 40px var(--shadow-secondary);
                border-color: var(--accent-primary);
            }
            
            .card h3 {
                color: var(--text-primary);
                margin-bottom: 20px;
                font-size: 1.3em;
                display: flex;
                align-items: center;
                gap: 10px;
            }
            
            .card-icon {
                width: 24px;
                height: 24px;
                background: var(--accent-primary);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-inverse);
                font-size: 12px;
                font-weight: bold;
            }
            
            .form-group {
                margin-bottom: 20px;
            }
            
            .form-group label {
                display: block;
                margin-bottom: 8px;
                color: var(--text-secondary);
                font-weight: 500;
            }
            
            .form-group input, .form-group select, .form-group textarea {
                width: 100%;
                padding: 12px;
                border: 2px solid var(--border-primary);
                border-radius: 8px;
                font-size: 14px;
                transition: all 0.3s ease;
                background: var(--bg-input);
                color: var(--text-primary);
            }
            
            .form-group input:focus, .form-group select:focus, .form-group textarea:focus {
                outline: none;
                border-color: var(--border-focus);
                box-shadow: 0 0 0 3px var(--shadow-accent);
                transform: translateY(-1px);
            }
            
            .form-group input:hover, .form-group select:hover, .form-group textarea:hover {
                border-color: var(--border-hover);
            }
            
            .btn {
                background: var(--accent-primary);
                color: var(--text-inverse);
                border: none;
                padding: 12px 25px;
                border-radius: 8px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 500;
                transition: all 0.3s ease;
                width: 100%;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
                text-decoration: none;
                box-shadow: 0 2px 4px var(--shadow-accent);
            }
            
            .btn:hover {
                background: var(--accent-primary-hover);
                transform: translateY(-1px);
                box-shadow: 0 4px 8px var(--shadow-accent-hover);
            }
            
            .btn:active {
                transform: translateY(0);
                box-shadow: 0 2px 4px var(--shadow-accent);
            }
            
            .btn-secondary {
                background: var(--accent-secondary);
                box-shadow: 0 2px 4px var(--shadow-primary);
            }
            
            .btn-secondary:hover {
                background: var(--accent-secondary-hover);
                box-shadow: 0 4px 8px var(--shadow-secondary);
            }
            
            .btn-success {
                background: var(--accent-success);
                box-shadow: 0 2px 4px var(--shadow-primary);
            }
            
            .btn-success:hover {
                background: var(--accent-success-hover);
                box-shadow: 0 4px 8px var(--shadow-secondary);
            }
            
            .btn-danger {
                background: var(--accent-danger);
                box-shadow: 0 2px 4px var(--shadow-primary);
            }
            
            .btn-danger:hover {
                background: var(--accent-danger-hover);
                box-shadow: 0 4px 8px var(--shadow-secondary);
            }
            
            .data-display {
                background: var(--bg-card);
                border-radius: 15px;
                padding: 25px;
                box-shadow: 0 10px 30px var(--shadow-primary);
                margin-bottom: 30px;
                transition: all 0.3s ease;
            }
            
            .data-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
                padding-bottom: 15px;
                border-bottom: 2px solid var(--border-secondary);
            }
            
            .data-stats {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: 15px;
                margin-bottom: 20px;
            }
            
            .stat-item {
                background: var(--bg-alert);
                padding: 15px;
                border-radius: 8px;
                text-align: center;
            }
            
            .stat-value {
                font-size: 1.5em;
                font-weight: bold;
                color: var(--accent-primary);
            }
            
            .stat-label {
                color: var(--text-secondary);
                font-size: 0.9em;
                margin-top: 5px;
            }
            
            .json-viewer {
                background: var(--bg-alert);
                border: 1px solid var(--border-primary);
                border-radius: 8px;
                padding: 15px;
                max-height: 400px;
                overflow-y: auto;
                font-family: 'Courier New', monospace;
                font-size: 12px;
                white-space: pre-wrap;
                color: var(--text-primary);
            }
            

            
            .pastas-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
                gap: 25px;
            }
            
            .pasta-card {
                background: var(--bg-card);
                border: 2px solid var(--border-primary);
                border-radius: 15px;
                padding: 25px;
                transition: all 0.3s ease;
                position: relative;
                overflow: hidden;
            }
            
            .pasta-card::before {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 4px;
                background: var(--pasta-cor, var(--accent-secondary));
            }
            
            .pasta-card:hover {
                border-color: var(--pasta-cor, var(--accent-secondary));
                box-shadow: 0 8px 25px var(--shadow-secondary);
                transform: translateY(-2px);
            }
            
            .pasta-card.has-scroll {
                position: relative;
            }
            
            .pasta-card.has-scroll::after {
                content: '';
                position: absolute;
                bottom: 0;
                left: 0;
                right: 0;
                height: 20px;
                background: linear-gradient(transparent, var(--bg-card));
                pointer-events: none;
                border-radius: 0 0 15px 15px;
            }
            
            .pasta-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
                padding-bottom: 15px;
                border-bottom: 1px solid var(--border-secondary);
            }
            
            .pasta-nome {
                font-size: 1.4em;
                font-weight: bold;
                color: var(--text-primary);
                display: flex;
                align-items: center;
                gap: 10px;
            }
            
            .pasta-stats {
                display: flex;
                gap: 15px;
                align-items: center;
            }
            
            .pasta-count {
                background: var(--pasta-cor, var(--accent-secondary));
                color: var(--text-inverse);
                padding: 5px 12px;
                border-radius: 20px;
                font-size: 0.9em;
                font-weight: bold;
            }
            
            .pasta-acoes {
                display: flex;
                gap: 8px;
            }
            
            .arquivos-pasta {
                display: grid;
                gap: 15px;
                max-height: 400px;
                overflow-y: auto;
                padding-right: 10px;
            }
            
            .arquivos-pasta::-webkit-scrollbar {
                width: 8px;
            }
            
            .arquivos-pasta::-webkit-scrollbar-track {
                background: var(--bg-scroll);
                border-radius: 4px;
            }
            
            .arquivos-pasta::-webkit-scrollbar-thumb {
                background: var(--bg-scroll-thumb);
                border-radius: 4px;
            }
            
            .arquivos-pasta::-webkit-scrollbar-thumb:hover {
                background: var(--bg-scroll-thumb-hover);
            }
            
            .arquivo-pasta-item {
                background: var(--bg-alert);
                border: 1px solid var(--border-secondary);
                border-radius: 8px;
                padding: 15px;
                transition: all 0.2s ease;
            }
            
            .arquivo-pasta-item:hover {
                border-color: var(--pasta-cor, var(--accent-secondary));
                background: var(--bg-card);
            }
            
            .arquivo-pasta-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 10px;
            }
            
            .arquivo-pasta-nome {
                font-weight: 500;
                color: var(--text-primary);
            }
            
            .arquivo-pasta-acoes {
                display: flex;
                gap: 5px;
            }
            
            .btn-xs {
                padding: 6px 10px;
                font-size: 11px;
                border-radius: 6px;
                width: auto;
                border: none;
                cursor: pointer;
                transition: all 0.2s ease;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 4px;
                min-width: 32px;
                height: 28px;
            }
            
            .btn-xs:hover {
                transform: translateY(-1px);
                box-shadow: 0 2px 8px rgba(0,0,0,0.15);
            }
            
            .btn-xs:active {
                transform: translateY(0);
            }
            
            .sem-pasta-section {
                background: var(--bg-alert);
                border: 2px dashed var(--border-secondary);
                border-radius: 15px;
                padding: 25px;
                text-align: center;
            }
            
            .sem-pasta-section .arquivos-pasta {
                max-height: 300px;
                overflow-y: auto;
                padding-right: 10px;
                text-align: left;
            }
            
            .sem-pasta-section h4 {
                color: var(--text-muted);
                margin-bottom: 15px;
            }
            
            .sem-pasta-section.has-scroll {
                position: relative;
            }
            
            .sem-pasta-section.has-scroll::after {
                content: '';
                position: absolute;
                bottom: 0;
                left: 0;
                right: 0;
                height: 20px;
                background: linear-gradient(transparent, rgba(248,249,250,0.9));
                pointer-events: none;
                border-radius: 0 0 15px 15px;
            }
            
            .filtros-container {
                border: 1px solid var(--border-secondary);
                transition: all 0.3s ease;
            }
            
            .filtros-container:hover {
                border-color: var(--border-hover);
                box-shadow: 0 2px 8px var(--shadow-accent);
            }
            
            .filtros-container select,
            .filtros-container input[type="date"] {
                transition: border-color 0.3s ease;
            }
            
            .filtros-container select:focus,
            .filtros-container input[type="date"]:focus {
                border-color: var(--border-focus);
                outline: none;
            }
            

            
            .modal {
                display: none;
                position: fixed;
                z-index: 1000;
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(0,0,0,0.5);
            }
            
            .modal-content {
                background-color: var(--bg-modal);
                margin: 5% auto;
                padding: 30px;
                border-radius: 15px;
                width: 80%;
                max-width: 800px;
                max-height: 80vh;
                overflow-y: auto;
                box-shadow: 0 20px 60px var(--shadow-secondary);
            }
            
            .close {
                color: var(--text-muted);
                float: right;
                font-size: 28px;
                font-weight: bold;
                cursor: pointer;
            }
            
            .close:hover {
                color: var(--text-primary);
            }
            
            .alert {
                padding: 15px;
                border-radius: 8px;
                margin-bottom: 20px;
            }
            
            .alert-success {
                background: #d4edda;
                color: #155724;
                border: 1px solid #c3e6cb;
            }
            
            .alert-error {
                background: #f8d7da;
                color: #721c24;
                border: 1px solid #f5c6cb;
            }
            
            .alert-info {
                background: #d1ecf1;
                color: #0c5460;
                border: 1px solid #bee5eb;
            }
            
            .file-upload {
                border: 2px dashed var(--accent-primary);
                border-radius: 8px;
                padding: 30px;
                text-align: center;
                background: var(--bg-alert);
                transition: background 0.3s ease;
            }
            
            .file-upload:hover {
                background: var(--bg-card);
            }
            
            .file-upload input[type="file"] {
                display: none;
            }
            
            .file-upload label {
                cursor: pointer;
                color: var(--accent-primary);
                font-weight: 500;
            }
            
            .loading {
                display: none;
                text-align: center;
                padding: 20px;
            }
            
            .spinner {
                border: 3px solid var(--border-secondary);
                border-top: 3px solid var(--accent-primary);
                border-radius: 50%;
                width: 30px;
                height: 30px;
                animation: spin 1s linear infinite;
                margin: 0 auto 10px;
            }
            
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            
            /* Theme Switch */
            .theme-switch-container {
                display: flex;
                align-items: center;
            }
            
            .theme-toggle {
                background: var(--bg-input);
                border: 2px solid var(--border-primary);
                border-radius: 50px;
                width: 50px;
                height: 50px;
                display: flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                transition: all 0.3s ease;
                font-size: 20px;
                box-shadow: 0 2px 8px var(--shadow-primary);
            }
            
            .theme-toggle:hover {
                border-color: var(--border-hover);
                box-shadow: 0 4px 12px var(--shadow-secondary);
                transform: translateY(-2px);
            }
            
            .theme-toggle:active {
                transform: translateY(0);
            }
            
            @media (max-width: 768px) {
                .grid {
                    grid-template-columns: 1fr;
                }
                
                .status-bar {
                    flex-direction: column;
                    gap: 15px;
                }
                
                .data-stats {
                    grid-template-columns: repeat(2, 1fr);
                }
                
                .header {
                    text-align: center;
                }
                
                .header > div {
                    flex-direction: column;
                    gap: 20px;
                }
            }
        </style>
    </head>
    <body>
        <nav class="app-nav">
            <a href="/">Processamento</a>
            <a href="/aws" class="active">AWS / S3</a>
        </nav>
        <div class="container">
            <!-- Header -->
            <div class="header">
                <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
                    <div>
                        <h1>AWS Manager</h1>
                        <p>Sistema de Integração e Gerenciamento de Dados</p>
                    </div>
                    <div class="theme-switch-container">
                        <button id="themeToggle" class="theme-toggle" onclick="toggleTheme()" title="Alternar tema">
                            <span id="themeIcon">🌙</span>
                        </button>
                    </div>
                </div>
            </div>
            
            <!-- Status Bar -->
            <div class="status-bar">
                <div class="status-indicator">
                    <div class="status-dot" id="statusDot"></div>
                    <span id="statusText">Verificando conexão...</span>
                </div>
                <button class="btn btn-secondary" onclick="testarConexao()">🔄 Testar Conexão</button>
            </div>
            
            <!-- Alert Area -->
            <div id="alertArea"></div>
            
            <!-- Main Grid (Explorador AWS) -->
            <div class="grid">
                <div class="card" style="grid-column: 1 / -1;">
                    <h3><div class="card-icon">🌐</div>Consultar arquivos na API (GET)</h3>
                    <p style="color:#666; margin-bottom: 10px;">Lista o status dos arquivos por data em <code>/prod/listar-arquivos</code>.</p>
                    <div class="form-group">
                        <label for="dataConsultaApi">Data (dd/mm/aaaa)</label>
                        <input id="dataConsultaApi" placeholder="11/03/2026" value="11/03/2026" />
                    </div>
                    <div style="display:flex; gap:10px; flex-wrap:wrap;">
                        <button class="btn" onclick="consultarArquivosApi()">🔍 Consultar todos</button>
                        <button class="btn btn-secondary" onclick="listarAwsDireto('MAB')">MAB</button>
                        <button class="btn btn-secondary" onclick="listarAwsDireto('MCR')">MCR</button>
                        <button class="btn btn-secondary" onclick="listarAwsDireto('DESCONTOS')">DESCONTOS</button>
                        <button class="btn btn-secondary" onclick="listarAwsDireto('RENUNCIAS')">RENUNCIAS</button>
                    </div>
                </div>
                <div class="card" style="grid-column: 1 / -1;">
                    <h3><div class="card-icon">📤</div>Enviar JSON (POST upload-arquivos)</h3>
                    <p style="color:#666; margin-bottom: 10px;">Envio com <code>content</code> como objeto JSON (não string). Endpoint: <code>/prod/upload-arquivos</code>.</p>
                        <div class="form-group">
                        <label for="tipoPut">Tipo</label>
                        <select id="tipoPut">
                            <option value="MAB">MAB</option>
                            <option value="MCR">MCR</option>
                            <option value="DESCONTOS">Descontos</option>
                            <option value="RENUNCIAS">Renuncias</option>
                            <option value="OUTROS">OUTROS</option>
                            </select>
                        </div>
                        <div class="form-group">
                        <label for="nomePut">Nome do arquivo (.json)</label>
                        <input id="nomePut" placeholder="Ex.: MAB_29-07-2025_20250811_080749.json" />
                        <small id="previewPath" style="display:block; color:#666; margin-top:6px;"></small>
                        </div>
                        <div class="form-group">
                        <label>Conteúdo JSON</label>
                        <div class="file-upload" style="margin-bottom:10px;">
                            <input type="file" id="filePut" accept=".json">
                            <label for="filePut">📁 Selecionar arquivo JSON (opcional)</label>
                        </div>
                            <div id="putFileInfo" class="alert alert-info" style="display:none; margin-bottom:10px;"></div>
                        <textarea id="jsonPut" rows="12" placeholder='Cole aqui o JSON ou selecione um arquivo acima'></textarea>
                        </div>
                    <div style="display:flex; gap:10px;">
                        <button class="btn btn-success" id="btnEnviarPut">📤 Enviar</button>
                        <button class="btn btn-secondary" id="btnLimparPut">🧹 Limpar</button>
                </div>
                </div>
            </div>
            
            <!-- Data Display -->
            <div class="data-display" id="dataDisplay" style="display: none;">
                <div class="data-header">
                    <h3>📊 Dados Armazenados</h3>
                    <button class="btn btn-secondary" onclick="fecharDados()">✕ Fechar</button>
                </div>
                <div id="dataStats" class="data-stats"></div>
                <div id="dataContent" class="json-viewer"></div>
            </div>
            

            
            <!-- Lista Remota (espelho S3) -->
            <div class="data-display" id="awsListDisplay" style="display: none;">
                <div class="data-header">
                    <h3>🌐 Arquivos na AWS: <span id="awsListTitulo"></span></h3>
                    <button class="btn btn-secondary" onclick="fecharAwsList()">✕ Fechar</button>
                </div>
                <div id="awsListContent"></div>
            </div>
            
            <!-- Loading -->
            <div class="loading" id="loading">
                <div class="spinner"></div>
                <p>Processando...</p>
            </div>
        </div>
        

        
        <!-- Modal para detalhes -->
        <div id="detailModal" class="modal">
            <div class="modal-content">
                <span class="close" onclick="fecharModal()">&times;</span>
                <h3 id="modalTitle">Detalhes dos Dados</h3>
                <div id="modalContent"></div>
            </div>
        </div>
        
        <!-- Modal para criar pasta -->
        <div id="criarPastaModal" class="modal">
            <div class="modal-content">
                <span class="close" onclick="fecharCriarPasta()">&times;</span>
                <h3>➕ Criar Nova Pasta</h3>
                <div style="margin-bottom: 20px;">
                    <label for="nomePasta" style="display: block; margin-bottom: 8px; font-weight: 500;">Nome da Pasta:</label>
                    <input type="text" id="nomePasta" placeholder="Ex: Relatórios Mensais" style="width: 100%; padding: 10px; border: 2px solid #e1e5e9; border-radius: 8px;">
                </div>
                <div style="margin-bottom: 20px;">
                    <label for="corPasta" style="display: block; margin-bottom: 8px; font-weight: 500;">Cor da Pasta:</label>
                    <input type="color" id="corPasta" value="#6c757d" style="width: 100%; height: 40px; border: 2px solid #e1e5e9; border-radius: 8px;">
                </div>
                <div style="text-align: right;">
                    <button class="btn btn-secondary" onclick="fecharCriarPasta()">❌ Cancelar</button>
                    <button class="btn" onclick="criarPasta()" style="margin-left: 10px;">✅ Criar Pasta</button>
                </div>
            </div>
        </div>
        
        <!-- Modal para editar pasta -->
        <div id="editarPastaModal" class="modal">
            <div class="modal-content">
                <span class="close" onclick="fecharEditarPasta()">&times;</span>
                <h3>✏️ Editar Pasta</h3>
                <div style="margin-bottom: 20px;">
                    <label for="nomePastaEdit" style="display: block; margin-bottom: 8px; font-weight: 500;">Nome da Pasta:</label>
                    <input type="text" id="nomePastaEdit" placeholder="Ex: Relatórios Mensais" style="width: 100%; padding: 10px; border: 2px solid #e1e5e9; border-radius: 8px;">
                </div>
                <div style="margin-bottom: 20px;">
                    <label for="corPastaEdit" style="display: block; margin-bottom: 8px; font-weight: 500;">Cor da Pasta:</label>
                    <input type="color" id="corPastaEdit" value="#6c757d" style="width: 100%; height: 40px; border: 2px solid #e1e5e9; border-radius: 8px;">
                </div>
                <div style="text-align: right;">
                    <button class="btn btn-secondary" onclick="fecharEditarPasta()">❌ Cancelar</button>
                    <button class="btn" onclick="salvarEdicaoPasta()" style="margin-left: 10px;">✅ Salvar</button>
                </div>
            </div>
        </div>
        
        <!-- Modal para mover arquivo -->
        <div id="moverArquivoModal" class="modal">
            <div class="modal-content">
                <span class="close" onclick="fecharMoverArquivo()">&times;</span>
                <h3>📁 Mover Arquivo</h3>
                <div style="margin-bottom: 20px;">
                    <p><strong>Arquivo:</strong> <span id="arquivoParaMover"></span></p>
                    <p><strong>Pasta Atual:</strong> <span id="pastaAtual"></span></p>
                </div>
                <div style="margin-bottom: 20px;">
                    <label for="pastaDestino" style="display: block; margin-bottom: 8px; font-weight: 500;">Mover para:</label>
                    <select id="pastaDestino" style="width: 100%; padding: 10px; border: 2px solid #e1e5e9; border-radius: 8px;">
                        <option value="">Selecione a pasta de destino...</option>
                    </select>
                </div>
                <div style="text-align: right;">
                    <button class="btn btn-secondary" onclick="fecharMoverArquivo()">❌ Cancelar</button>
                    <button class="btn" onclick="confirmarMoverArquivo()" style="margin-left: 10px;">✅ Mover</button>
                </div>
            </div>
        </div>
        
        <script>
            // Variáveis globais
            let arquivoSelecionado = null;
            let dadosCompletos = null; // Armazena todos os dados sem filtro
            let filtrosAtivos = {
                periodo: 'todos',
                dataInicio: null,
                dataFim: null
            };
            
            // ============================================
            // FUNÇÕES PUT - DEFINIDAS PRIMEIRO para evitar erros
            // ============================================
            
            // Helpers PUT dinâmico - tornando acessíveis globalmente
            window.previewPutPath = function previewPutPath() {
                const tipoEl = document.getElementById('tipoPut');
                const nomeEl = document.getElementById('nomePut');
                const previewEl = document.getElementById('previewPath');
                
                if (!tipoEl || !nomeEl || !previewEl) return;
                
                const tipo = tipoEl.value || 'MAB';
                const nome = (nomeEl.value || '').trim();
                const url = `https://v60yr1ma4f.execute-api.sa-east-1.amazonaws.com/prod/upload-arquivos`;
                previewEl.textContent = nome ? `Endpoint: ${url} | file_name: ${nome}` : `Endpoint: ${url}`;
            };

            window.enviarPutRemoto = async function enviarPutRemoto() {
                try {
                    const tipoEl = document.getElementById('tipoPut');
                    const nomeEl = document.getElementById('nomePut');
                    const jsonEl = document.getElementById('jsonPut');
                    
                    if (!tipoEl || !nomeEl || !jsonEl) {
                        const elementosFaltando = [];
                        if (!tipoEl) elementosFaltando.push('tipoPut');
                        if (!nomeEl) elementosFaltando.push('nomePut');
                        if (!jsonEl) elementosFaltando.push('jsonPut');
                        mostrarAlerta(`❌ Erro: Elementos não encontrados: ${elementosFaltando.join(', ')}. Recarregue a página.`, 'error');
                        return;
                    }
                
                    const tipo = (tipoEl?.value || '').trim();
                    const nome = (nomeEl?.value || '').trim();
                    const conteudo = (jsonEl?.value || '').trim();
                    
                    if (!tipo || !nome) { 
                        mostrarAlerta('Informe tipo e nome do arquivo', 'error'); 
                        return; 
                    }
                    if (!conteudo) { 
                        mostrarAlerta('Informe o JSON no campo de conteúdo', 'error'); 
                        return; 
                    }
                    
                    let dados;
                    try { 
                        dados = JSON.parse(conteudo); 
                    } catch (e) { 
                        mostrarAlerta(`JSON inválido: ${e.message}`, 'error'); 
                        return; 
                    }
                    
                    // Validar que não é o arquivo de teste
                    if (dados.resultados && dados.resultados.length > 0) {
                        const primeiroResultado = dados.resultados[0];
                        if (primeiroResultado.banco === 'teste' || primeiroResultado.banco === 'teste_banco') {
                            mostrarAlerta('⚠️ AVISO: Parece que você está enviando um arquivo de teste. Verifique o conteúdo antes de enviar.', 'error');
                            return;
                        }
                    }
                    
                    mostrarLoading(true);
                    try {
                        const res = await fetch('/api/put-remoto', { 
                            method: 'POST', 
                            headers: { 'Content-Type': 'application/json' }, 
                            body: JSON.stringify({ tipo, nome, dados }) 
                        });
                        const out = await res.json();
                        if (out.sucesso) {
                            const pathInfo = out.path ? ` | path: ${out.path}` : '';
                            mostrarAlerta(`✅ Upload realizado (${out.status_code})${pathInfo}`, 'success');
                            if (window.previewPutPath) window.previewPutPath();
                            // Limpar campos após sucesso
                            nomeEl.value = '';
                            jsonEl.value = '';
                            const filePutEl = document.getElementById('filePut');
                            if (filePutEl) filePutEl.value = '';
                            // Recarregar estrutura de pastas automaticamente após 1 segundo
                            setTimeout(() => {
                                if (typeof listarPorPastas === 'function') {
                                    listarPorPastas();
                                }
                            }, 1000);
                        } else {
                            mostrarAlerta(`❌ Erro: ${out.mensagem}`, 'error');
                        }
                    } catch (e) {
                        mostrarAlerta(`❌ Erro: ${e.message}`, 'error');
                    }
                    mostrarLoading(false);
                } catch (e) {
                    mostrarAlerta(`❌ Erro: ${e.message}`, 'error');
                    mostrarLoading(false);
                }
            };

            window.limparPutRemoto = function limparPutRemoto() {
                const nomeEl = document.getElementById('nomePut');
                const jsonEl = document.getElementById('jsonPut');
                const fileEl = document.getElementById('filePut');
                const previewEl = document.getElementById('previewPath');
                
                if (nomeEl) nomeEl.value = '';
                if (jsonEl) jsonEl.value = '';
                if (fileEl) fileEl.value = '';
                if (previewEl) previewEl.textContent = '';
            };
            
            // ============================================
            // FIM DAS FUNÇÕES PUT
            // ============================================
            
            // Inicialização
            document.addEventListener('DOMContentLoaded', function() {
                testarConexao();
                configurarEventos();
                inicializarTema();
            });
            
            function configurarEventos() {
                // PUT dinâmico: carregar arquivo opcional
                const filePutEl = document.getElementById('filePut');
                if (filePutEl) {
                    filePutEl.addEventListener('change', async function(e) {
                        const file = e?.target?.files?.[0];
                        if (!file) return;
                        try {
                            const text = await file.text();
                            const jsonEl = document.getElementById('jsonPut');
                            if (jsonEl) jsonEl.value = text;
                            // Confirmação visual
                            const info = document.getElementById('putFileInfo');
                            if (info) {
                                info.style.display = 'block';
                                info.innerHTML = `<strong>Arquivo carregado:</strong> ${file.name} | <strong>Tamanho:</strong> ${(file.size/1024).toFixed(2)} KB`;
                            }
                            // Inferir tipo e nome
                            try {
                                const obj = JSON.parse(text);
                                const tipo = (obj && obj.tipo) ? String(obj.tipo).toUpperCase() : null;
                                if (tipo && ['MAB','MCR','DESCONTOS','RENUNCIAS','OUTROS'].includes(tipo)) {
                                    const tipoSel = document.getElementById('tipoPut');
                                    if (tipoSel) tipoSel.value = tipo;
                                }
                                const dataFiltro = (obj && obj.data_filtro) ? String(obj.data_filtro).replaceAll('/', '-').trim() : '';
                                const dataArrec = (obj && (obj['data_arrecadação'] || obj['data_arrecadacao'])) ? String(obj['data_arrecadação'] || obj['data_arrecadacao']).replaceAll('/', '-').trim() : '';
                                const proc = (obj && obj.data_processamento) ? String(obj.data_processamento).trim() : '';
                                let ts = 'sem_data';
                                if (proc) {
                                    try {
                                        const dt = new Date(proc.replace('Z',''));
                                        const pad = n => String(n).padStart(2,'0');
                                        ts = `${dt.getFullYear()}${pad(dt.getMonth()+1)}${pad(dt.getDate())}_${pad(dt.getHours())}${pad(dt.getMinutes())}${pad(dt.getSeconds())}`;
                                    } catch (_) {}
                                }
                                const baseTipo = (document.getElementById('tipoPut') || {}).value || 'OUTROS';
                                const dataNome = dataArrec || dataFiltro;
                                const nomeSug = dataNome ? `${baseTipo}_${dataNome}.json` : `${baseTipo}.json`;
                                const nomeEl = document.getElementById('nomePut');
                                if (nomeEl) nomeEl.value = nomeSug;
                            } catch (_) {
                                const nomeEl = document.getElementById('nomePut');
                                if (nomeEl && file.name) nomeEl.value = file.name;
                            }
                            if (window.previewPutPath) window.previewPutPath();
                        } catch (err) {
                            mostrarAlerta(`❌ Erro ao ler arquivo: ${err.message}`, 'error');
                        }
                    });
                }

                // Reagir a edições do JSON colado manualmente
                const jsonPutEl = document.getElementById('jsonPut');
                if (jsonPutEl) {
                    jsonPutEl.addEventListener('input', function(e) {
                        const txt = e?.target?.value || '';
                        try {
                            const obj = JSON.parse(txt);
                            const tipo = (obj && obj.tipo) ? String(obj.tipo).toUpperCase() : null;
                            if (tipo && ['MAB','MCR','DESCONTOS','RENUNCIAS','OUTROS'].includes(tipo)) {
                                const tipoSel = document.getElementById('tipoPut');
                                if (tipoSel) tipoSel.value = tipo;
                            }
                            const dataFiltro = (obj && obj.data_filtro) ? String(obj.data_filtro).replaceAll('/', '-').trim() : '';
                            const dataArrec = (obj && (obj['data_arrecadação'] || obj['data_arrecadacao'])) ? String(obj['data_arrecadação'] || obj['data_arrecadacao']).replaceAll('/', '-').trim() : '';
                            const proc = (obj && obj.data_processamento) ? String(obj.data_processamento).trim() : '';
                            let ts = 'sem_data';
                            if (proc) {
                                try {
                                    const dt = new Date(proc.replace('Z',''));
                                    const pad = n => String(n).padStart(2,'0');
                                    ts = `${dt.getFullYear()}${pad(dt.getMonth()+1)}${pad(dt.getDate())}_${pad(dt.getHours())}${pad(dt.getMinutes())}${pad(dt.getSeconds())}`;
                                } catch (_) {}
                            }
                            const baseTipo = (document.getElementById('tipoPut') || {}).value || 'OUTROS';
                            const dataNome = dataArrec || dataFiltro;
                            const nomeSug = dataNome ? `${baseTipo}_${dataNome}.json` : `${baseTipo}.json`;
                            const nomeEl = document.getElementById('nomePut');
                            if (nomeEl) nomeEl.value = nomeSug;
                            if (window.previewPutPath) window.previewPutPath();
                        } catch (_) {
                            // JSON ainda inválido; ignorar
                        }
                    });
                }

                
                // Configurar eventos dos botões PUT - com verificação de que as funções existem
                const btnEnviarPut = document.getElementById('btnEnviarPut');
                if (btnEnviarPut) {
                    if (typeof window.enviarPutRemoto === 'function') {
                        btnEnviarPut.addEventListener('click', function(e) {
                            e.preventDefault();
                            e.stopPropagation();
                            window.enviarPutRemoto();
                        });
                    }
                }
                
                const btnLimparPut = document.getElementById('btnLimparPut');
                if (btnLimparPut && typeof window.limparPutRemoto === 'function') {
                    btnLimparPut.addEventListener('click', function(e) {
                        e.preventDefault();
                        e.stopPropagation();
                        window.limparPutRemoto();
                    });
                }
                
                // Configurar preview ao digitar nome
                const nomePutEl = document.getElementById('nomePut');
                if (nomePutEl) {
                    if (typeof window.previewPutPath === 'function') {
                        nomePutEl.addEventListener('input', window.previewPutPath);
                    }
                }
                
                // Configurar preview ao trocar tipo
                const tipoPutEl = document.getElementById('tipoPut');
                if (tipoPutEl) {
                    if (typeof window.previewPutPath === 'function') {
                        tipoPutEl.addEventListener('change', window.previewPutPath);
                    }
                }
            }
            
            function mostrarInfoArquivo(file) {
                const fileInfo = document.getElementById('fileInfo');
                fileInfo.innerHTML = `
                    <div class="alert alert-info">
                        <strong>Arquivo selecionado:</strong> ${file.name}<br>
                        <strong>Tamanho:</strong> ${(file.size / 1024).toFixed(2)} KB
                    </div>
                `;
                fileInfo.style.display = 'block';
            }
            
            async function testarConexao() {
                mostrarLoading(true);
                try {
                    const response = await fetch('/api/testar-conexao');
                    const resultado = await response.json();
                    
                    const statusDot = document.getElementById('statusDot');
                    const statusText = document.getElementById('statusText');
                    
                    if (resultado.sucesso) {
                        statusDot.className = 'status-dot connected';
                        statusText.textContent = '✅ Conectado à AWS';
                    } else {
                        statusDot.className = 'status-dot disconnected';
                        statusText.textContent = '❌ Erro de conexão';
                    }
                } catch (error) {
                    document.getElementById('statusDot').className = 'status-dot disconnected';
                    document.getElementById('statusText').textContent = '❌ Erro de conexão';
                }
                mostrarLoading(false);
            }
            
                
                
            async function enviarArquivo() {
                if (!arquivoSelecionado) {
                    mostrarAlerta('Por favor, selecione um arquivo', 'error');
                    return;
                }
                
                mostrarLoading(true);
                
                try {
                    const formData = new FormData();
                    formData.append('file', arquivoSelecionado);
                    
                    const response = await fetch('/api/enviar-arquivo', {
                        method: 'POST',
                        body: formData
                    });
                    
                    const resultado = await response.json();
                    
                    if (resultado.sucesso) {
                        mostrarAlerta('✅ Arquivo enviado com sucesso!', 'success');
                        document.getElementById('fileInput').value = '';
                        document.getElementById('fileInfo').style.display = 'none';
                        arquivoSelecionado = null;
                        // Atualizar estrutura de pastas automaticamente
                        setTimeout(() => listarPorPastas(), 1000);
                    } else {
                        mostrarAlerta(`❌ Erro: ${resultado.mensagem}`, 'error');
                    }
                } catch (error) {
                    mostrarAlerta(`❌ Erro: ${error.message}`, 'error');
                }
                
                mostrarLoading(false);
            }
            

            
            function fecharDados() {
                document.getElementById('dataDisplay').style.display = 'none';
            }
            

            
            
            
            async function visualizarArquivo(arquivoId) {
                mostrarLoading(true);
                
                try {
                    const response = await fetch(`/api/obter-arquivo/${arquivoId}`);
                    const resultado = await response.json();
                    
                    if (resultado.sucesso) {
                        const modal = document.getElementById('detailModal');
                        const modalTitle = document.getElementById('modalTitle');
                        const modalContent = document.getElementById('modalContent');
                        
                        modalTitle.textContent = `📄 ${resultado.arquivo.tipo || 'Arquivo'}`;
                        modalContent.innerHTML = `
                            <div style="margin-bottom: 20px;">
                                <strong>ID:</strong> ${arquivoId}<br>
                                <strong>Data Processamento:</strong> ${resultado.arquivo.data_processamento ? new Date(resultado.arquivo.data_processamento).toLocaleString() : 'N/A'}<br>
                                <strong>Data Filtro:</strong> ${resultado.arquivo.data_filtro || 'N/A'}<br>
                                <strong>Total Registros:</strong> ${resultado.arquivo.total_registros || 0}
                            </div>
                            <div class="json-viewer">${JSON.stringify(resultado.arquivo, null, 2)}</div>
                        `;
                        
                        modal.style.display = 'block';
                    } else {
                        mostrarAlerta(`❌ Erro: ${resultado.mensagem}`, 'error');
                    }
                } catch (error) {
                    mostrarAlerta(`❌ Erro: ${error.message}`, 'error');
                }
                
                mostrarLoading(false);
            }
            
            async function editarArquivo(arquivoId) {
                mostrarLoading(true);
                
                try {
                    const response = await fetch(`/api/obter-arquivo/${arquivoId}`);
                    const resultado = await response.json();
                    
                    if (resultado.sucesso) {
                        const modal = document.getElementById('detailModal');
                        const modalTitle = document.getElementById('modalTitle');
                        const modalContent = document.getElementById('modalContent');
                        
                        modalTitle.textContent = `✏️ Editar ${resultado.arquivo.tipo || 'Arquivo'}`;
                        modalContent.innerHTML = `
                            <div style="margin-bottom: 20px;">
                                <strong>ID:</strong> ${arquivoId}
                            </div>
                            <textarea id="editArquivoData" rows="20" style="width: 100%; font-family: monospace; font-size: 12px;">${JSON.stringify(resultado.arquivo, null, 2)}</textarea>
                            <div style="margin-top: 20px; text-align: right;">
                                <button class="btn btn-secondary" onclick="fecharModal()">❌ Cancelar</button>
                                <button class="btn" onclick="salvarArquivo('${arquivoId}')" style="margin-left: 10px;">💾 Salvar</button>
                            </div>
                        `;
                        
                        modal.style.display = 'block';
                    } else {
                        mostrarAlerta(`❌ Erro: ${resultado.mensagem}`, 'error');
                    }
                } catch (error) {
                    mostrarAlerta(`❌ Erro: ${error.message}`, 'error');
                }
                
                mostrarLoading(false);
            }
            
            async function salvarArquivo(arquivoId) {
                const editData = document.getElementById('editArquivoData').value;
                
                try {
                    const dados = JSON.parse(editData);
                    
                    const response = await fetch(`/api/atualizar-arquivo/${arquivoId}`, {
                        method: 'PUT',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify(dados)
                    });
                    
                    const resultado = await response.json();
                    
                    if (resultado.sucesso) {
                        mostrarAlerta('✅ Arquivo atualizado com sucesso!', 'success');
                        fecharModal();
                        // Recarregar estrutura de pastas
                        listarPorPastas();
                    } else {
                        mostrarAlerta(`❌ Erro: ${resultado.mensagem}`, 'error');
                    }
                } catch (error) {
                    mostrarAlerta(`❌ Erro: JSON inválido - ${error.message}`, 'error');
                }
            }
            
            async function deletarArquivo(arquivoId) {
                if (!confirm('Tem certeza que deseja deletar este arquivo? Esta ação não pode ser desfeita.')) {
                    return;
                }
                
                mostrarLoading(true);
                
                try {
                    const response = await fetch(`/api/deletar-arquivo/${arquivoId}`, {
                        method: 'DELETE'
                    });
                    
                    const resultado = await response.json();
                    
                    if (resultado.sucesso) {
                        mostrarAlerta('✅ Arquivo deletado com sucesso!', 'success');
                        // Recarregar estrutura de pastas
                        listarPorPastas();
                    } else {
                        mostrarAlerta(`❌ Erro: ${resultado.mensagem}`, 'error');
                    }
                } catch (error) {
                    mostrarAlerta(`❌ Erro: ${error.message}`, 'error');
                }
                
                mostrarLoading(false);
            }
            
            function fecharModal() {
                document.getElementById('detailModal').style.display = 'none';
            }
            
            async function limparDados() {
                if (!confirm('Tem certeza que deseja limpar todos os dados? Esta ação não pode ser desfeita.')) {
                    return;
                }
                
                mostrarLoading(true);
                
                try {
                    const response = await fetch('/api/limpar-dados', {
                        method: 'POST'
                    });
                    
                    const resultado = await response.json();
                    
                    if (resultado.sucesso) {
                        mostrarAlerta('✅ Dados limpos com sucesso!', 'success');
                        fecharDados();
                    } else {
                        mostrarAlerta(`❌ Erro: ${resultado.mensagem}`, 'error');
                    }
                } catch (error) {
                    mostrarAlerta(`❌ Erro: ${error.message}`, 'error');
                }
                
                mostrarLoading(false);
            }
            
            async function exportarDados() {
                mostrarLoading(true);
                
                try {
                    const response = await fetch('/api/listar-por-pastas');
                    const resultado = await response.json();
                    
                    if (resultado.sucesso) {
                        const dataStr = JSON.stringify(resultado, null, 2);
                const dataBlob = new Blob([dataStr], {type: 'application/json'});
                const url = URL.createObjectURL(dataBlob);
                const link = document.createElement('a');
                link.href = url;
                        link.download = `estrutura_pastas_${new Date().toISOString().split('T')[0]}.json`;
                link.click();
                URL.revokeObjectURL(url);
                
                        mostrarAlerta('✅ Estrutura de pastas exportada com sucesso!', 'success');
                    } else {
                        mostrarAlerta(`❌ Erro: ${resultado.mensagem}`, 'error');
                    }
                } catch (error) {
                    mostrarAlerta(`❌ Erro: ${error.message}`, 'error');
                }
                
                mostrarLoading(false);
            }
            
            function mostrarAlerta(mensagem, tipo) {
                const alertArea = document.getElementById('alertArea');
                const alertClass = tipo === 'error' ? 'alert-error' : tipo === 'success' ? 'alert-success' : 'alert-info';
                
                alertArea.innerHTML = `<div class="alert ${alertClass}">${mensagem}</div>`;
                
                setTimeout(() => {
                    alertArea.innerHTML = '';
                }, 5000);
            }
            
            function mostrarLoading(mostrar) {
                document.getElementById('loading').style.display = mostrar ? 'block' : 'none';
            }
            
            // Toggle de seções (colapsar/expandir grupos mês-ano)
            function toggleSection(sectionId) {
                try {
                    const el = document.getElementById(sectionId);
                    if (!el) return;
                    const isHidden = el.style.display === 'none';
                    el.style.display = isHidden ? 'block' : 'none';
                    const icon = document.getElementById(sectionId + '_icon');
                    if (icon) icon.textContent = isHidden ? '▾' : '▸';
                } catch (_) {}
            }
            

            
            // Funções para gerenciamento de pastas
            async function listarPorPastas() {
                mostrarLoading(true);
                
                try {
                    const response = await fetch('/api/listar-por-pastas');
                    const resultado = await response.json();
                    
                    if (resultado.sucesso) {
                        dadosCompletos = resultado; // Armazena dados completos
                        aplicarFiltros(); // Aplica filtros ativos
                    } else {
                        mostrarAlerta(`❌ Erro: ${resultado.mensagem}`, 'error');
                    }
                } catch (error) {
                    mostrarAlerta(`❌ Erro: ${error.message}`, 'error');
                }
                
                mostrarLoading(false);
            }

            // Helper: extrai mês-ano do nome do arquivo (procura por DD[-_/]MM[-_/]YYYY)
            function extrairMesAnoDeNomeArquivo(nome) {
                try {
                    const re = /(\d{1,2})[-_\/]?(\d{1,2})[-_\/]?(\d{2,4})/g;
                    let m = null;
                    // Buscar primeira ocorrência com separador claro (DD-MM-YYYY, DD_MM_YYYY ou DD/MM/YYYY)
                    const reSeparado = /(\d{1,2})[-_\/]\s*(\d{1,2})[-_\/]\s*(\d{2,4})/;
                    m = nome.match(reSeparado) || nome.match(/(\d{1,2})-(\d{1,2})-(\d{2,4})/) || nome.match(/(\d{1,2})_(\d{1,2})_(\d{2,4})/) || nome.match(/(\d{1,2})\/(\d{1,2})\/(\d{2,4})/);
                    if (!m) {
                        // Fallback: tentar sem exigir separadores diferentes
                        const re2 = /(\d{1,2})[-_\/]?(\d{1,2})[-_\/]?(\d{2,4})/;
                        m = nome.match(re2);
                        if (!m) return { key: '0000-00', label: 'Sem data' };
                    }
                    const dia = parseInt(m[1], 10);
                    const mes = parseInt(m[2], 10);
                    let ano = parseInt(m[3], 10);
                    if (ano < 100) ano += 2000;
                    if (!(mes >= 1 && mes <= 12)) return { key: '0000-00', label: 'Sem data' };
                    const nomes = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];
                    const key = `${ano}-${String(mes).padStart(2,'0')}`;
                    const label = `${nomes[mes-1]} ${ano}`;
                    return { key, label };
                } catch (_) {
                    return { key: '0000-00', label: 'Sem data' };
                }
            }

            // Agrupa array de arquivos (locais) por mês-ano usando o nome (ou data_filtro)
            function agruparPorMesAno(arquivos) {
                const grupos = {};
                (arquivos || []).forEach(arquivo => {
                    const base = String((arquivo && (arquivo.nome || arquivo.data_filtro)) || '');
                    const meta = extrairMesAnoDeNomeArquivo(base);
                    if (!grupos[meta.key]) grupos[meta.key] = { label: meta.label, itens: [] };
                    grupos[meta.key].itens.push(arquivo);
                });
                return grupos;
            }

            function obterDataConsultaApi() {
                const el = document.getElementById('dataConsultaApi');
                return (el?.value || '').trim();
            }

            function renderizarListaApi(tituloTexto, tipos) {
                const display = document.getElementById('awsListDisplay');
                const titulo = document.getElementById('awsListTitulo');
                const conteudo = document.getElementById('awsListContent');
                titulo.textContent = tituloTexto;

                if (!Array.isArray(tipos) || tipos.length === 0) {
                    conteudo.innerHTML = '<div style="color:#666">Nenhum registro retornado.</div>';
                    display.style.display = 'block';
                    return;
                }

                const linhas = tipos.map(t => {
                    const presente = t.presente ? '✅ Sim' : '❌ Não';
                    const obrigatorio = t.obrigatorio ? 'Sim' : 'Não';
                    return `
                        <tr>
                            <td>${t.tipo || '-'}</td>
                            <td>${presente}</td>
                            <td>${obrigatorio}</td>
                            <td>${t.file_name || '-'}</td>
                            <td>${t.status || '-'}</td>
                            <td>${t.retificacao ?? '-'}</td>
                            <td>${t.created_at || '-'}</td>
                        </tr>
                    `;
                }).join('');

                conteudo.innerHTML = `
                    <table style="width:100%; border-collapse: collapse; font-size: 0.92em;">
                        <thead>
                            <tr style="text-align:left; border-bottom:1px solid var(--border-secondary);">
                                <th>Tipo</th><th>Presente</th><th>Obrigatório</th><th>Arquivo</th><th>Status</th><th>RET</th><th>Criado em</th>
                            </tr>
                        </thead>
                        <tbody>${linhas}</tbody>
                    </table>
                `;
                display.style.display = 'block';
            }

            async function consultarArquivosApi() {
                const data = obterDataConsultaApi();
                if (!data) {
                    mostrarAlerta('Informe a data no formato dd/mm/aaaa', 'error');
                    return;
                }
                mostrarLoading(true);
                try {
                    const res = await fetch(`/api/listar-arquivos-remoto?data=${encodeURIComponent(data)}`);
                    const out = await res.json();
                    if (out.sucesso) {
                        renderizarListaApi(`Arquivos em ${out.data} (${out.presentes}/${out.total} presentes)`, out.tipos || []);
                        mostrarAlerta('✅ Consulta GET realizada com sucesso', 'success');
                    } else {
                        mostrarAlerta(`❌ Erro: ${out.mensagem || 'Falha na consulta'}`, 'error');
                    }
                } catch (e) {
                    mostrarAlerta(`❌ Erro: ${e.message}`, 'error');
                }
                mostrarLoading(false);
            }

            async function listarAwsDireto(tipo) {
                const data = obterDataConsultaApi();
                if (!data) {
                    mostrarAlerta('Informe a data no formato dd/mm/aaaa', 'error');
                    return;
                }
                mostrarLoading(true);
                try {
                    const res = await fetch(`/api/listar-remoto?tipo=${encodeURIComponent(tipo)}&data=${encodeURIComponent(data)}`);
                    const out = await res.json();
                    if (out.sucesso) {
                        const arquivos = Array.isArray(out.arquivos) ? out.arquivos : [];
                        const tipos = arquivos.length
                            ? arquivos.map(a => ({
                                tipo: a.tipo,
                                presente: true,
                                obrigatorio: true,
                                file_name: a.nome,
                                status: a.status,
                                retificacao: a.retificacao,
                                created_at: a.created_at
                            }))
                            : (out.resumo_tipo ? [Object.assign({ presente: false }, out.resumo_tipo)] : []);
                        renderizarListaApi(`${tipo} em ${out.data}`, tipos);
                        mostrarAlerta('✅ Consulta por tipo realizada', 'success');
                    } else {
                        mostrarAlerta(`❌ Erro: ${out.mensagem || 'Falha ao listar remoto'}`, 'error');
                    }
                } catch (e) {
                    mostrarAlerta(`❌ Erro: ${e.message}`, 'error');
                }
                mostrarLoading(false);
            }

            function fecharAwsList() {
                document.getElementById('awsListDisplay').style.display = 'none';
            }

            async function abrirRemoto(tipoEnc, nomeEnc) {
                mostrarLoading(true);
                try {
                    const tipo = decodeURIComponent(tipoEnc);
                    const nome = decodeURIComponent(nomeEnc);
                    const res = await fetch(`/api/get-remoto?tipo=${encodeURIComponent(tipo)}&nome=${encodeURIComponent(nome)}`);
                    const out = await res.json();
                    if (out.sucesso) {
                const modal = document.getElementById('detailModal');
                        const modalTitle = document.getElementById('modalTitle');
                        const modalContent = document.getElementById('modalContent');
                        modalTitle.textContent = `📄 ${nome}`;
                        modalContent.innerHTML = `<div class=\"json-viewer\">${JSON.stringify(out.dados, null, 2)}</div>`;
                        modal.style.display = 'block';
                    } else {
                        mostrarAlerta(`❌ Erro: ${out.mensagem}`, 'error');
                    }
                } catch (e) {
                    mostrarAlerta(`❌ Erro: ${e.message}`, 'error');
                }
                mostrarLoading(false);
            }
            
            function aplicarFiltros() {
                if (!dadosCompletos) return;
                
                const periodo = document.getElementById('filtroPeriodo').value;
                const filtroPersonalizado = document.getElementById('filtroPersonalizado');
                const filtroInfo = document.getElementById('filtroInfo');
                
                // Mostrar/ocultar campos personalizados
                if (periodo === 'personalizado') {
                    filtroPersonalizado.style.display = 'flex';
                } else {
                    filtroPersonalizado.style.display = 'none';
                }
                
                // Calcular datas de filtro
                let dataInicio = null;
                let dataFim = null;
                
                const hoje = new Date();
                
                switch (periodo) {
                    case 'semana':
                        dataInicio = new Date(hoje.getTime() - 7 * 24 * 60 * 60 * 1000);
                        dataFim = hoje;
                        break;
                    case 'mes':
                        dataInicio = new Date(hoje.getFullYear(), hoje.getMonth() - 1, hoje.getDate());
                        dataFim = hoje;
                        break;
                    case 'personalizado':
                        const inicioInput = document.getElementById('dataInicio').value;
                        const fimInput = document.getElementById('dataFim').value;
                        if (inicioInput && fimInput) {
                            dataInicio = new Date(inicioInput);
                            dataFim = new Date(fimInput);
                        }
                        break;
                    case 'todos':
                    default:
                        // Sem filtro de data
                        break;
                }
                
                // Atualizar filtros ativos
                filtrosAtivos = {
                    periodo: periodo,
                    dataInicio: dataInicio,
                    dataFim: dataFim
                };
                
                // Filtrar dados
                const dadosFiltrados = filtrarDadosPorPeriodo(dadosCompletos, dataInicio, dataFim);
                
                // Mostrar informações do filtro
                mostrarInfoFiltro(periodo, dataInicio, dataFim, dadosCompletos, dadosFiltrados);
                
                // Exibir dados filtrados
                mostrarEstruturaPastas(dadosFiltrados);
            }
            
            function filtrarDadosPorPeriodo(dados, dataInicio, dataFim) {
                if (!dataInicio || !dataFim) {
                    return dados; // Retorna todos os dados se não há filtro
                }
                
                const dadosFiltrados = {
                    sucesso: dados.sucesso,
                    pastas: {},
                    arquivos_sem_pasta: [],
                    total_pastas: 0,
                    total_arquivos_sem_pasta: 0
                };
                
                // Filtrar pastas
                for (const [nomePasta, pasta] of Object.entries(dados.pastas)) {
                    const arquivosFiltrados = pasta.arquivos.filter(arquivo => {
                        if (!arquivo.data_processamento) return false;
                        
                        const dataArquivo = new Date(arquivo.data_processamento);
                        return dataArquivo >= dataInicio && dataArquivo <= dataFim;
                    });
                    
                    if (arquivosFiltrados.length > 0) {
                        dadosFiltrados.pastas[nomePasta] = {
                            ...pasta,
                            arquivos: arquivosFiltrados,
                            total_arquivos: arquivosFiltrados.length
                        };
                        dadosFiltrados.total_pastas++;
                    }
                }
                
                // Filtrar arquivos sem pasta
                dadosFiltrados.arquivos_sem_pasta = dados.arquivos_sem_pasta.filter(arquivo => {
                    if (!arquivo.data_processamento) return false;
                    
                    const dataArquivo = new Date(arquivo.data_processamento);
                    return dataArquivo >= dataInicio && dataArquivo <= dataFim;
                });
                
                dadosFiltrados.total_arquivos_sem_pasta = dadosFiltrados.arquivos_sem_pasta.length;
                
                return dadosFiltrados;
            }
            
            function mostrarInfoFiltro(periodo, dataInicio, dataFim, dadosCompletos, dadosFiltrados) {
                const filtroInfo = document.getElementById('filtroInfo');
                
                if (periodo === 'todos') {
                    filtroInfo.innerHTML = '📊 Mostrando todos os arquivos';
                    return;
                }
                
                const totalCompleto = Object.values(dadosCompletos.pastas).reduce((sum, pasta) => sum + pasta.total_arquivos, 0) + dadosCompletos.total_arquivos_sem_pasta;
                const totalFiltrado = Object.values(dadosFiltrados.pastas).reduce((sum, pasta) => sum + pasta.total_arquivos, 0) + dadosFiltrados.total_arquivos_sem_pasta;
                
                let periodoTexto = '';
                if (dataInicio && dataFim) {
                    periodoTexto = `de ${dataInicio.toLocaleDateString('pt-BR')} até ${dataFim.toLocaleDateString('pt-BR')}`;
                }
                
                filtroInfo.innerHTML = `
                    📊 Filtro ativo: ${periodoTexto} | 
                    Mostrando ${totalFiltrado} de ${totalCompleto} arquivos 
                    (${Math.round((totalFiltrado / totalCompleto) * 100)}%)
                `;
            }
            
            function limparFiltros() {
                document.getElementById('filtroPeriodo').value = 'todos';
                document.getElementById('filtroPersonalizado').style.display = 'none';
                document.getElementById('dataInicio').value = '';
                document.getElementById('dataFim').value = '';
                document.getElementById('filtroInfo').innerHTML = '';
                
                if (dadosCompletos) {
                    mostrarEstruturaPastas(dadosCompletos);
                }
            }
            
            function mostrarEstruturaPastas(dados) {
                const pastasDisplay = document.getElementById('pastasDisplay');
                const pastasList = document.getElementById('pastasList');
                const pastasCount = document.getElementById('pastasCount');
                
                const totalPastas = dados.total_pastas;
                const totalArquivos = Object.values(dados.pastas).reduce((sum, pasta) => sum + pasta.total_arquivos, 0) + dados.total_arquivos_sem_pasta;
                
                pastasCount.textContent = `(${totalPastas} pastas, ${totalArquivos} arquivos)`;
                
                let html = '';
                
                // Renderiza cada pasta (agrupando visualmente por mês-ano)
                for (const [nomePasta, pasta] of Object.entries(dados.pastas)) {
                    const temScroll = pasta.total_arquivos > 8;
                    // Agrupar arquivos da pasta por mês
                    const grupos = agruparPorMesAno(pasta.arquivos);
                    const chavesOrdenadas = Object.keys(grupos).sort().reverse();
                    const gruposHtml = chavesOrdenadas.map(key => {
                        const grupo = grupos[key];
                        const sectionId = `pasta_${nomePasta}_${key}`;
                        const itensHtml = grupo.itens.map(arquivo => `
                                        <div class=\"arquivo-pasta-item\">\n                                            <div class=\"arquivo-pasta-header\">\n                                                <div class=\"arquivo-pasta-nome\">📄 ${arquivo.nome}</div>\n                                                <div class=\"arquivo-pasta-acoes\">\n                                                    <button class=\"btn btn-xs\" onclick=\"visualizarArquivo('${arquivo.id}')\" title=\"Visualizar\">👁️</button>\n                                                    <button class=\"btn btn-xs btn-secondary\" onclick=\"editarArquivo('${arquivo.id}')\" title=\"Editar\">✏️</button>\n                                                    <button class=\"btn btn-xs btn-secondary\" onclick=\"mostrarMoverArquivo('${arquivo.id}', '${nomePasta}')\" title=\"Mover\">📁</button>\n                                                    <button class=\"btn btn-xs btn-danger\" onclick=\"deletarArquivo('${arquivo.id}')\" title=\"Deletar\">🗑️</button>\n                                                </div>\n                                            </div>\n                                            <div style=\"font-size: 0.85em; color: #666;\">\n                                                <div>Data: ${arquivo.data_processamento ? new Date(arquivo.data_processamento).toLocaleString('pt-BR') : 'N/A'}</div>\n                                                <div>Registros: ${arquivo.total_registros}</div>\n                                                <div>Tamanho: ${(arquivo.tamanho / 1024).toFixed(1)} KB</div>\n                                            </div>\n                                        </div>
                                    `).join('');
                        return `
                                <div style=\"margin:8px 0; padding:8px 12px; background: var(--bg-alert); border:1px solid var(--border-secondary); border-radius:8px;\">\n                                    <div style=\"font-weight:600; color: var(--text-secondary); margin-bottom:8px; display:flex; align-items:center; gap:8px; cursor:pointer;\" onclick=\"toggleSection('${sectionId}')\">\n                                        <span id=\"${sectionId}_icon\">▾</span>\n                                        <span>📅 ${grupo.label}</span>\n                                    </div>\n                                    <div id=\"${sectionId}\" style=\"display:block;\">${itensHtml || '<div style=\\\"color:#666\\\">Vazio</div>'}</div>\n                                </div>
                        `;
                    }).join('');
                    html += `
                        <div class="pasta-card ${temScroll ? 'has-scroll' : ''}" style="--pasta-cor: ${pasta.cor}" data-pasta-nome="${nomePasta}">
                            <div class="pasta-header">
                                <div class="pasta-nome">
                                    📂 ${pasta.nome}
                                </div>
                                <div class="pasta-stats">
                                    <span class="pasta-count">${pasta.total_arquivos} arquivos</span>
                                    ${pasta.total_arquivos > 8 ? '<span style="font-size: 0.8em; color: #666; margin-left: 5px;">(scroll ↓)</span>' : ''}
                                    <div class="pasta-acoes">
                                        <button class="btn btn-xs btn-secondary" onclick="mostrarMoverArquivoPara('${nomePasta}')" title="Mover arquivo para esta pasta">📁 Mover Para</button>
                                        ${!['MAB', 'MCR', 'DESCONTOS', 'RENUNCIAS'].includes(nomePasta) ? `<button class="btn btn-xs" onclick="editarPasta('${nomePasta}')" title="Editar pasta">✏️ Editar</button>` : ''}
                                        ${!['MAB', 'MCR', 'DESCONTOS', 'RENUNCIAS'].includes(nomePasta) ? `<button class="btn btn-xs btn-danger" onclick="deletarPasta('${nomePasta}')" title="Deletar pasta">🗑️ Deletar</button>` : ''}
                                    </div>
                                </div>
                            </div>
                            <div class="arquivos-pasta">
                                ${pasta.arquivos.length === 0 ? 
                                    '<div style="text-align: center; color: #666; padding: 20px;">Nenhum arquivo nesta pasta</div>' :
                                    gruposHtml
                                }
                            </div>
                        </div>
                    `;
                }
                
                // Seção de arquivos sem pasta (agrupada por mês-ano)
                if (dados.arquivos_sem_pasta.length > 0) {
                    const temScrollSemPasta = dados.arquivos_sem_pasta.length > 6;
                    const gruposSemPasta = agruparPorMesAno(dados.arquivos_sem_pasta);
                    const chavesOrdenadasSP = Object.keys(gruposSemPasta).sort().reverse();
                    const gruposSemPastaHtml = chavesOrdenadasSP.map(key => {
                        const grupo = gruposSemPasta[key];
                        const sectionId = `sem_pasta_${key}`;
                        const itensHtml = grupo.itens.map(arquivo => `
                                    <div class=\"arquivo-pasta-item\">\n                                        <div class=\"arquivo-pasta-header\">\n                                            <div class=\"arquivo-pasta-nome\">📄 ${arquivo.nome}</div>\n                                            <div class=\"arquivo-pasta-acoes\">\n                                                <button class=\"btn btn-xs\" onclick=\"visualizarArquivo('${arquivo.id}')\" title=\"Visualizar\">👁️</button>\n                                                <button class=\"btn btn-xs btn-secondary\" onclick=\"editarArquivo('${arquivo.id}')\" title=\"Editar\">✏️</button>\n                                                <button class=\"btn btn-xs btn-secondary\" onclick=\"mostrarMoverArquivo('${arquivo.id}', 'sem_pasta')\" title=\"Mover\">📁</button>\n                                                <button class=\"btn btn-xs btn-danger\" onclick=\"deletarArquivo('${arquivo.id}')\" title=\"Deletar\">🗑️</button>\n                                            </div>\n                                        </div>\n                                        <div style=\"font-size: 0.85em; color: #666;\">\n                                            <div>Data: ${arquivo.data_processamento ? new Date(arquivo.data_processamento).toLocaleString('pt-BR') : 'N/A'}</div>\n                                            <div>Registros: ${arquivo.total_registros}</div>\n                                            <div>Tamanho: ${(arquivo.tamanho / 1024).toFixed(1)} KB</div>\n                                        </div>\n                                    </div>
                                `).join('');
                        return `
                            <div style=\"margin:8px 0; padding:8px 12px; background: var(--bg-alert); border:1px solid var(--border-secondary); border-radius:8px;\">\n                                <div style=\"font-weight:600; color: #666; margin-bottom:8px; display:flex; align-items:center; gap:8px; cursor:pointer;\" onclick=\"toggleSection('${sectionId}')\">\n                                    <span id=\"${sectionId}_icon\">▾</span>\n                                    <span>📅 ${grupo.label}</span>\n                                </div>\n                                <div id=\"${sectionId}\" style=\"display:block;\">${itensHtml}</div>\n                            </div>
                        `;
                    }).join('');
                    html += `
                        <div class="sem-pasta-section ${temScrollSemPasta ? 'has-scroll' : ''}">
                            <h4>📁 Arquivos sem Pasta (${dados.arquivos_sem_pasta.length})${dados.arquivos_sem_pasta.length > 6 ? ' <span style="font-size: 0.8em; color: #666;">(scroll ↓)</span>' : ''}</h4>
                            <div class="arquivos-pasta">
                                ${gruposSemPastaHtml}
                            </div>
                        </div>
                    `;
                }
                
                pastasList.innerHTML = `<div class="pastas-grid">${html}</div>`;
                pastasDisplay.style.display = 'block';
            }
            
            function fecharPastas() {
                document.getElementById('pastasDisplay').style.display = 'none';
            }
            
            function mostrarCriarPasta() {
                document.getElementById('criarPastaModal').style.display = 'block';
                document.getElementById('nomePasta').value = '';
                document.getElementById('corPasta').value = '#6c757d';
            }
            
            function fecharCriarPasta() {
                document.getElementById('criarPastaModal').style.display = 'none';
            }
            
            function editarPasta(nomePasta) {
                // Buscar dados da pasta atual
                if (!dadosCompletos || !dadosCompletos.pastas[nomePasta]) {
                    mostrarAlerta('Erro: dados da pasta não encontrados', 'error');
                    return;
                }
                
                const pasta = dadosCompletos.pastas[nomePasta];
                
                // Preencher modal com dados atuais
                document.getElementById('nomePastaEdit').value = pasta.nome;
                document.getElementById('corPastaEdit').value = pasta.cor;
                
                // Armazenar nome original para referência
                window.pastaEditando = nomePasta;
                
                // Mostrar modal
                document.getElementById('editarPastaModal').style.display = 'block';
            }
            
            function fecharEditarPasta() {
                document.getElementById('editarPastaModal').style.display = 'none';
                window.pastaEditando = null;
            }
            
            async function salvarEdicaoPasta() {
                if (!window.pastaEditando) {
                    mostrarAlerta('Erro: pasta não identificada', 'error');
                    return;
                }
                
                const novoNome = document.getElementById('nomePastaEdit').value.trim();
                const novaCor = document.getElementById('corPastaEdit').value;
                
                if (!novoNome) {
                    mostrarAlerta('Por favor, insira um nome para a pasta', 'error');
                    return;
                }
                
                mostrarLoading(true);
                
                try {
                    // Atualizar dados locais primeiro
                    if (dadosCompletos && dadosCompletos.pastas[window.pastaEditando]) {
                        const pastaOriginal = dadosCompletos.pastas[window.pastaEditando];
                        
                        // Se o nome mudou, criar nova entrada e remover antiga
                        if (novoNome !== window.pastaEditando) {
                            dadosCompletos.pastas[novoNome] = {
                                nome: novoNome,
                                cor: novaCor,
                                arquivos: pastaOriginal.arquivos
                            };
                            delete dadosCompletos.pastas[window.pastaEditando];
                        } else {
                            // Apenas atualizar cor
                            dadosCompletos.pastas[window.pastaEditando].cor = novaCor;
                            dadosCompletos.pastas[window.pastaEditando].nome = novoNome;
                        }
                        
                        // Salvar na AWS
                        const response = await fetch('/api/salvar-estrutura', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({
                                pastas: dadosCompletos.pastas,
                                arquivos_sem_pasta: dadosCompletos.arquivos_sem_pasta
                            })
                        });
                        
                        const resultado = await response.json();
                        
                        if (resultado.sucesso) {
                            mostrarAlerta('✅ Pasta editada com sucesso!', 'success');
                            fecharEditarPasta();
                            aplicarFiltros(); // Recarregar com filtros ativos
                        } else {
                            mostrarAlerta(`❌ Erro: ${resultado.mensagem}`, 'error');
                        }
                    }
                } catch (error) {
                    mostrarAlerta(`❌ Erro: ${error.message}`, 'error');
                }
                
                mostrarLoading(false);
            }
            
            async function criarPasta() {
                const nome = document.getElementById('nomePasta').value.trim();
                const cor = document.getElementById('corPasta').value;
                
                if (!nome) {
                    mostrarAlerta('Por favor, insira um nome para a pasta', 'error');
                    return;
                }
                
                mostrarLoading(true);
                
                try {
                    const response = await fetch('/api/criar-pasta', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ nome, cor })
                    });
                    
                    const resultado = await response.json();
                    
                    if (resultado.sucesso) {
                        mostrarAlerta('✅ Pasta criada com sucesso!', 'success');
                        fecharCriarPasta();
                        listarPorPastas();
                    } else {
                        mostrarAlerta(`❌ Erro: ${resultado.mensagem}`, 'error');
                    }
                } catch (error) {
                    mostrarAlerta(`❌ Erro: ${error.message}`, 'error');
                }
                
                mostrarLoading(false);
            }
            
            async function deletarPasta(nomePasta) {
                if (!confirm(`Tem certeza que deseja deletar a pasta '${nomePasta}'? Os arquivos serão movidos para 'Arquivos sem Pasta'.`)) {
                    return;
                }
                
                mostrarLoading(true);
                
                try {
                    const response = await fetch(`/api/deletar-pasta/${nomePasta}`, {
                        method: 'DELETE'
                    });
                    
                    const resultado = await response.json();
                    
                    if (resultado.sucesso) {
                        mostrarAlerta('✅ Pasta deletada com sucesso!', 'success');
                        listarPorPastas();
                    } else {
                        mostrarAlerta(`❌ Erro: ${resultado.mensagem}`, 'error');
                    }
                } catch (error) {
                    mostrarAlerta(`❌ Erro: ${error.message}`, 'error');
                }
                
                mostrarLoading(false);
            }
            
            function mostrarMoverArquivo(arquivoId, pastaOrigem) {
                // Primeiro, obtém a lista de pastas disponíveis
                fetch('/api/listar-por-pastas')
                    .then(response => response.json())
                    .then(dados => {
                        if (dados.sucesso) {
                            const select = document.getElementById('pastaDestino');
                            select.innerHTML = '<option value="">Selecione a pasta de destino...</option>';
                            
                            // Adiciona opções para cada pasta
                            for (const [nomePasta, pasta] of Object.entries(dados.pastas)) {
                                if (nomePasta !== pastaOrigem) {
                                    select.innerHTML += `<option value="${nomePasta}">${pasta.nome}</option>`;
                                }
                            }
                            
                            // Adiciona opção para "sem pasta"
                            if (pastaOrigem !== 'sem_pasta') {
                                select.innerHTML += '<option value="sem_pasta">Arquivos sem Pasta</option>';
                            }
                            
                            // Armazena dados para uso posterior
                            window.arquivoParaMover = {
                                id: arquivoId,
                                origem: pastaOrigem
                            };
                            
                            document.getElementById('arquivoParaMover').textContent = arquivoId.substring(0, 8) + '...';
                            document.getElementById('pastaAtual').textContent = pastaOrigem === 'sem_pasta' ? 'Arquivos sem Pasta' : dados.pastas[pastaOrigem]?.nome || pastaOrigem;
                            
                            document.getElementById('moverArquivoModal').style.display = 'block';
                        }
                    })
                    .catch(error => {
                        mostrarAlerta(`❌ Erro: ${error.message}`, 'error');
                    });
            }
            
            function fecharMoverArquivo() {
                document.getElementById('moverArquivoModal').style.display = 'none';
            }
            
            async function confirmarMoverArquivo() {
                const pastaDestino = document.getElementById('pastaDestino').value;
                
                if (!pastaDestino) {
                    mostrarAlerta('Por favor, selecione uma pasta de destino', 'error');
                    return;
                }
                
                if (!window.arquivoParaMover) {
                    mostrarAlerta('Erro: dados do arquivo não encontrados', 'error');
                    return;
                }
                
                mostrarLoading(true);
                
                try {
                    const response = await fetch('/api/mover-arquivo', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            arquivo_id: window.arquivoParaMover.id,
                            pasta_origem: window.arquivoParaMover.origem,
                            pasta_destino: pastaDestino
                        })
                    });
                    
                    const resultado = await response.json();
                    
                    if (resultado.sucesso) {
                        mostrarAlerta('✅ Arquivo movido com sucesso!', 'success');
                        fecharMoverArquivo();
                        listarPorPastas();
                    } else {
                        mostrarAlerta(`❌ Erro: ${resultado.mensagem}`, 'error');
                    }
                } catch (error) {
                    mostrarAlerta(`❌ Erro: ${error.message}`, 'error');
                }
                
                mostrarLoading(false);
            }
            
            // Fechar modais ao clicar fora
            window.onclick = function(event) {
                const detailModal = document.getElementById('detailModal');
                const criarPastaModal = document.getElementById('criarPastaModal');
                const editarPastaModal = document.getElementById('editarPastaModal');
                const moverArquivoModal = document.getElementById('moverArquivoModal');
                
                if (event.target === detailModal) {
                    fecharModal();
                }
                if (event.target === criarPastaModal) {
                    fecharCriarPasta();
                }
                if (event.target === editarPastaModal) {
                    fecharEditarPasta();
                }
                if (event.target === moverArquivoModal) {
                    fecharMoverArquivo();
                }
            }
            
            // Sistema de Temas
            function inicializarTema() {
                const temaSalvo = localStorage.getItem('aws-manager-theme') || 'light';
                aplicarTema(temaSalvo);
            }
            
            function toggleTheme() {
                const temaAtual = document.documentElement.getAttribute('data-theme') || 'light';
                const novoTema = temaAtual === 'light' ? 'dark' : 'light';
                aplicarTema(novoTema);
                localStorage.setItem('aws-manager-theme', novoTema);
            }
            
            function aplicarTema(tema) {
                document.documentElement.setAttribute('data-theme', tema);
                const themeIcon = document.getElementById('themeIcon');
                
                if (tema === 'dark') {
                    themeIcon.textContent = '☀️';
                    themeIcon.title = 'Alternar para tema claro';
                } else {
                    themeIcon.textContent = '🌙';
                    themeIcon.title = 'Alternar para tema escuro';
                }
                
                // Atualizar cores das pastas dinamicamente
                atualizarCoresPastas(tema);
            }
            
            function atualizarCoresPastas(tema) {
                const pastaCards = document.querySelectorAll('.pasta-card');
                pastaCards.forEach(card => {
                    const nomePasta = card.getAttribute('data-pasta-nome');
                    if (nomePasta) {
                        let corPasta = '';
                        switch(nomePasta) {
                            case 'MAB':
                                corPasta = tema === 'dark' ? '#dc3545' : '#ff6600';
                                break;
                            case 'MCR':
                                corPasta = '#28a745';
                                break;
                            case 'DESCONTOS':
                                corPasta = '#17a2b8';
                                break;
                            case 'RENUNCIAS':
                                corPasta = '#6f42c1';
                                break;
                            case 'OUTROS':
                                corPasta = '#6c757d';
                                break;
                            default:
                                corPasta = tema === 'dark' ? '#dc3545' : '#ff6600';
                        }
                        card.style.setProperty('--pasta-cor', corPasta);
                    }
                });
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@router.get("/api/testar-conexao")
async def testar_conexao():

    resultado = aws_manager.testar_conexao()
   
    if (not resultado.get("sucesso")) and (
        resultado.get("status_code") is None or
        (isinstance(resultado.get("mensagem"), str) and "Expecting value" in resultado.get("mensagem", ""))
    ):
        try:
            resp = requests.get(aws_manager.AWS_API_URL, headers=aws_manager.headers, timeout=10)
            conteudo_bruto = (resp.text or "").strip()
            return JSONResponse(content={
                "sucesso": resp.status_code == 200,
                "status_code": resp.status_code,
                "mensagem": "Conexão bem-sucedida" if resp.status_code == 200 else f"Erro: {resp.status_code}",
                "dados": None,
                "url": aws_manager.AWS_API_URL,
                "raw": conteudo_bruto[:500]
            })
        except Exception as e:
            return JSONResponse(content={
                "sucesso": False,
                "status_code": None,
                "mensagem": f"Erro de conexão: {str(e)}",
                "dados": None
            })
    return JSONResponse(content=resultado)

@router.post("/api/enviar-dados")
async def enviar_dados(request: Request):

    dados = await request.json()
    resultado = aws_manager.enviar_dados_visivel(dados)
    return JSONResponse(content=resultado)

@router.post("/api/enviar-arquivo")
async def enviar_arquivo(file: UploadFile = File(...)):

    try:

        temp_path = f"temp_{file.filename}"
        with open(temp_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        

        resultado = aws_manager.enviar_arquivo_json(temp_path)
        

        os.remove(temp_path)
        
        return JSONResponse(content=resultado)
    except Exception as e:
        return JSONResponse(content={
            "sucesso": False,
            "mensagem": f"Erro ao processar arquivo: {str(e)}"
        })



@router.post("/api/limpar-dados")
async def limpar_dados():

    resultado = aws_manager.limpar_dados()
    return JSONResponse(content=resultado)

@router.get("/api/listar-arquivos")
async def listar_arquivos():

    resultado = aws_manager.listar_arquivos_por_pasta()
    return JSONResponse(content=resultado)

@router.get("/api/obter-arquivo/{arquivo_id}")
async def obter_arquivo(arquivo_id: str):

    resultado = aws_manager.obter_arquivo_por_id(arquivo_id)
    return JSONResponse(content=resultado)

@router.put("/api/atualizar-arquivo/{arquivo_id}")
async def atualizar_arquivo(arquivo_id: str, request: Request):

    novos_dados = await request.json()
    resultado = aws_manager.atualizar_arquivo(arquivo_id, novos_dados)
    return JSONResponse(content=resultado)

@router.delete("/api/deletar-arquivo/{arquivo_id}")
async def deletar_arquivo(arquivo_id: str):

    resultado = aws_manager.deletar_arquivo(arquivo_id)
    return JSONResponse(content=resultado)


@router.get("/api/listar-por-pastas")
async def listar_por_pastas():
   
    resultado = aws_manager.listar_arquivos_por_pasta()
    return JSONResponse(content=resultado)

@router.post("/api/criar-pasta")
async def criar_pasta(request: Request):
   
    dados = await request.json()
    nome_pasta = dados.get("nome")
    cor = dados.get("cor", "#6c757d")
    
    if not nome_pasta:
        return JSONResponse(content={
            "sucesso": False,
            "mensagem": "Nome da pasta é obrigatório"
        })
    
    resultado = aws_manager.criar_pasta(nome_pasta, cor)
    return JSONResponse(content=resultado)

@router.delete("/api/deletar-pasta/{nome_pasta}")
async def deletar_pasta(nome_pasta: str):

    resultado = aws_manager.deletar_pasta(nome_pasta)
    return JSONResponse(content=resultado)

@router.post("/api/mover-arquivo")
async def mover_arquivo(request: Request):

    dados = await request.json()
    arquivo_id = dados.get("arquivo_id")
    pasta_origem = dados.get("pasta_origem")
    pasta_destino = dados.get("pasta_destino")
    
    if not all([arquivo_id, pasta_origem, pasta_destino]):
        return JSONResponse(content={
            "sucesso": False,
            "mensagem": "arquivo_id, pasta_origem e pasta_destino são obrigatórios"
        })
    
    resultado = aws_manager.mover_arquivo(arquivo_id, pasta_origem, pasta_destino)
    return JSONResponse(content=resultado)

@router.post("/api/salvar-estrutura")
async def salvar_estrutura(request: Request):
    
    dados = await request.json()
    pastas = dados.get("pastas", {})
    arquivos_sem_pasta = dados.get("arquivos_sem_pasta", [])
    
    estrutura = {
        "pastas": pastas,
        "arquivos_sem_pasta": arquivos_sem_pasta
    }
    
    resultado = aws_manager._salvar_estrutura_pastas(estrutura)
    return JSONResponse(content=resultado)


@router.get("/api/get-remoto")
async def get_remoto(tipo: str, nome: str):
    resultado = aws_manager.baixar_arquivo_por_tipo_nome(tipo, nome)
    return JSONResponse(content=resultado)

#
@router.get("/api/get-remoto-por-id/{arquivo_id}")
async def get_remoto_por_id(arquivo_id: str):
    info = aws_manager.obter_arquivo_por_id(arquivo_id)
    if not info.get("sucesso"):
        return JSONResponse(content=info)
    metadados = info.get("metadados") or {}
    tipo = metadados.get("tipo") or (info.get("arquivo") or {}).get("tipo")
    nome_arquivo = metadados.get("nome_arquivo")
    if not tipo or not nome_arquivo:
        return JSONResponse(content={
            "sucesso": False,
            "mensagem": "Metadados insuficientes para GET remoto"
        })
    resultado = aws_manager.baixar_arquivo_por_tipo_nome(tipo, nome_arquivo)
    return JSONResponse(content=resultado)


@router.get("/api/listar-arquivos-remoto")
async def listar_arquivos_remoto(data: str):
    resultado = aws_manager.listar_arquivos_por_data(data)
    return JSONResponse(content=resultado)


@router.get("/api/listar-remoto")
async def listar_remoto(tipo: str, data: str = ""):
    resultado = aws_manager.listar_pasta_remota(tipo, data=data)
    return JSONResponse(content=resultado)


@router.post("/api/put-remoto")
async def put_remoto(request: Request):
    body = await request.json()
    tipo = body.get("tipo")
    nome = body.get("nome")
    dados = body.get("dados")
    if not all([tipo, nome, dados is not None]):
        return JSONResponse(content={"sucesso": False, "mensagem": "tipo, nome e dados são obrigatórios"})
    
    # Único envio: PUT direto no S3 com o nome curto escolhido pelo usuário
    resultado_put = aws_manager.put_arquivo_remoto(tipo, nome, dados)
    
    # Se o PUT funcionou, apenas adiciona entrada ao índice (sem segundo upload)
    if resultado_put.get("sucesso"):
        resultado_indice = aws_manager.adicionar_entrada_indice(tipo, nome, dados)
        body_api = {}
        try:
            body_api = json.loads(resultado_put.get("body") or "{}")
        except Exception:
            body_api = {"raw": resultado_put.get("body")}
        resposta = {
            "sucesso": True,
            "status_code": resultado_put.get("status_code"),
            "url": resultado_put.get("url"),
            "path": body_api.get("path"),
            "message": body_api.get("message"),
            "mensagem": body_api.get("message") or f"Upload realizado. Arquivo: {nome}",
            "upload_direto": resultado_put,
            "indice_atualizado": resultado_indice.get("sucesso", False),
        }
        if resultado_indice.get("sucesso"):
            resposta["arquivo_id"] = resultado_indice.get("arquivo_id")
        return JSONResponse(content=resposta)
    return JSONResponse(content=resultado_put)

app.include_router(router)


@app.get("/", include_in_schema=False)
async def standalone_root():
    return RedirectResponse(url="/aws")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("aws_interface:app", host="0.0.0.0", port=8001) 