from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

TRACK_REGION_HALF = 260
LOCK_BOX_HALF = 18
INIT_PATCH_HALF = 30
SEARCH_HALF = 135
MIN_TEMPLATE_STD = 5.0
MIN_EDGE_PIXELS = 8
MIN_MATCH_SCORE = 0.34
MIN_REACQUIRE_SCORE = 0.26
MIN_PSR = 4.2
MIN_APPEARANCE_SCORE = 0.30
TOPK_CANDIDATES = 6
TEMPLATE_UPDATE_ALPHA = 0.05
MAX_TARGET_JUMP = 48.0
MAX_REACQUIRE_JUMP = 90.0
MAX_SOFT_LOST = 12


def to_gray(frame_bgr: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)


def _clip_box(
    gray: np.ndarray,
    center: tuple[float, float],
    half_size: int,
) -> tuple[int, int, int, int]:
    h, w = gray.shape
    cx, cy = center
    x1 = max(0, int(round(cx - half_size)))
    y1 = max(0, int(round(cy - half_size)))
    x2 = min(w, int(round(cx + half_size)))
    y2 = min(h, int(round(cy + half_size)))
    return x1, y1, x2, y2


def _extract_patch(gray: np.ndarray, center: tuple[float, float], half_size: int) -> np.ndarray | None:
    x1, y1, x2, y2 = _clip_box(gray, center, half_size)
    if (x2 - x1) < 8 or (y2 - y1) < 8:
        return None
    return gray[y1:y2, x1:x2]


def _preprocess(gray: np.ndarray) -> np.ndarray:
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    return cv2.Canny(blur, 60, 140)


def _patch_quality(gray_patch: np.ndarray) -> tuple[float, int]:
    edge = _preprocess(gray_patch)
    return float(np.std(gray_patch)), int(np.count_nonzero(edge))


def _gray_hist(patch: np.ndarray) -> np.ndarray:
    hist = cv2.calcHist([patch], [0], None, [16], [0, 256])
    cv2.normalize(hist, hist, alpha=1.0, beta=0.0, norm_type=cv2.NORM_L1)
    return hist


def _hist_similarity(h1: np.ndarray, h2: np.ndarray) -> float:
    dist = cv2.compareHist(h1, h2, cv2.HISTCMP_BHATTACHARYYA)
    return float(max(0.0, 1.0 - dist))


def _compute_psr(res: np.ndarray, max_loc: tuple[int, int], guard: int = 6) -> float:
    h, w = res.shape
    x, y = max_loc
    mask = np.ones((h, w), dtype=np.uint8)
    x1 = max(0, x - guard)
    y1 = max(0, y - guard)
    x2 = min(w, x + guard + 1)
    y2 = min(h, y + guard + 1)
    mask[y1:y2, x1:x2] = 0
    side = res[mask == 1]
    if side.size < 10:
        return 0.0
    mu = float(np.mean(side))
    sigma = float(np.std(side)) + 1e-6
    return float((res[y, x] - mu) / sigma)


@dataclass
class TrackerConfig:
    lock_half: int = LOCK_BOX_HALF
    init_half: int = INIT_PATCH_HALF
    search_half: int = SEARCH_HALF
    min_std: float = MIN_TEMPLATE_STD
    min_edge_pixels: int = MIN_EDGE_PIXELS
    min_score: float = MIN_MATCH_SCORE
    min_reacquire_score: float = MIN_REACQUIRE_SCORE
    min_psr: float = MIN_PSR
    min_appearance: float = MIN_APPEARANCE_SCORE
    top_k: int = TOPK_CANDIDATES
    update_alpha: float = TEMPLATE_UPDATE_ALPHA
    max_jump: float = MAX_TARGET_JUMP
    max_reacquire_jump: float = MAX_REACQUIRE_JUMP
    max_soft_lost: int = MAX_SOFT_LOST


