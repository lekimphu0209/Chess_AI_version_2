import chess
# Đơn vị: centipawn (cp)
#   1 Tốt = 100 cp  (đơn vị cơ sở)
#   1 Mã  = 320 cp  (Mã mạnh hơn 3.2 Tốt)
#   v.v...
#
# Hàm đánh giá Version 1 rất đơn giản:
#   - CHỈ đếm vật chất (số quân và giá trị)
#   - Không quan tâm vị trí quân cờ (sẽ thêm ở Version 3)
#
# Kết quả hàm đánh giá:
#   > 0  → Trắng đang tốt hơn
#   < 0  → Đen đang tốt hơn
#   = 0  → Cân bằng

# Từ điển: loại quân → giá trị (centipawns)
# Vua có giá trị rất lớn để AI không bao giờ "đổi" Vua
PIECE_VALUES = {
    chess.PAWN:   100,    # Tốt
    chess.KNIGHT: 320,    # Mã
    chess.BISHOP: 330,    # Tượng
    chess.ROOK:   500,    # Xe
    chess.QUEEN:  900,    # Hậu
    chess.KING:   20000,  # Vua (không thể mất)
}


def evaluate(board: chess.Board) -> int:
    """
    Hàm đánh giá vị trí bàn cờ — VERSION 2 (material + PST + heuristic cơ bản).

    Tham số:
        board: đối tượng bàn cờ hiện tại (chess.Board)

    Trả về:
        int: điểm số từ góc nhìn của Trắng
            > 0 = Trắng tốt hơn | < 0 = Đen tốt hơn | 0 = cân bằng
    """

    # --- Xử lý các trạng thái kết thúc trước ---

    # Chiếu hết: bên đang đến lượt bị thua
    if board.is_checkmate():
        # Nếu Trắng đang đến lượt mà bị chiếu hết → Trắng thua → điểm rất âm
        if board.turn == chess.WHITE:
            return -99999
        # Ngược lại Đen thua → điểm rất dương (tốt cho Trắng)
        else:
            return 99999

    # Hòa cờ: tất cả các loại hòa đều trả về 0 (không bên nào lợi)
    if (board.is_stalemate()            # Hết nước đi nhưng không bị chiếu
            or board.is_insufficient_material()  # Không đủ quân để chiếu hết
            or board.is_fifty_moves()            # 50 nước không ăn/không đi Tốt
            or board.is_repetition(3)):          # Lặp vị trí 3 lần
        return 0

    # ────────────────────────────────────────────────────────────
    # PST (Piece-Square Table):
    # - Thưởng/phạt vị trí cho Tốt/Mã/Tượng.
    # - Bảng dưới được viết theo "góc nhìn Trắng". Quân Đen sẽ mirror lại ô để tra.
    # - Điểm PST nhỏ (vài chục cp) để material vẫn là yếu tố chính.
    # ────────────────────────────────────────────────────────────
    PST_PAWN = [
          0,   0,   0,   0,   0,   0,   0,   0,
         10,  10,  10, -10, -10,  10,  10,  10,
          5,   5,  10,  20,  20,  10,   5,   5,
          0,   0,   0,  25,  25,   0,   0,   0,
          5,  -5, -10,   0,   0, -10,  -5,   5,
          5,  10,  10, -25, -25,  10,  10,   5,
          0,   0,   0, -10, -10,   0,   0,   0,
          0,   0,   0,   0,   0,   0,   0,   0,
    ]

    PST_KNIGHT = [
        -50, -40, -30, -30, -30, -30, -40, -50,
        -40, -20,   0,   0,   0,   0, -20, -40,
        -30,   0,  10,  15,  15,  10,   0, -30,
        -30,   5,  15,  20,  20,  15,   5, -30,
        -30,   0,  15,  20,  20,  15,   0, -30,
        -30,   5,  10,  15,  15,  10,   5, -30,
        -40, -20,   0,   5,   5,   0, -20, -40,
        -50, -40, -30, -30, -30, -30, -40, -50,
    ]

    PST_BISHOP = [
        -20, -10, -10, -10, -10, -10, -10, -20,
        -10,   5,   0,   0,   0,   0,   5, -10,
        -10,  10,  10,  10,  10,  10,  10, -10,
        -10,   0,  10,  10,  10,  10,   0, -10,
        -10,   5,   5,  10,  10,   5,   5, -10,
        -10,   0,   5,  10,  10,   5,   0, -10,
        -10,   0,   0,   0,   0,   0,   0, -10,
        -20, -10, -10, -10, -10, -10, -10, -20,
    ]

    def pst_value(piece: chess.Piece, square: chess.Square) -> int:
        # Mirror ô với quân Đen để dùng chung PST theo góc nhìn Trắng.
        sq = square if piece.color == chess.WHITE else chess.square_mirror(square)
        if piece.piece_type == chess.PAWN:
            return PST_PAWN[sq]
        if piece.piece_type == chess.KNIGHT:
            return PST_KNIGHT[sq]
        if piece.piece_type == chess.BISHOP:
            return PST_BISHOP[sq]
        return 0

    def game_phase() -> str:
        # Phase = khai cuộc/trung cuộc/tàn cuộc để đổi trọng số heuristic.
        # Dựa trên tổng non-pawn material (nhanh, đủ dùng; không cần ML).
        minor_major = 0
        for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
            minor_major += (len(board.pieces(pt, chess.WHITE)) + len(board.pieces(pt, chess.BLACK))) * PIECE_VALUES[pt]
        if minor_major >= 2600:
            return "opening"
        if minor_major <= 1300:
            return "endgame"
        return "middlegame"

    def center_control_score() -> int:
        # Thưởng 2 phần:
        # - "Chiếm" ô trung tâm (có quân đứng trên ô)
        # - "Kiểm soát" ô trung tâm (số quân đang tấn công ô đó)
        centers = (chess.D4, chess.E4, chess.D5, chess.E5)
        s = 0
        for sq in centers:
            p = board.piece_at(sq)
            if p:
                s += 15 if p.color == chess.WHITE else -15
            s += 4 * (len(board.attackers(chess.WHITE, sq)) - len(board.attackers(chess.BLACK, sq)))
        return s

    def development_score_opening() -> int:
        # Khai cuộc: thưởng/phạt dựa trên "nguyên tắc" (develop + king safety).
        # 1) Phạt minor pieces còn ở ô xuất phát (mất nhịp phát triển).
        s = 0
        start_squares = {
            chess.WHITE: {
                chess.KNIGHT: (chess.B1, chess.G1),
                chess.BISHOP: (chess.C1, chess.F1),
            },
            chess.BLACK: {
                chess.KNIGHT: (chess.B8, chess.G8),
                chess.BISHOP: (chess.C8, chess.F8),
            },
        }
        for color in (chess.WHITE, chess.BLACK):
            sign = 1 if color == chess.WHITE else -1
            for pt, sqs in start_squares[color].items():
                undeveloped = 0
                for sq in sqs:
                    p = board.piece_at(sq)
                    if p is not None and p.piece_type == pt and p.color == color:
                        undeveloped += 1
                s += sign * (-18 * undeveloped)

        # 2) Phạt đi lại cùng 1 quân (minor) trong 10 ply đầu.
        #    Làm bằng cách replay lại move_stack trên bàn cờ khởi đầu để đếm số lần
        #    mỗi "thực thể quân" (token) bị di chuyển.
        max_plies = min(10, len(board.move_stack))
        if max_plies > 0:
            tmp = chess.Board()
            token_id = 1
            sq_to_tok = {}
            for sq, _pc in tmp.piece_map().items():
                sq_to_tok[sq] = token_id
                token_id += 1

            moves_per_tok = {chess.WHITE: {}, chess.BLACK: {}}
            tok_type = {}

            for i in range(max_plies):
                mv = board.move_stack[i]
                mover = tmp.piece_at(mv.from_square)
                if mover is None:
                    tmp.push(mv)
                    continue

                tok = sq_to_tok.get(mv.from_square)
                if tok is None:
                    tok = token_id
                    token_id += 1

                if tok not in tok_type:
                    tok_type[tok] = mover.piece_type

                d = moves_per_tok[mover.color]
                d[tok] = d.get(tok, 0) + 1

                sq_to_tok.pop(mv.from_square, None)
                sq_to_tok.pop(mv.to_square, None)   # nếu có ăn quân thì token ở ô đích bị xóa
                sq_to_tok[mv.to_square] = tok

                tmp.push(mv)

            for color in (chess.WHITE, chess.BLACK):
                sign = 1 if color == chess.WHITE else -1
                for tok, cnt in moves_per_tok[color].items():
                    if tok_type.get(tok) in (chess.KNIGHT, chess.BISHOP):
                        extra = max(0, cnt - 1)
                        # Mỗi lần đi lại thêm = mất nhịp → bị phạt.
                        s += sign * (-12 * extra)

        # 3) Thưởng nhập thành (đơn giản: vua ở g/c).
        wk = board.king(chess.WHITE)
        bk = board.king(chess.BLACK)
        if wk in (chess.G1, chess.C1):
            s += 25
        if bk in (chess.G8, chess.C8):
            s -= 25
        return s

    def king_safety_score(phase: str) -> int:
        # An toàn vua:
        # - Opening/middlegame: vua ở trung tâm thường nguy hiểm hơn.
        # - Endgame: vua hoạt động được, nên phạt nhẹ hơn.
        wk = board.king(chess.WHITE)
        bk = board.king(chess.BLACK)
        if wk is None or bk is None:
            return 0

        def in_center(king_sq: chess.Square) -> bool:
            f = chess.square_file(king_sq)
            r = chess.square_rank(king_sq)
            return (2 <= f <= 5) and (2 <= r <= 5)

        base = 22 if phase != "endgame" else 8
        s = 0
        if in_center(wk):
            s -= base
        if in_center(bk):
            s += base

        if board.is_check():
            s += -12 if board.turn == chess.WHITE else 12
        return s

    phase = game_phase()
    # Trọng số theo phase (thực dụng): khai cuộc ưu tiên develop/center/king safety hơn.
    if phase == "opening":
        w_material, w_pst, w_center, w_dev, w_king = 1.00, 1.20, 1.10, 1.25, 1.15
    elif phase == "middlegame":
        w_material, w_pst, w_center, w_dev, w_king = 1.00, 1.00, 1.00, 0.80, 1.10
    else:
        w_material, w_pst, w_center, w_dev, w_king = 1.05, 0.70, 0.60, 0.30, 0.60

    score_material = 0
    score_pst = 0

    # board.piece_map() trả về dict: {ô → quân}
    # Ví dụ: {chess.E1: Piece(KING, WHITE), chess.D8: Piece(QUEEN, BLACK), ...}
    for square, piece in board.piece_map().items():
        # Lấy giá trị của loại quân này (Tốt=100, Mã=320,...)
        value = PIECE_VALUES[piece.piece_type]

        if piece.color == chess.WHITE:
            score_material += value
            score_pst += pst_value(piece, square)
        else:
            score_material -= value
            score_pst -= pst_value(piece, square)

    score_center = center_control_score()                               # D. Trung tâm
    score_dev = development_score_opening() if phase == "opening" else 0 # C. Khai cuộc/develop
    score_king = king_safety_score(phase)                               # E. An toàn vua

    # Tổng hợp: tất cả vẫn là centipawn (cp) theo góc nhìn Trắng.
    total = (
        w_material * score_material
        + w_pst * score_pst
        + w_center * score_center
        + w_dev * score_dev
        + w_king * score_king
    )

    return int(round(total))