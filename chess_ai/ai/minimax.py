import math
import time
import chess
import random

from game.game_logic import evaluate
# ── SWITCH CHỌN THUẬT TOÁN ────────────────────────────────────────────────────
# True  = V2: Alpha-Beta Pruning (nhanh hơn, dùng cho production)
# False = V1: Minimax thuần túy  (chậm hơn, dùng để benchmark so sánh)
USE_ALPHA_BETA = True
#   Nguyên lý:
#   - Bên MAX (AI - Trắng): LUÔN chọn nước có điểm CAO NHẤT
#   - Bên MIN (đối thủ - Đen): LUÔN chọn nước có điểm THẤP NHẤT
#   - Giả định: đối thủ luôn đi nước TỐT NHẤT cho họ (tệ nhất cho ta)
#
#   Ví dụ depth=2:
#     AI xem xét: "Nếu tôi đi nước A,
#                  đối thủ sẽ đi nước tốt nhất của họ là A1,
#                  kết quả là điểm X.
#                  Nếu tôi đi nước B, kết quả là Y.
#                  Tôi chọn max(X, Y)."
#
# ĐỘ PHỨC TẠP:
#   O(b^d) với b=branching factor (~30 nước/lượt), d=depth
#   depth=2: 30^2 = 900 nodes
#   depth=3: 30^3 = 27,000 nodes
#   depth=4: 30^4 = 810,000 nodes  ← rất chậm!
#   (Version 2 sẽ cắt tỉa để giảm mạnh)

# Biến đếm số node đã duyệt (dùng list để có thể sửa trong hàm đệ quy)
# Lý do dùng list thay vì int: Python không cho sửa biến int ở scope ngoài trong hàm đệ quy
nodes_visited = [0]   # Số node đã đi vào (kể cả bị cắt tỉa)
nodes_pruned  = [0]   # Số node bị cắt tỉa (chỉ có trong V2, luôn 0 ở V1)

# ─────────────────────────────────────────────────────────────────────────────
# V2 extras: move ordering + transposition table + quiescence + anti-loop
# ─────────────────────────────────────────────────────────────────────────────

# Transposition Table (TT)
# - Key: board.fen() theo yêu cầu (bao gồm side to move, castling, ep, halfmove/fullmove)
# - Value: (depth, score, flag)
#   - depth: độ sâu đã tính (depth còn lại ở node)
#   - score: điểm minimax từ góc nhìn Trắng (giống evaluate)
#   - flag : loại node (EXACT / LOWERBOUND / UPPERBOUND)
TT = {}
TT_EXACT = 0
TT_LOWER = 1
TT_UPPER = 2

# Giá trị quân cho move ordering (không ảnh hưởng evaluate, chỉ để xếp nước)
_MV_VAL = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20000,
}


def _recent_fens(board: chess.Board, plies: int = 10) -> set:
    """
    Lưu các FEN gần đây (6–10 ply) để phạt nước quay lại thế cờ cũ (anti-loop).
    Triển khai bằng pop/push để không tạo board copy (nhanh hơn deepcopy).
    """
    fens = {board.fen()}
    popped = []
    n = min(plies, len(board.move_stack))
    for _ in range(n):
        popped.append(board.pop())
        fens.add(board.fen())
    for mv in reversed(popped):
        board.push(mv)
    return fens


def _move_order_key(board: chess.Board, move: chess.Move):
    """
    Move ordering (ưu tiên):
    1) Ăn quân
    2) Chiếu
    3) Phong cấp
    4) Nước thường

    Trả về tuple để sort giảm dần (reverse=True).
    """
    is_capture = board.is_capture(move)          # ưu tiên 1: ăn quân
    gives_check = board.gives_check(move)        # ưu tiên 2: chiếu
    is_promo = (move.promotion is not None)      # ưu tiên 3: phong cấp

    # Nhóm ưu tiên theo yêu cầu
    if is_capture:
        group = 3
    elif gives_check:
        group = 2
    elif is_promo:
        group = 1
    else:
        group = 0

    # Tie-break cho captures: MVV-LVA đơn giản (nạn nhân lớn, quân tấn công nhỏ)
    capture_score = 0
    if is_capture:
        victim = board.piece_at(move.to_square)
        if victim is None and board.is_en_passant(move):
            victim_val = _MV_VAL[chess.PAWN]
        else:
            victim_val = _MV_VAL.get(victim.piece_type, 0) if victim else 0
        attacker = board.piece_at(move.from_square)
        attacker_val = _MV_VAL.get(attacker.piece_type, 0) if attacker else 0
        capture_score = victim_val - attacker_val

    promo_score = _MV_VAL.get(move.promotion, 0) if is_promo else 0

    return (group, capture_score, promo_score)


