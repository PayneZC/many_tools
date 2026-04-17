from __future__ import annotations

import sys
import unittest
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageSequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RECOIL_DIR = PROJECT_ROOT / "recoil_macro"
if str(RECOIL_DIR) not in sys.path:
    sys.path.insert(0, str(RECOIL_DIR))

from follow_core import (  # noqa: E402
    RobustPointTracker,
    TrackerConfig,
    to_gray,
)


def _build_base_scene(size: int = 220) -> np.ndarray:
    rng = np.random.default_rng(42)
    scene = np.zeros((size, size, 3), dtype=np.uint8)
    noise = rng.integers(20, 110, size=(size, size, 3), dtype=np.uint8)
    scene[:] = noise

    center = size // 2
    cv2.rectangle(scene, (center - 40, center - 40), (center + 40, center + 40), (240, 240, 240), 2)
    cv2.line(scene, (center - 25, center), (center + 25, center), (0, 0, 255), 2)
    cv2.line(scene, (center, center - 25), (center, center + 25), (0, 255, 0), 2)
    cv2.circle(scene, (center, center), 12, (255, 0, 0), -1)

    for _ in range(24):
        x = int(rng.integers(0, size))
        y = int(rng.integers(0, size))
        r = int(rng.integers(2, 7))
        color = tuple(int(v) for v in rng.integers(40, 220, size=3))
        cv2.circle(scene, (x, y), r, color, -1)
    return scene


def _build_flat_scene(size: int = 220, value: int = 127) -> np.ndarray:
    return np.full((size, size, 3), value, dtype=np.uint8)


def _draw_ufo(frame: np.ndarray, center: tuple[int, int]) -> None:
    x, y = center
    cv2.ellipse(frame, (x, y + 8), (24, 9), 0, 0, 360, (140, 200, 255), -1)
    cv2.ellipse(frame, (x, y + 2), (13, 7), 0, 0, 360, (180, 230, 255), -1)
    cv2.line(frame, (x - 30, y + 12), (x + 30, y + 12), (95, 160, 220), 1)
    for dx in (-15, 0, 15):
        cv2.circle(frame, (x + dx, y + 12), 2, (255, 255, 180), -1)


def _shift_scene(scene: np.ndarray, dx: int, dy: int) -> np.ndarray:
    mat = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(scene, mat, (scene.shape[1], scene.shape[0]), borderMode=cv2.BORDER_REFLECT)


def _create_tracking_gif(gif_path: Path, offsets: list[tuple[int, int]], ufo_path: list[tuple[int, int]]) -> None:
    gif_path.parent.mkdir(parents=True, exist_ok=True)
    base = _build_base_scene()
    frames = []
    for (dx, dy), ufo_center in zip(offsets, ufo_path):
        frame = _shift_scene(base, dx, dy)
        _draw_ufo(frame, ufo_center)
        frames.append(frame)
    pil_frames = [Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)) for frame in frames]
    pil_frames[0].save(
        gif_path,
        save_all=True,
        append_images=pil_frames[1:],
        duration=40,
        loop=0,
        optimize=True,
    )


def _read_gif_frames(gif_path: Path) -> list[np.ndarray]:
    with Image.open(gif_path) as gif:
        return [
            cv2.cvtColor(np.array(frame.convert("RGB")), cv2.COLOR_RGB2BGR)
            for frame in ImageSequence.Iterator(gif)
        ]


class TestFollowWithGif(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.offsets = [(0, 0)] * 10
        cls.ufo_path = [(110 + i * 6, 108 + (i % 2)) for i in range(len(cls.offsets))]
        cls.gif_path = Path(__file__).resolve().parent / "assets" / "target_follow.gif"
        _create_tracking_gif(cls.gif_path, cls.offsets, cls.ufo_path)

    def test_tracker_does_not_lock_flat_background(self) -> None:
        frames = [_build_flat_scene() for _ in range(6)]
        region_center = (110.0, 110.0)
        tracker = RobustPointTracker(
            TrackerConfig(
                lock_half=18,
                init_half=30,
                search_half=135,
                min_std=5.0,
                min_edge_pixels=8,
                min_score=0.34,
                min_reacquire_score=0.26,
                min_psr=4.2,
                min_appearance=0.30,
                top_k=6,
                update_alpha=0.05,
                max_jump=48.0,
                max_reacquire_jump=90.0,
                max_soft_lost=12,
            )
        )
        initialized = tracker.initialize(to_gray(frames[0]), region_center)
        self.assertFalse(initialized, "纯色背景不应初始化成功，否则会导致乱飞")

        for frame in frames[1:]:
            locked, dx, dy = tracker.update(to_gray(frame), region_center)
            self.assertFalse(locked)
            self.assertEqual(dx, 0.0)
            self.assertEqual(dy, 0.0)

    def test_tracker_follows_ufo_like_motion(self) -> None:
        frames = _read_gif_frames(self.gif_path)
        self.assertGreaterEqual(len(frames), 6)

        h, w = frames[0].shape[:2]
        region_center = (float(w // 2), float(h // 2))
        tracker = RobustPointTracker(
            TrackerConfig(
                lock_half=18,
                init_half=30,
                search_half=135,
                min_std=5.0,
                min_edge_pixels=8,
                min_score=0.34,
                min_reacquire_score=0.26,
                min_psr=4.2,
                min_appearance=0.30,
                top_k=6,
                update_alpha=0.05,
                max_jump=48.0,
                max_reacquire_jump=90.0,
                max_soft_lost=12,
            )
        )
        initialized = tracker.initialize(to_gray(frames[0]), region_center)
        self.assertTrue(initialized, "初始化失败：未能锁定中心目标")
        fail_count = 0
        first_expected = self.ufo_path[0]
        base_expected_dx = first_expected[0] - region_center[0]
        base_expected_dy = first_expected[1] - region_center[1]
        observed_rel_dx: list[float] = []
        observed_rel_dy: list[float] = []
        expected_rel_dx_series: list[float] = []
        expected_rel_dy_series: list[float] = []

        for idx, frame in enumerate(frames[1:], start=1):
            curr_gray = to_gray(frame)
            locked, dx, dy = tracker.update(curr_gray, region_center)
            if not locked:
                fail_count += 1
                continue

            expected_x, expected_y = self.ufo_path[idx]
            expected_dx = expected_x - region_center[0]
            expected_dy = expected_y - region_center[1]
            rel_dx = dx - base_expected_dx
            rel_dy = dy - base_expected_dy
            expected_rel_dx = expected_dx - base_expected_dx
            expected_rel_dy = expected_dy - base_expected_dy
            observed_rel_dx.append(rel_dx)
            observed_rel_dy.append(rel_dy)
            expected_rel_dx_series.append(expected_rel_dx)
            expected_rel_dy_series.append(expected_rel_dy)

        self.assertLessEqual(fail_count, 2, "跟踪丢失次数过多")
        self.assertGreaterEqual(len(observed_rel_dx), len(frames) - 3, "有效跟踪帧太少")
        self.assertGreater(observed_rel_dx[-1], expected_rel_dx_series[-1] * 0.75)
        self.assertLess(observed_rel_dx[-1], expected_rel_dx_series[-1] * 1.30)
        self.assertGreater(observed_rel_dy[-1], expected_rel_dy_series[-1] * 0.4 - 1.0)
        for i in range(1, len(observed_rel_dx)):
            self.assertGreaterEqual(observed_rel_dx[i] + 1.0, observed_rel_dx[i - 1])


if __name__ == "__main__":
    unittest.main()