class RobustPointTracker:
    """
    全屏预测窗口模板跟踪器：
    1) 在点击点初始化目标模板；
    2) 用速度预测位置并在局部窗口做匹配；
    3) 通过匹配分数和最大跳变限制防止串目标；
    4) 缓慢更新模板以适应外观变化。
    """

    def __init__(self, config: TrackerConfig | None = None) -> None:
        self.config = config or TrackerConfig()
        self.template_anchor: np.ndarray | None = None
        self.template_live: np.ndarray | None = None
        self.hist_anchor: np.ndarray | None = None
        self.hist_live: np.ndarray | None = None
        self.target_center: tuple[float, float] | None = None
        self.velocity: tuple[float, float] = (0.0, 0.0)
        self.locked: bool = False
        self.lost_count: int = 0
        self.last_score: float = 0.0
        self.last_points: int = 0

    def _mark_lost(self) -> None:
        self.lost_count += 1
        self.velocity = (self.velocity[0] * 0.7, self.velocity[1] * 0.7)
        if self.lost_count > self.config.max_soft_lost:
            self.locked = False

    def initialize(self, frame_gray: np.ndarray, center: tuple[float, float]) -> bool:
        patch = _extract_patch(frame_gray, center, self.config.init_half)
        if patch is None:
            self.locked = False
            return False
        std_val, edge_count = _patch_quality(patch)
        if std_val < self.config.min_std or edge_count < self.config.min_edge_pixels:
            self.locked = False
            return False

        self.template_anchor = patch.astype(np.uint8)
        self.template_live = patch.astype(np.uint8)
        self.hist_anchor = _gray_hist(self.template_anchor)
        self.hist_live = _gray_hist(self.template_live)
        self.target_center = center
        self.velocity = (0.0, 0.0)
        self.locked = True
        self.lost_count = 0
        self.last_score = 1.0
        self.last_points = edge_count
        return True

    def update(
        self,
        frame_gray: np.ndarray,
        aim_center: tuple[float, float],
    ) -> tuple[bool, float, float]:
        if not self.locked or self.target_center is None or self.template_live is None or self.template_anchor is None:
            if not self.initialize(frame_gray, aim_center):
                return False, 0.0, 0.0

        lost_mode = self.lost_count > 0
        search_half = int(round(self.config.search_half * (1.8 if lost_mode else 1.0)))
        min_score = self.config.min_reacquire_score if lost_mode else self.config.min_score
        min_psr = self.config.min_psr - 1.0 if lost_mode else self.config.min_psr
        max_jump = self.config.max_reacquire_jump if lost_mode else self.config.max_jump

        pred_center = (
            self.target_center[0] + self.velocity[0],
            self.target_center[1] + self.velocity[1],
        )
        x1, y1, x2, y2 = _clip_box(frame_gray, pred_center, search_half)
        search_gray = frame_gray[y1:y2, x1:x2]
        th, tw = self.template_live.shape
        if search_gray.shape[0] <= th + 2 or search_gray.shape[1] <= tw + 2:
            self._mark_lost()
            return False, 0.0, 0.0

        result_live = cv2.matchTemplate(search_gray, self.template_live, cv2.TM_CCOEFF_NORMED)
        result_anchor = cv2.matchTemplate(search_gray, self.template_anchor, cv2.TM_CCOEFF_NORMED)
        result = 0.68 * result_live + 0.32 * result_anchor

        flat = result.reshape(-1)
        k = max(1, min(self.config.top_k, flat.size))
        top_idx = np.argpartition(flat, -k)[-k:]
        top_idx = top_idx[np.argsort(flat[top_idx])[::-1]]

        best_candidate: tuple[tuple[float, float], float, float, float] | None = None
        best_total = -1.0
        for idx in top_idx:
            row, col = divmod(int(idx), result.shape[1])
            corr = float(result[row, col])
            if corr < min_score - 0.05:
                continue

            cand_center = (x1 + col + tw / 2.0, y1 + row + th / 2.0)
            jump = float(np.hypot(cand_center[0] - self.target_center[0], cand_center[1] - self.target_center[1]))
            if jump > max_jump:
                continue

            cand_patch = _extract_patch(frame_gray, cand_center, self.config.init_half)
            if cand_patch is None or cand_patch.shape != self.template_live.shape:
                continue
            _, edge_count = _patch_quality(cand_patch)
            if edge_count < max(4, self.config.min_edge_pixels // 2):
                continue

            cand_hist = _gray_hist(cand_patch)
            sim_live = _hist_similarity(cand_hist, self.hist_live) if self.hist_live is not None else 0.0
            sim_anchor = _hist_similarity(cand_hist, self.hist_anchor) if self.hist_anchor is not None else 0.0
            appearance = 0.64 * sim_live + 0.36 * sim_anchor
            if appearance < self.config.min_appearance:
                continue

            motion_score = max(0.0, 1.0 - jump / (max_jump + 1e-6))
            total = corr * 0.60 + appearance * 0.30 + motion_score * (0.10 if not lost_mode else 0.05)
            if total > best_total:
                best_total = total
                best_candidate = (cand_center, corr, appearance, jump)

        if best_candidate is None:
            self._mark_lost()
            return False, 0.0, 0.0

        new_center, score, appearance, jump = best_candidate
        result_x = int(round(new_center[0] - tw / 2.0 - x1))
        result_y = int(round(new_center[1] - th / 2.0 - y1))
        result_x = max(0, min(result.shape[1] - 1, result_x))
        result_y = max(0, min(result.shape[0] - 1, result_y))
        psr = _compute_psr(result, (result_x, result_y))
        if score < min_score or psr < min_psr:
            self._mark_lost()
            return False, 0.0, 0.0

        inst_vx = new_center[0] - self.target_center[0]
        inst_vy = new_center[1] - self.target_center[1]
        self.velocity = (
            0.72 * self.velocity[0] + 0.28 * inst_vx,
            0.72 * self.velocity[1] + 0.28 * inst_vy,
        )

        self.target_center = new_center
        self.last_score = 0.75 * score + 0.25 * appearance
        self.lost_count = 0

        fresh_patch = _extract_patch(frame_gray, self.target_center, self.config.init_half)
        if fresh_patch is not None and fresh_patch.shape == self.template_live.shape:
            std_val, edge_count = _patch_quality(fresh_patch)
            if std_val >= self.config.min_std and edge_count >= self.config.min_edge_pixels:
                alpha = self.config.update_alpha
                merged = cv2.addWeighted(
                    self.template_live.astype(np.float32),
                    1.0 - alpha,
                    fresh_patch.astype(np.float32),
                    alpha,
                    0.0,
                )
                self.template_live = np.clip(merged, 0, 255).astype(np.uint8)
                self.hist_live = _gray_hist(self.template_live)
                self.last_points = edge_count

        dx = self.target_center[0] - aim_center[0]
        dy = self.target_center[1] - aim_center[1]
        return True, float(dx), float(dy)