def _ordered_moves(board: chess.Board):
    """Trả về list nước đi đã được sắp xếp theo heuristic move ordering."""
    moves = list(board.legal_moves)
    # reverse=True: tuple key càng lớn càng được xét trước → alpha-beta cắt tỉa tốt hơn
    moves.sort(key=lambda m: _move_order_key(board, m), reverse=True)
    return moves


def _quiescence(board: chess.Board, is_maximizing: bool, alpha: float, beta: float) -> int:
    """
    Quiescence search: khi hết depth, vẫn xét tiếp các nước ăn quân để giảm horizon effect.
    Chỉ mở rộng CAPTURES (theo yêu cầu).
    """
    nodes_visited[0] += 1

    stand_pat = evaluate(board)  # điểm "đứng yên" nếu không mở rộng nữa
    if is_maximizing:
        if stand_pat >= beta:
            return int(beta)
        if stand_pat > alpha:
            alpha = stand_pat
    else:
        if stand_pat <= alpha:
            return int(alpha)
        if stand_pat < beta:
            beta = stand_pat

    # Chỉ xét nước ăn quân (captures). Dùng ordering để thử "ăn ngon" trước.
    moves = [m for m in _ordered_moves(board) if board.is_capture(m)]
    if not moves:
        return int(stand_pat)

    if is_maximizing:
        best = stand_pat
        for move in moves:
            board.push(move)
            score = _quiescence(board, False, alpha, beta)
            board.pop()

            if score > best:
                best = score
            if best > alpha:
                alpha = best
            if alpha >= beta:
                break
        return int(best)
    else:
        best = stand_pat
        for move in moves:
            board.push(move)
            score = _quiescence(board, True, alpha, beta)
            board.pop()

            if score < best:
                best = score
            if best < beta:
                beta = best
            if alpha >= beta:
                break
        return int(best)


def minimax(board: chess.Board, depth: int, is_maximizing: bool) -> int:
    """
    Thuật toán Minimax thuần túy (KHÔNG có Alpha-Beta Pruning).

    Tham số:
        board          : trạng thái bàn cờ hiện tại
        depth          : độ sâu còn lại cần tìm kiếm
                        depth=0 → dừng lại và đánh giá ngay
        is_maximizing  : True nếu đây là lượt của MAX (Trắng muốn điểm cao)
                        False nếu đây là lượt của MIN (Đen muốn điểm thấp)

    Trả về:
        int: điểm số tốt nhất có thể đạt được từ vị trí này
    """
    # Đếm số node đã thăm để theo dõi hiệu suất
    nodes_visited[0] += 1

    # --- Điều kiện dừng đệ quy (Base Case) ---
    # Dừng khi: đã đạt độ sâu tối đa HOẶC trò chơi đã kết thúc
    if depth == 0 or board.is_game_over():
        # Gọi hàm đánh giá để lấy điểm của vị trí này
        return evaluate(board)

    # --- Lấy tất cả nước đi hợp lệ ---
    # board.legal_moves là generator của chess.Move objects
    legal_moves = list(board.legal_moves)

    if is_maximizing:
        # ----- NODE MAX: Trắng đang đi, muốn điểm CAO nhất -----
        best_score = -math.inf  # Khởi tạo = âm vô cực (chưa tìm được gì)

        for move in legal_moves:
            # Thực hiện nước đi (thay đổi trạng thái board)
            board.push(move)

            # Đệ quy: sau khi Trắng đi, đến lượt Đen (is_maximizing=False)
            score = minimax(board, depth - 1, False)

            # Hoàn tác nước đi (quan trọng! phải pop để thử nước khác)
            board.pop()

            # Trắng chọn nước có điểm CAO nhất
            best_score = max(best_score, score)

        return best_score  # Trả về điểm tốt nhất tìm được

    else:
        # ----- NODE MIN: Đen đang đi, muốn điểm THẤP nhất -----
        best_score = math.inf  # Khởi tạo = dương vô cực

        for move in legal_moves:
            board.push(move)

            # Đệ quy: sau khi Đen đi, đến lượt Trắng (is_maximizing=True)
            score = minimax(board, depth - 1, True)

            board.pop()

            # Đen chọn nước có điểm THẤP nhất (tệ nhất cho Trắng)
            best_score = min(best_score, score)

        return best_score


