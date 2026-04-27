# ============================================================
# ui/ui.py
# UI dùng Flask (local web server) + HTML/CSS/JS
# Mở browser tự động, render bàn cờ bằng chess.svg (giống Colab)
# Giao tiếp JS ↔ Python qua REST API thay vì invokeFunction
# ============================================================

import chess
import chess.svg
import threading
import webbrowser
import time
from flask import Flask, jsonify, request, render_template_string

from ai.minimax import get_best_move

# ── Flask app ─────────────────────────────────────────────────────
app = Flask(__name__)
app.config['SECRET_KEY'] = 'chess_ai_local'

# ── HTML Template (giữ nguyên style từ Colab Cell 4) ─────────────
HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<title>Chess AI — Minimax</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
html {
    overflow-y: scroll;
    scrollbar-gutter: stable;
}
body {
    font-family: Tahoma, 'Segoe UI', Arial, sans-serif;
    background: #f8fafc;
    color: #0f172a;
    font-size: 16px;
    line-height: 1.5;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 16px;
}

h2 {
    font-family: Georgia, serif;
    color: #0f172a;
    margin-bottom: 4px;
    font-size: 22px;
}
.subtitle {
    color: #64748b;
    font-size: 13px;
    margin-bottom: 14px;
}

.main-layout {
    display: flex;
    gap: 20px;
    align-items: flex-start;
    flex-wrap: wrap;
    justify-content: center;
}

/* ── LEFT: bàn cờ + status ── */
.left-col {
    width: 600px;
    max-width: calc(100vw - 32px);
    display: flex;
    flex-direction: column;
    gap: 10px;
}

#board-container {
    width: 100%;
    aspect-ratio: 1 / 1;
    height: auto;
    cursor: pointer;
    border-radius: 4px;
    overflow: hidden;
    border: 1px solid #dbe5f0;
    box-shadow: 0 10px 24px rgba(15, 23, 42, 0.12);
    position: relative;
}
#board-container svg { width: 100% !important; height: 100% !important; display: block; }