def get_best_move(board: chess.Board, depth: int = 2):
    """
    Tìm nước đi tốt nhất cho bên đang đến lượt.

    Đây là hàm "wrapper" gọi minimax() cho từng nước đi ở tầng 1,
    sau đó chọn nước có điểm tốt nhất.

    Tham số:
        board : trạng thái bàn cờ hiện tại
        depth : độ sâu tìm kiếm (mặc định 2)
                depth=2: ~1 giây | depth=3: ~10-30 giây (chậm!)

    Trả về:
        tuple: (nước_đi_tốt_nhất, điểm_tốt_nhất, số_node_đã_duyệt, thời_gian)
    """
    # NOTE:
    # - Hàm này là phiên bản V1 (minimax thuần).
    # - Ở cuối file có V2 (alpha-beta) định nghĩa lại `get_best_move()` cùng chữ ký
    #   để UI không cần đổi gì. Python sẽ dùng định nghĩa SAU CÙNG.
    # Reset bộ đếm
    nodes_visited[0] = 0
    start_time = time.time()  # Bắt đầu đếm giờ

    # Xác định AI đang đi màu gì
    # board.turn == chess.WHITE nghĩa là đến lượt Trắng
    is_white = (board.turn == chess.WHITE)

    best_move = None                                           # Nước đi tốt nhất
    best_score = -math.inf if is_white else math.inf          # Điểm tốt nhất

    # Duyệt qua tất cả nước đi hợp lệ ở tầng 1 (root level)
    for move in board.legal_moves:
        # Thực hiện nước đi thử
        board.push(move)

        # Gọi minimax cho phần còn lại của cây (depth-1 tầng còn lại)
        # Sau khi AI đi, đến lượt đối thủ → đảo ngược is_maximizing
        score = minimax(board, depth - 1, not is_white)

        # Hoàn tác nước đi
        board.pop()

        # Cập nhật nước đi tốt nhất
        if is_white:
            # Trắng muốn điểm CAO nhất
            if score > best_score:
                best_score = score
                best_move = move
        else:
            # Đen muốn điểm THẤP nhất
            if score < best_score:
                best_score = score
                best_move = move

    elapsed = time.time() - start_time  # Thời gian tính toán

    return best_move, best_score, nodes_visited[0], elapsed




# ══════════════════════════════════════════════════════════════════════════════
# V2: MINIMAX + ALPHA-BETA PRUNING
# ══════════════════════════════════════════════════════════════════════════════
#
# ALPHA-BETA PRUNING LÀ GÌ?
# ─────────────────────────
# Ý tưởng: Bỏ qua các nhánh mà chắc chắn không ảnh hưởng đến kết quả cuối.
#
# Hai biến quan trọng:
#
#   alpha (α): Điểm TỐT NHẤT mà bên MAX (Trắng) đã tìm được ĐẾN LÚC NÀY
#              trên đường đi từ gốc đến node hiện tại.
#              → Trắng sẽ KHÔNG CHẤP NHẬN điểm nào thấp hơn alpha.
#              → Khởi tạo = -∞ (chưa tìm được gì)
#
#   beta  (β): Điểm TỐT NHẤT mà bên MIN (Đen) đã tìm được ĐẾN LÚC NÀY
#              trên đường đi từ gốc đến node hiện tại.
#              → Đen sẽ KHÔNG CHẤP NHẬN điểm nào cao hơn beta.
#              → Khởi tạo = +∞ (chưa tìm được gì)
#
# ĐIỀU KIỆN CẮT TỈA (Pruning condition):
#   Tại node MAX: nếu best_score >= beta  → CẮT (Beta cutoff)
#       Vì: Trắng đã tìm được nước ≥ beta, nhưng tổ tiên MIN sẽ không
#           bao giờ chọn nhánh này (vì Đen đã có lựa chọn tốt hơn).
#
#   Tại node MIN: nếu best_score <= alpha → CẮT (Alpha cutoff)
#       Vì: Đen đã tìm được nước ≤ alpha, nhưng tổ tiên MAX sẽ không
#           bao giờ chọn nhánh này (vì Trắng đã có lựa chọn tốt hơn).
#
# VÍ DỤ TRỰC QUAN:
#   MAX đang xét nhánh A, tìm được điểm 5.
#   Đang xét nhánh B, nhánh con đầu trả về 3.
#   → MIN (trong nhánh B) sẽ chọn ≤ 3.
#   → MAX biết nhánh B sẽ cho kết quả ≤ 3 < 5 (đã có từ nhánh A).
#   → MAX không cần xét các nhánh con còn lại của B → CẮT.

def minimax_ab(board: chess.Board,
            depth: int,
            is_maximizing: bool,
            alpha: float,
            beta: float) -> int:
    """
    Minimax với Alpha-Beta Pruning — Version 2.

    Tham số:
        board          : trạng thái bàn cờ hiện tại
        depth          : độ sâu còn lại (giảm dần đến 0)
        is_maximizing  : True = lượt MAX (Trắng) | False = lượt MIN (Đen)
        alpha          : ngưỡng tốt nhất của MAX (từ gốc đến đây)
                        → Tăng dần khi MAX tìm được nước tốt hơn
        beta           : ngưỡng tốt nhất của MIN (từ gốc đến đây)
                        → Giảm dần khi MIN tìm được nước tốt hơn

    Trả về:
        int: điểm tốt nhất từ vị trí này (sau khi đã cắt tỉa)

    Bất biến (invariant) quan trọng: alpha < beta
        Nếu alpha >= beta → cắt tỉa ngay, không xét thêm.
    """
    # ── Đếm số node đã đi vào ─────────────────────────────────────
    nodes_visited[0] += 1

    # ── Điều kiện dừng ────────────────────────────────────────────
    # - Depth=0: chuyển sang quiescence (xét captures) để giảm horizon effect
    # - Game over: evaluate() đã xử lý checkmate/draw
    if depth == 0:
        # Hết depth: dùng quiescence để tránh "ăn xong bị ăn lại" ngay sau khi dừng
        return _quiescence(board, is_maximizing, alpha, beta)
    if board.is_game_over():
        return evaluate(board)

    # ── Transposition Table lookup ────────────────────────────────
    # Dùng FEN làm key theo yêu cầu.
    fen = board.fen()  # key TT theo yêu cầu (đơn giản, dễ debug; chậm hơn hash chuyên dụng)
    tt_entry = TT.get(fen)
    if tt_entry is not None:
        tt_depth, tt_score, tt_flag = tt_entry
        if tt_depth >= depth:
            # Nếu đã có kết quả ở depth >= hiện tại thì có thể dùng lại ngay
            if tt_flag == TT_EXACT:
                return tt_score
            if tt_flag == TT_LOWER:
                alpha = max(alpha, tt_score)
            elif tt_flag == TT_UPPER:
                beta = min(beta, tt_score)
            if alpha >= beta:
                return tt_score

    # ── Lấy tất cả nước đi hợp lệ ────────────────────────────────
    legal_moves = _ordered_moves(board)  # move ordering: capture > check > promo > quiet

    alpha_orig = alpha  # lưu cửa sổ ban đầu để set TT flag (EXACT/LOWER/UPPER)
    beta_orig = beta

    # ═════════════════════════════════════════════════════════════
    # NHÁNH MAX: Trắng đang đi, muốn điểm CAO NHẤT
    # ═════════════════════════════════════════════════════════════
    if is_maximizing:
        best_score = -math.inf  # Chưa tìm được nước nào, khởi tạo = -∞

        for move in legal_moves:
            # Thực hiện nước đi thử
            board.push(move)

            # Đệ quy: sau Trắng đến Đen (is_maximizing đảo, alpha/beta truyền xuống)
            score = minimax_ab(board, depth - 1, False, alpha, beta)

            # Hoàn tác để thử nước tiếp theo
            board.pop()

            # Cập nhật điểm tốt nhất của MAX
            best_score = max(best_score, score)

            # ── Cập nhật alpha ─────────────────────────────────
            # alpha = điểm tốt nhất MAX đã đảm bảo được đến lúc này
            # Nếu best_score > alpha: MAX vừa tìm được nước tốt hơn trước
            alpha = max(alpha, best_score)

            # ── KIỂM TRA CẮT TỈA (Beta Cutoff) ────────────────
            # Nếu best_score >= beta:
            #   → Trắng đã tìm được nước cho điểm ≥ beta
            #   → Đen (tổ tiên MIN) đã có lựa chọn tốt hơn ở nhánh khác
            #     (lựa chọn đó cho điểm ≤ beta, tức tệ hơn cho Trắng)
            #   → Đen sẽ KHÔNG BAO GIỜ chọn đi vào nhánh này
            #   → Bỏ qua tất cả nước còn lại: BREAK ngay!
            if best_score >= beta:
                # Tăng đếm số node bị cắt (ước tính: còn lại bao nhiêu nước chưa xét)
                remaining = len(legal_moves) - legal_moves.index(move) - 1
                nodes_pruned[0] += remaining  # Ước tính thô (thực tế ít hơn)
                break  # ← Đây là "beta cutoff" (hay "fail-high")

        # ── TT store ─────────────────────────────────────────────
        # Flag phụ thuộc vào mối quan hệ với cửa sổ alpha/beta ban đầu.
        if best_score <= alpha_orig:
            flag = TT_UPPER
        elif best_score >= beta_orig:
            flag = TT_LOWER
        else:
            flag = TT_EXACT
        TT[fen] = (depth, int(best_score), flag)  # store kết quả node vào TT

        return best_score

    # ═════════════════════════════════════════════════════════════
    # NHÁNH MIN: Đen đang đi, muốn điểm THẤP NHẤT
    # ═════════════════════════════════════════════════════════════
    else:
        best_score = math.inf   # Chưa tìm được nước nào, khởi tạo = +∞

        for move in legal_moves:
            # Thực hiện nước đi thử
            board.push(move)

            # Đệ quy: sau Đen đến Trắng (is_maximizing đảo, alpha/beta truyền xuống)
            score = minimax_ab(board, depth - 1, True, alpha, beta)

            # Hoàn tác để thử nước tiếp theo
            board.pop()

            # Cập nhật điểm tốt nhất của MIN
            best_score = min(best_score, score)

            # ── Cập nhật beta ──────────────────────────────────
            # beta = điểm tốt nhất MIN đã đảm bảo được đến lúc này
            # Nếu best_score < beta: MIN vừa tìm được nước tốt hơn trước
            beta = min(beta, best_score)

            # ── KIỂM TRA CẮT TỈA (Alpha Cutoff) ───────────────
            # Nếu best_score <= alpha:
            #   → Đen đã tìm được nước cho điểm ≤ alpha
            #   → Trắng (tổ tiên MAX) đã có lựa chọn tốt hơn ở nhánh khác
            #     (lựa chọn đó cho điểm ≥ alpha, tức tốt hơn cho Trắng)
            #   → Trắng sẽ KHÔNG BAO GIỜ chọn đi vào nhánh này
            #   → Bỏ qua tất cả nước còn lại: BREAK ngay!
            if best_score <= alpha:
                remaining = len(legal_moves) - legal_moves.index(move) - 1
                nodes_pruned[0] += remaining  # Ước tính thô
                break  # ← Đây là "alpha cutoff" (hay "fail-low")

        # ── TT store ─────────────────────────────────────────────
        if best_score <= alpha_orig:
            flag = TT_UPPER
        elif best_score >= beta_orig:
            flag = TT_LOWER
        else:
            flag = TT_EXACT
        TT[fen] = (depth, int(best_score), flag)  # store kết quả node vào TT

        return best_score