.status-bar {
    background: #ffffff;
    width: 100%;
    border-radius: 6px;
    padding: 10px 14px;
    font-size: 15px;
    border: 1px solid #dbe5f0;
    border-left: 4px solid #27ae60;
    transition: border-color 0.3s;
}
.status-bar .captured {
    color: #64748b;
    font-size: 13px;
    margin-bottom: 4px;
}
.status-bar .status-text { font-weight: 600; font-size: 16px; }
.status-ok   { color: #27ae60; }
.status-ai   { color: #3498db; }
.status-err  { color: #e74c3c; }
.status-warn { color: #f39c12; }

/* ── RIGHT: panel điều khiển ── */
.right-col {
    width: 260px;
    display: flex;
    flex-direction: column;
    gap: 12px;
}

.card {
    background: #ffffff;
    border: 1px solid #dbe5f0;
    border-radius: 8px;
    padding: 14px;
    box-shadow: 0 8px 20px rgba(15, 23, 42, 0.08);
}
.card h3 {
    font-size: 14px;
    color: #334155;
    margin-bottom: 10px;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}

/* Nút */
.btn-row { display: flex; gap: 8px; }
.btn {
    flex: 1;
    padding: 9px 0;
    border: none;
    border-radius: 6px;
    font-size: 14px;
    font-weight: bold;
    cursor: pointer;
    transition: filter 0.15s, transform 0.1s;
}
.btn:hover  { filter: brightness(1.15); transform: translateY(-1px); }
.btn:active { transform: translateY(0); }
.btn-new  { background: #2980b9; color: #fff; }
.btn-undo { background: #e67e22; color: #fff; }

/* Radio buttons (style đẹp) */
.radio-group { display: flex; flex-direction: column; gap: 7px; }
.radio-item {
    display: flex;
    align-items: center;
    gap: 10px;
    cursor: pointer;
    padding: 6px 10px;
    border-radius: 6px;
    transition: background 0.15s;
    font-size: 14px;
}
.radio-item:hover { background: #f1f5f9; }
.radio-item input[type=radio] { display: none; }
.radio-dot {
    width: 16px; height: 16px;
    border-radius: 50%;
    border: 2px solid #94a3b8;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
    transition: border-color 0.2s;
}
.radio-item input:checked ~ .radio-dot {
    border-color: #3498db;
}
.radio-item input:checked ~ .radio-dot::after {
    content: '';
    width: 8px; height: 8px;
    border-radius: 50%;
    background: #3498db;
}
.radio-item input:checked ~ span { color: #0f172a; font-weight: 600; }

/* Lịch sử nước đi */
.history-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
}
.history-table th {
    color: #64748b;
    text-align: left;
    padding: 3px 4px;
    font-size: 13px;
}
.history-table td { padding: 3px 4px; }
.history-table tr:nth-child(even) td { background: rgba(15, 23, 42, 0.05); }
.move-white { color: #0f172a; }
.move-black { color: #e0937a; }
.move-num   { color: #64748b; }

#history-scroll {
    max-height: 180px;
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: #94a3b8 transparent;
}

/* Thống kê AI */
.stat-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 4px 0;
    font-size: 14px;
    border-bottom: 1px solid rgba(15, 23, 42, 0.08);
}
.stat-row:last-child { border-bottom: none; }
.stat-label { color: #64748b; }
.stat-val   { color: #0f172a; font-weight: bold; }
.stat-pos   { color: #27ae60; }
.stat-neg   { color: #e74c3c; }

/* Spinner AI */
.ai-spinner {
    display: none;
    width: 14px; height: 14px;
    border: 2px solid #3498db;
    border-top-color: transparent;
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
    margin-right: 6px;
}
@keyframes spin { to { transform: rotate(360deg); } }

.empty-hint { color: #64748b; font-size: 13px; font-style: italic; }
hr { border-color: rgba(15, 23, 42, 0.12); margin: 2px 0; }

@media (max-width: 760px) {
    .right-col {
        width: min(420px, calc(100vw - 32px));
    }
}
</style>
</head>
<body>
<h2>♟️ Chess AI : Minimax Alpha-Beta Pruning</h2>

<div class="main-layout">

<!-- ── LEFT ── -->
<div class="left-col">
    <div id="board-container" onclick="handleBoardClick(event)">
    <!-- SVG bàn cờ inject vào đây -->
    </div>

    <div class="status-bar" id="status-bar">
    <div class="captured" id="captured-text">Trắng ăn: — | Đen ăn: —</div>
    <div class="status-text status-ok" id="status-text">🟢 Lượt của bạn!</div>
    </div>
</div>

<!-- ── RIGHT ── -->
<div class="right-col">

    <!-- Nút điều khiển -->
    <div class="card">
    <div class="btn-row">
        <button class="btn btn-new"  onclick="newGame()">Ván mới</button>
        <button class="btn btn-undo" onclick="undoMove()">Đi lại</button>
    </div>
    </div>

    <!-- Màu quân -->
    <div class="card">
    <h3>Màu quân</h3>
    <div class="radio-group">
        <label class="radio-item">
        <input type="radio" name="color" value="white" checked onchange="setColor('white')">
        <div class="radio-dot"></div>
        <span>Chơi Trắng ♙</span>
        </label>
        <label class="radio-item">
        <input type="radio" name="color" value="black" onchange="setColor('black')">
        <div class="radio-dot"></div>
        <span>Chơi Đen ♟</span>
        </label>
    </div>
    </div>

    <!-- Độ khó -->
    <div class="card">
    <h3>Độ khó (Depth)</h3>
    <div class="radio-group">
        <label class="radio-item">
        <input type="radio" name="depth" value="1" onchange="setDepth(1)">
        <div class="radio-dot"></div>
        <span>Dễ (depth 1)</span>
        </label>
        <label class="radio-item">
        <input type="radio" name="depth" value="2" checked onchange="setDepth(2)">
        <div class="radio-dot"></div>
        <span>TB (depth 2)</span>
        </label>
        <label class="radio-item">
        <input type="radio" name="depth" value="3" onchange="setDepth(3)">
        <div class="radio-dot"></div>
        <span>Khó (depth 3)</span>
        </label>
    </div>
    </div>

    <!-- Lịch sử nước đi -->
    <div class="card">
    <h3>Lịch sử nước đi</h3>
    <div id="history-scroll">
        <div class="empty-hint" id="history-empty">Chưa có nước đi...</div>
        <table class="history-table" id="history-table" style="display:none">
        <thead>
            <tr>
            <th>#</th><th>Trắng</th><th>Đen</th>
            </tr>
        </thead>
        <tbody id="history-body"></tbody>
        </table>
    </div>
    </div>

    <!-- Thống kê AI -->
    <div class="card">
    <h3>
        <span class="ai-spinner" id="ai-spinner"></span>
        Thống kê AI
    </h3>
    <div id="stats-content">
        <div class="empty-hint">Chờ AI tính toán...</div>
    </div>
    </div>

</div><!-- end right-col -->
</div><!-- end main-layout -->

<script>
// Popup chọn quân phong cấp
function showPromotionDialog(callback) {
    const dialog = document.createElement('div');
    dialog.id = 'promotion-dialog';
    dialog.style.position = 'fixed';
    dialog.style.left = '0';
    dialog.style.top = '0';
    dialog.style.width = '100vw';
    dialog.style.height = '100vh';
    dialog.style.background = 'rgba(0,0,0,0.25)';
    dialog.style.display = 'flex';
    dialog.style.alignItems = 'center';
    dialog.style.justifyContent = 'center';
    dialog.style.zIndex = '9999';
    dialog.innerHTML = `
        <div style="background:#fff;padding:24px 32px;border-radius:12px;box-shadow:0 8px 32px #0002;display:flex;flex-direction:column;align-items:center;gap:16px;min-width:220px">
            <div style="font-size:18px;font-weight:bold;margin-bottom:8px">Chọn quân phong cấp</div>
            <div style="display:flex;gap:16px;justify-content:center">
                <button class="promo-btn" data-piece="q" title="Hậu" style="font-size:28px">♕</button>
                <button class="promo-btn" data-piece="r" title="Xe" style="font-size:28px">♖</button>
                <button class="promo-btn" data-piece="b" title="Tượng" style="font-size:28px">♗</button>
                <button class="promo-btn" data-piece="n" title="Mã" style="font-size:28px">♘</button>
            </div>
            <div style="font-size:13px;color:#64748b">(Chỉ hiện khi tốt đi đến cuối bàn)</div>
        </div>
    `;
    document.body.appendChild(dialog);
    dialog.querySelectorAll('.promo-btn').forEach(btn => {
        btn.onclick = () => {
            const piece = btn.getAttribute('data-piece');
            dialog.remove();
            callback(piece);
        };
    });
}

// ══════════════════════════════════════════════════════════════
// STATE CLIENT
// ══════════════════════════════════════════════════════════════
let selectedSquare = null;   // null = chưa chọn
let legalTargets   = [];     // danh sách ô hợp lệ từ ô đang chọn
let aiThinking     = false;

// ══════════════════════════════════════════════════════════════
// KHỞI ĐỘNG
// ══════════════════════════════════════════════════════════════
window.onload = () => {
refreshBoard();
};

// ══════════════════════════════════════════════════════════════
// FETCH HELPERS
// ══════════════════════════════════════════════════════════════
async function api(path, body = null) {
const opts = { method: body ? 'POST' : 'GET', headers: { 'Content-Type': 'application/json' } };
if (body) opts.body = JSON.stringify(body);
const r = await fetch(path, opts);
return r.json();
}

// ══════════════════════════════════════════════════════════════
// RENDER BÀN CỜ — gọi server lấy SVG về rồi inject
// ══════════════════════════════════════════════════════════════
async function refreshBoard(highlightFrom = null, highlightTo = null,
                            selected = null, legalSqs = []) {
const params = new URLSearchParams();
if (highlightFrom !== null) params.set('from_sq', highlightFrom);
if (highlightTo   !== null) params.set('to_sq',   highlightTo);
if (selected      !== null) params.set('selected', selected);
if (legalSqs.length)        params.set('legal', legalSqs.join(','));

const data = await api('/board?' + params.toString());
document.getElementById('board-container').innerHTML = data.svg;
document.getElementById('captured-text').textContent = data.captured;
updateHistoryUI(data.history);
updateStatsUI(data.stats);
updateStatusUI(data.status, data.status_class);
}

// ══════════════════════════════════════════════════════════════
// CLICK BÀN CỜ — tính ô từ tọa độ pixel (giống JS trong Colab)
// ══════════════════════════════════════════════════════════════
async function handleBoardClick(event) {
if (aiThinking) return;

const container = document.getElementById('board-container');
const rect = container.getBoundingClientRect();

// chess.svg có margin 20px trên kích thước gốc 420px
const svgSize = rect.width;
const scale   = svgSize / 420;
const margin  = 20 * scale;
const cell    = (svgSize - 2 * margin) / 8;

const x = event.clientX - rect.left;
const y = event.clientY - rect.top;

const col = Math.floor((x - margin) / cell);
const row = Math.floor((y - margin) / cell);
if (col < 0 || col > 7 || row < 0 || row > 7) return;

// Lấy player_color từ server để tính đúng flipped
const stateData = await api('/state');
const flipped = stateData.flipped;

let square;
if (flipped) {
    square = row * 8 + (7 - col);
} else {
    square = (7 - row) * 8 + col;
}

await handleClick(square);
}

// ══════════════════════════════════════════════════════════════
// HANDLE CLICK — máy trạng thái 2 bước (giống _handle_click Colab)
// ══════════════════════════════════════════════════════════════
async function handleClick(square) {
if (aiThinking) return;

// ── BƯỚC 1: Chưa chọn quân ──
if (selectedSquare === null) {
    const data = await api('/select', { square });
    if (!data.ok) return;

    selectedSquare = square;
    legalTargets   = data.legal_targets;

    setStatus(
    `🎯 Đã chọn ${data.square_name} — Click ô đích hoặc click lại để bỏ chọn`,
    'status-ai'
    );
    await refreshBoard(null, null, selectedSquare, legalTargets);
    return;
}

// ── BƯỚC 2: Đã chọn quân ──
const from_sq = selectedSquare;

// Click lại ô cũ → bỏ chọn
if (square === from_sq) {
    selectedSquare = null;
    legalTargets   = [];
    await refreshBoard();
    return;
}

// Click quân mình khác → chuyển chọn
const checkData = await api('/select', { square });
if (checkData.ok && checkData.own_piece) {
    selectedSquare = square;
    legalTargets   = checkData.legal_targets;
    setStatus(
    `🎯 Đã chọn ${checkData.square_name} — Click ô đích`,
    'status-ai'
    );
    await refreshBoard(null, null, selectedSquare, legalTargets);
    return;
}

// Click ô không hợp lệ
if (!legalTargets.includes(square)) {
    selectedSquare = null;
    legalTargets   = [];
    setStatus('❌ Ô không hợp lệ! Click lại quân cờ.', 'status-err');
    await refreshBoard();
    return;
}

selectedSquare = null;
legalTargets   = [];

// Kiểm tra có phải nước phong cấp không
const stateData = await api('/state');
const isWhitePlayer = !stateData.flipped;
const toRank = Math.floor(square / 8);
const pieceData = await api('/select', { square: from_sq });
const isPawn = pieceData.ok && pieceData.own_piece && pieceData.piece_type === 'p';
const promotionRank = isWhitePlayer ? 7 : 0;
let promotion = null;
if (isPawn && (toRank === promotionRank)) {
    // Hiện popup chọn quân
    await new Promise(resolve => {
        showPromotionDialog(sel => {
            promotion = sel;
            resolve();
        });
    });
}

const moveData = await api('/move', { from_sq, to_sq: square, promotion });
if (!moveData.ok) {
        setStatus('❌ Nước đi lỗi!', 'status-err');
        await refreshBoard();
        return;
}

await refreshBoard();

if (moveData.game_over) return;

aiThinking = true;
document.getElementById('ai-spinner').style.display = 'inline-block';
setStatus('🤖 AI đang tính toán (Minimax)...', 'status-ai');

// Gọi AI qua fetch (server tính xong mới trả về)
await api('/ai_move', {});
aiThinking = false;
document.getElementById('ai-spinner').style.display = 'none';

await refreshBoard();
}

// ══════════════════════════════════════════════════════════════
// ACTIONS
// ══════════════════════════════════════════════════════════════
async function newGame() {
if (aiThinking) return;
selectedSquare = null;
legalTargets   = [];
await api('/new_game', {});
await refreshBoard();

// Nếu player chọn đen → AI đi trước
const stateData = await api('/state');
if (stateData.ai_should_move) {
    aiThinking = true;
    document.getElementById('ai-spinner').style.display = 'inline-block';
    setStatus('🤖 AI đang tính toán...', 'status-ai');
    await api('/ai_move', {});
    aiThinking = false;
    document.getElementById('ai-spinner').style.display = 'none';
    await refreshBoard();
}
}

async function undoMove() {
if (aiThinking) return;
selectedSquare = null;
legalTargets   = [];
await api('/undo', {});
await refreshBoard();
}

async function setColor(color) {
if (aiThinking) return;
selectedSquare = null;
legalTargets   = [];
const data = await api('/set_color', { color });
await refreshBoard();
if (data.ai_should_move) {
    aiThinking = true;
    document.getElementById('ai-spinner').style.display = 'inline-block';
    setStatus('🤖 AI đang tính toán...', 'status-ai');
    await api('/ai_move', {});
    aiThinking = false;
    document.getElementById('ai-spinner').style.display = 'none';
    await refreshBoard();
}
}

async function setDepth(d) {
await api('/set_depth', { depth: d });
}

// ══════════════════════════════════════════════════════════════
// UI UPDATES
// ══════════════════════════════════════════════════════════════
function setStatus(msg, cls) {
const el = document.getElementById('status-text');
el.textContent = msg;
el.className = 'status-text ' + cls;
}

function updateStatusUI(msg, cls) {
if (msg) setStatus(msg, cls || 'status-ok');
}

function updateHistoryUI(history) {
if (!history || history.length === 0) {
    document.getElementById('history-empty').style.display = 'block';
    document.getElementById('history-table').style.display = 'none';
    return;
}
document.getElementById('history-empty').style.display = 'none';
document.getElementById('history-table').style.display = 'table';

const tbody = document.getElementById('history-body');
tbody.innerHTML = '';
for (let i = 0; i < history.length; i += 2) {
    const n  = Math.floor(i / 2) + 1;
    const w  = history[i]   || '';
    const b  = history[i+1] || '';
    const tr = document.createElement('tr');
    tr.innerHTML = `
    <td class="move-num">${n}.</td>
    <td class="move-white">${w}</td>
    <td class="move-black">${b}</td>`;
    tbody.appendChild(tr);
}
// Auto scroll xuống cuối
const scroll = document.getElementById('history-scroll');
scroll.scrollTop = scroll.scrollHeight;
}

function updateStatsUI(stats) {
const el = document.getElementById('stats-content');
if (!stats) {
    el.innerHTML = '<div class="empty-hint">Chờ AI tính toán...</div>';
    return;
}
const scoreClass = stats.score > 0 ? 'stat-pos' : stats.score < 0 ? 'stat-neg' : 'stat-val';
const scoreSign  = stats.score > 0 ? '+' : '';
el.innerHTML = `
    <div class="stat-row">
    <span class="stat-label">Độ sâu tìm kiếm</span>
    <span class="stat-val">${stats.depth}</span>
    </div>
    <div class="stat-row">
    <span class="stat-label">Điểm đánh giá</span>
    <span class="${scoreClass}">${scoreSign}${stats.score} cp</span>
    </div>
    <div class="stat-row">
    <span class="stat-label">Nodes đã duyệt</span>
    <span class="stat-val">${stats.nodes.toLocaleString()}</span>
    </div>
    <div class="stat-row">
    <span class="stat-label">Thời gian</span>
    <span class="stat-val">${stats.elapsed.toFixed(3)}s</span>
    </div>
    <div class="stat-row">
    <span class="stat-label" style="font-size:10px">cp=centipawns | +Trắng tốt | −Đen tốt</span>
    </div>`;
}
</script>
</body>
</html>
"""

# ══════════════════════════════════════════════════════════════
# GAME STATE — giữ nguyên tên biến từ ClickToMoveUI Colab
# ══════════════════════════════════════════════════════════════
class GameState:
    def __init__(self):
        self.board           = chess.Board()
        self.player_color    = chess.WHITE
        self.ai_depth        = 2
        self.move_history    = []
        self.last_move       = None
        self.game_over       = False
        self.last_ai_stats   = None   # (score, nodes, elapsed, depth)

    # ── Giữ nguyên logic _get_captured từ ClickToMoveUI ───────────
    def get_captured(self):
        start = chess.Board()
        sym = {
            chess.QUEEN: '♛', chess.ROOK: '♜', chess.BISHOP: '♝',
            chess.KNIGHT: '♞', chess.PAWN: '♟'
        }
        cw = cb = ''
        for pt in [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN]:
            lost_b = len(start.pieces(pt, chess.BLACK)) - len(self.board.pieces(pt, chess.BLACK))
            lost_w = len(start.pieces(pt, chess.WHITE)) - len(self.board.pieces(pt, chess.WHITE))
            cw += sym[pt] * lost_b
            cb += sym[pt] * lost_w
        return (cw or '—'), (cb or '—')

    # ── Giữ nguyên logic _update_status từ ClickToMoveUI ──────────
    def get_status(self):
        if self.board.is_checkmate():
            winner = 'Trắng' if self.board.turn == chess.BLACK else 'Đen'
            return f'🏆 {winner} THẮNG! Chiếu hết!', 'status-err'
        elif self.board.is_stalemate():
            return '🤝 Hòa! (Stalemate)', 'status-warn'
        elif self.board.is_insufficient_material():
            return '🤝 Hòa! (Thiếu quân)', 'status-warn'
        elif self.board.is_repetition(3):
            return '🤝 Hòa! (Lặp 3 lần)', 'status-warn'
        elif self.board.is_check():
            side = 'Trắng' if self.board.turn == chess.WHITE else 'Đen'
            return f'⚠️ Chiếu! Lượt {side}', 'status-err'
        else:
            if self.board.turn == self.player_color:
                return '🟢 Lượt của bạn — Click quân cờ!', 'status-ok'
            else:
                return '🤖 AI đang suy nghĩ...', 'status-ai'

    def get_stats_dict(self):
        if self.last_ai_stats is None:
            return None
        score, nodes, elapsed, depth = self.last_ai_stats
        return {'score': score, 'nodes': nodes, 'elapsed': elapsed, 'depth': depth}

    # ── Giữ nguyên logic _ai_move từ ClickToMoveUI ─────────────────
    def ai_move(self):
        move, score, nodes, elapsed = get_best_move(self.board, depth=self.ai_depth)
        if move is None:
            self.game_over = True
            return False

        san = self.board.san(move)
        self.board.push(move)
        self.last_move = move
        self.move_history.append(san)
        self.last_ai_stats = (score, nodes, elapsed, self.ai_depth)

        if self.board.is_game_over():
            self.game_over = True
        return True

    # ── Giữ nguyên logic _on_undo từ ClickToMoveUI ─────────────────
    def undo(self):
        n = min(2, len(self.board.move_stack))
        if n == 0:
            return False
        for _ in range(n):
            self.board.pop()
            if self.move_history:
                self.move_history.pop()
        self.last_move     = self.board.peek() if self.board.move_stack else None
        self.game_over     = False
        self.last_ai_stats = None
        return True


# Singleton game state
gs = GameState()


# ══════════════════════════════════════════════════════════════
# FLASK ROUTES — thay thế colab_output.register_callback
# ══════════════════════════════════════════════════════════════

def make_board_svg(selected=None, legal_targets=None):
    """Tạo SVG bàn cờ với highlight — giữ nguyên logic _render_board."""
    fill = {}

    if gs.last_move:
        fill[gs.last_move.from_square] = '#aed6f1'  # COLOR_LAST_FROM
        fill[gs.last_move.to_square]   = '#2980b9'  # COLOR_LAST_TO

    if gs.board.is_check():
        king_sq = gs.board.king(gs.board.turn)
        if king_sq is not None:
            fill[king_sq] = '#e74c3c'               # COLOR_CHECK

    if selected is not None:
        fill[selected] = '#f1c40f'                  # COLOR_SELECTED
        for sq in (legal_targets or []):
            fill[sq] = ('#e67e22'                   # COLOR_CAPTURE
                        if gs.board.piece_at(sq)
                        else '#B7E892')             # COLOR_LEGAL

    return chess.svg.board(
        gs.board,
        flipped=(gs.player_color == chess.BLACK),
        lastmove=gs.last_move,
        fill=fill,
        size=420,
    )


def board_response(selected=None, legal_targets=None):
    """Trả về JSON gồm SVG + trạng thái để JS render."""
    cw, cb = gs.get_captured()
    status_msg, status_cls = gs.get_status()
    return jsonify({
        'svg':      make_board_svg(selected, legal_targets),
        'captured': f'Trắng ăn: {cw}   |   Đen ăn: {cb}',
        'history':  gs.move_history,
        'stats':    gs.get_stats_dict(),
        'status':   status_msg,
        'status_class': status_cls,
        'game_over': gs.game_over,
    })


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/board')
def board_endpoint():
    selected     = request.args.get('selected', type=int)
    legal_raw    = request.args.get('legal', '')
    legal_targets = [int(x) for x in legal_raw.split(',') if x] if legal_raw else []
    return board_response(selected, legal_targets)


@app.route('/state')
def state_endpoint():
    return jsonify({
        'flipped':       gs.player_color == chess.BLACK,
        'ai_should_move': (not gs.game_over and gs.board.turn != gs.player_color),
        'game_over':     gs.game_over,
    })


@app.route('/select', methods=['POST'])
def select_endpoint():
    """Kiểm tra ô click: có quân mình không, trả về legal_targets."""
    data   = request.json
    square = data['square']

    if gs.game_over or gs.board.turn != gs.player_color:
        return jsonify({'ok': False})

    piece = gs.board.piece_at(square)
    if piece is None or piece.color != gs.player_color:
        return jsonify({'ok': False, 'own_piece': False})

    legal_from = [m for m in gs.board.legal_moves if m.from_square == square]
    if not legal_from:
        return jsonify({'ok': False, 'own_piece': True})

    targets = [m.to_square for m in legal_from]
    return jsonify({
        'ok':          True,
        'own_piece':   True,
        'legal_targets': targets,
        'square_name': chess.square_name(square).upper(),
        'piece_type': piece.symbol().lower(),  # 'p','n','b','r','q','k'
    })


@app.route('/move', methods=['POST'])
def move_endpoint():
    """Thực hiện nước đi người chơi — hỗ trợ chọn quân phong cấp."""
    data    = request.json
    from_sq = data['from_sq']
    to_sq   = data['to_sq']
    promotion = data.get('promotion', None)

    if gs.game_over or gs.board.turn != gs.player_color:
        return jsonify({'ok': False})

    move = None
    for m in gs.board.legal_moves:
        if m.from_square == from_sq and m.to_square == to_sq:
            if m.promotion:
                # Nếu có promotion, kiểm tra loại quân
                if promotion:
                    promo_map = {'q': chess.QUEEN, 'r': chess.ROOK, 'b': chess.BISHOP, 'n': chess.KNIGHT}
                    if m.promotion == promo_map.get(promotion):
                        move = m
                        break
                else:
                    # Nếu không gửi promotion, mặc định là Hậu
                    if m.promotion == chess.QUEEN:
                        move = m
                        break
            else:
                move = m
                break

    if move is None:
        for m in gs.board.legal_moves:
            if m.from_square == from_sq and m.to_square == to_sq:
                move = m
                break

    if move is None:
        return jsonify({'ok': False})

    san = gs.board.san(move)
    gs.board.push(move)
    gs.last_move = move
    gs.move_history.append(san)

    if gs.board.is_game_over():
        gs.game_over = True

    return jsonify({'ok': True, 'san': san, 'game_over': gs.game_over})


@app.route('/ai_move', methods=['POST'])
def ai_move_endpoint():
    """Gọi AI — giữ nguyên logic _ai_move từ ClickToMoveUI."""
    if gs.game_over or gs.board.turn == gs.player_color:
        return jsonify({'ok': False})

    gs.ai_move()
    return jsonify({'ok': True, 'game_over': gs.game_over})


@app.route('/new_game', methods=['POST'])
def new_game_endpoint():
    """Reset ván — giữ nguyên logic _on_new_game."""
    gs.board         = chess.Board()
    gs.move_history  = []
    gs.game_over     = False
    gs.last_move     = None
    gs.last_ai_stats = None
    return jsonify({'ok': True, 'ai_should_move': gs.board.turn != gs.player_color})


@app.route('/undo', methods=['POST'])
def undo_endpoint():
    """Hoàn tác — giữ nguyên logic _on_undo."""
    gs.undo()
    return jsonify({'ok': True})


@app.route('/set_color', methods=['POST'])
def set_color_endpoint():
    data  = request.json
    color = data['color']
    gs.player_color = chess.WHITE if color == 'white' else chess.BLACK
    ai_should = (not gs.game_over and gs.board.turn != gs.player_color)
    return jsonify({'ok': True, 'ai_should_move': ai_should})


@app.route('/set_depth', methods=['POST'])
def set_depth_endpoint():
    data = request.json
    gs.ai_depth = int(data['depth'])
    return jsonify({'ok': True})


# ══════════════════════════════════════════════════════════════
# CLASS ClickToMoveUI — giữ nguyên tên, chỉ thay run()
# ══════════════════════════════════════════════════════════════
class ClickToMoveUI:
    """
    Wrapper class giữ nguyên tên ClickToMoveUI.
    Thay vì display(self.root) → chạy Flask + mở browser.
    """
    def run(self):
        port = 5678
        url  = f'http://127.0.0.1:{port}'
        print(f'Mở browser tại: {url}')

        # Mở browser sau 1 giây (đợi Flask khởi động)
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

        # Chạy Flask (blocking)
        app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False)