# ══════════════════════════════════════════════════════════════════════════════
# HÀM CHÍNH — GIỮ NGUYÊN CHỮ KÝ, TƯƠNG THÍCH HOÀN TOÀN VỚI ui.py
# ══════════════════════════════════════════════════════════════════════════════

def get_best_move(board: chess.Board, depth: int = 2):
    """
    Tìm nước đi tốt nhất — chữ ký KHÔNG ĐỔI so với V1.

    Tự động chọn thuật toán dựa trên biến USE_ALPHA_BETA ở đầu file:
    True  → gọi minimax_ab() với alpha=-∞, beta=+∞
    False → gọi minimax()    (V1 thuần túy)

    Tham số:
        board : trạng thái bàn cờ hiện tại
        depth : độ sâu tìm kiếm (mặc định 2)

    Trả về:
        tuple: (best_move, best_score, nodes_visited, elapsed)
            ← GIỐNG HỆT V1, ui.py không cần sửa gì
    """
    # ── Reset bộ đếm trước mỗi lần tìm kiếm ──────────────────────
    nodes_visited[0] = 0
    nodes_pruned[0]  = 0
    start_time       = time.time()
    TT.clear()  # TT chỉ sống trong 1 lần tìm kiếm (mỗi lượt), tránh phình bộ nhớ

    # ── Xác định AI đang đi màu nào ──────────────────────────────
    # board.turn == chess.WHITE → Trắng đang đến lượt
    is_white = (board.turn == chess.WHITE)

    # ── Khởi tạo kết quả ─────────────────────────────────────────
    best_move  = None
    # MAX (Trắng) muốn tối đa → khởi tạo -∞
    # MIN (Đen)  muốn tối thiểu → khởi tạo +∞
    best_score = -math.inf if is_white else math.inf

    # ── Anti-loop: lưu 6–10 trạng thái gần nhất (FEN) ────────────
    recent_fens = _recent_fens(board, plies=10)  # 6–10 trạng thái gần nhất để phạt loop

    # ── Duyệt tất cả nước đi hợp lệ ở tầng gốc ───────────────────
    best_moves = []
    moves_root = _ordered_moves(board)  # ordering ở root giúp tìm best_move nhanh hơn
    for move in moves_root:

        # Thực hiện nước đi thử nghiệm
        board.push(move)

        # ── GỌI THUẬT TOÁN PHÙ HỢP ───────────────────────────────
        if USE_ALPHA_BETA:
            # V2: truyền alpha=-∞, beta=+∞ ban đầu (cửa sổ mở rộng tối đa)
            # Sau khi tìm được nước đầu tiên, alpha/beta sẽ dần thu hẹp
            # → giúp các nước sau bị cắt tỉa nhiều hơn
            score = minimax_ab(
                board,
                depth - 1,       # Còn lại depth-1 tầng
                not is_white,    # Đảo lượt: AI đi xong thì đến đối thủ
                -math.inf,       # alpha khởi đầu = -∞ (MAX chưa có gì)
                math.inf         # beta  khởi đầu = +∞ (MIN chưa có gì)
            )
        else:
            # V1: minimax thuần túy (để so sánh benchmark)
            score = minimax(
                board,
                depth - 1,
                not is_white
            )

        # Anti-loop (theo yêu cầu): nếu quay lại FEN gần đây thì phạt -20 (từ góc nhìn Trắng).
        if board.fen() in recent_fens:
            # Phạt loop theo yêu cầu: -20cp (góc nhìn Trắng)
            score += (-20 if is_white else 20)

        # Hoàn tác nước đi
        board.pop()

        # ── Cập nhật nước đi tốt nhất ────────────────────────────
        if is_white:
            # Trắng (MAX): chọn nước có điểm CAO nhất
            if score > best_score:
                best_score = score
                best_moves = [move]
            elif score == best_score:
                best_moves.append(move)
        else:
            # Đen (MIN): chọn nước có điểm THẤP nhất
            if score < best_score:
                best_score = score
                best_moves = [move]
            elif score == best_score:
                best_moves.append(move)

    # Random tie-break nếu nhiều nước có cùng điểm (bonus)
    best_move = random.choice(best_moves) if best_moves else None  # tie-break ngẫu nhiên (bonus)

    # ── Tính thời gian ────────────────────────────────────────────
    elapsed = time.time() - start_time

    # ── In thống kê ra console để so sánh V1 vs V2 ───────────────
    algo_name = "Alpha-Beta V2" if USE_ALPHA_BETA else "Minimax V1"
    print(f"\n{'='*50}")
    print(f"  {algo_name} | depth={depth}")
    print(f"{'='*50}")
    print(f"  Nước đi tốt nhất : {best_move}")
    print(f"  Điểm đánh giá    : {best_score:+d} cp")
    print(f"  Nodes đã duyệt   : {nodes_visited[0]:,}")
    if USE_ALPHA_BETA:
        total = nodes_visited[0] + nodes_pruned[0]
        pct   = (nodes_pruned[0] / total * 100) if total > 0 else 0
        print(f"  Nodes bị cắt tỉa : ~{nodes_pruned[0]:,} (~{pct:.1f}% tiết kiệm)")
    print(f"  Thời gian        : {elapsed:.3f}s")
    print(f"{'='*50}\n")

    # ── Trả về đúng format V1 (ui.py không cần sửa gì) ───────────
    return best_move, best_score, nodes_visited[0], elapsed