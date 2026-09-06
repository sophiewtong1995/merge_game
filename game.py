from __future__ import annotations

import math
from pathlib import Path
import sys
import time

import pygame

from game_logic import COLORS, MAX_LEVEL, GameState, Piece


WIDTH, HEIGHT = 540, 900
FPS = 60
MERGE_ANIMATION_DURATION = 0.26
FALL_ANIMATION_DURATION = 0.30
PROJECTILE_TRAVEL_DURATION = 0.42
PROJECTILE_IMPACT_DURATION = 0.55
BOARD_X, BOARD_Y = 25, 405
CELL = 70
BOARD_W, BOARD_H = CELL * 7, CELL * 6

PALETTE = {
    "sky": (106, 211, 239),
    "sand": (255, 231, 177),
    "panel": (232, 252, 255),
    "line": (122, 211, 225),
    "ink": (41, 78, 102),
    "red": (239, 91, 89),
    "blue": (75, 153, 236),
    "green": (92, 194, 120),
    "white": (255, 255, 255),
    "shadow": (47, 103, 121),
}


def font(size: int, bold: bool = False) -> pygame.font.Font:
    candidates = [
        "/System/Library/Fonts/STHeiti Medium.ttc" if bold else "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return pygame.font.Font(candidate, size)
    return pygame.font.SysFont("Arial", size, bold=bold)


def rounded_rect(surface, color, rect, radius=16, width=0):
    pygame.draw.rect(surface, color, rect, width=width, border_radius=radius)


class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("海滩合成大作战")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.state = GameState()
        self.selected = None
        self.drag_start = None
        self.drag_pos = None
        self.is_dragging = False
        self.mouse_down = None
        self.refill_at = 0.0
        self.auto_merge_at = 0.0
        self.auto_focus = None
        self.message = "把相同物品摆到相邻位置"
        self.message_until = 0.0
        self.merge_animation = None
        self.fall_animations = []
        self.projectile_animations = []
        self.active_chain_attack = None
        self.settle_at = 0.0
        self.running = True

    def cell_at(self, pos):
        x, y = pos
        if not (BOARD_X <= x < BOARD_X + BOARD_W and BOARD_Y <= y < BOARD_Y + BOARD_H):
            return None
        return ((y - BOARD_Y) // CELL, (x - BOARD_X) // CELL)

    def handle_cell_action(self, source, target):
        result = self.state.move(source, target)
        if result.kind == "invalid":
            return
        if result.kind == "no_moves":
            self.show_message("拖拽次数已用完", 1.5)
            return
        if result.kind == "game_over":
            return
        if result.kind in ("merge", "max_merge", "attack"):
            self.handle_merge_result(result, animate=False, new_chain=True)
            self.auto_focus = result.target
            self.auto_merge_at = time.monotonic() + 0.10
        else:
            self.show_message("物品不同，返回原位", 1.2)

    def handle_merge_result(self, result, animate=True, new_chain=False):
        if result.kind == "merge":
            self.show_message(f"合成成功！累计 {result.damage} 点攻击")
            self.record_chain_attack(result, new_chain)
            if animate:
                self.start_merge_animation(result)
        elif result.kind == "max_merge":
            self.show_message(f"达到最高等级！累计 {result.damage} 点攻击")
            self.record_chain_attack(result, new_chain)
            if animate:
                self.start_merge_animation(result)
        elif result.kind == "attack":
            self.show_message(f"五级物品准备发射：{result.damage} 点攻击")
            self.start_projectile(result.target, result.color, result.damage)

    def show_attack_resolution(self, result):
        if result.wave_cleared:
            self.show_message("炮弹命中！本级怪物全部击败")
        elif result.monster_defeated:
            self.show_message("炮弹命中并击败怪物，等待其他颜色")
        else:
            self.show_message(f"炮弹发射！怪物生命减少 {result.damage}")

    def record_chain_attack(self, result, new_chain=False):
        if (
            self.active_chain_attack
            and (new_chain or self.active_chain_attack["color"] != result.color)
        ):
            self.launch_active_chain_attack()
        if self.active_chain_attack is None:
            self.active_chain_attack = {
                "color": result.color,
                "damage": 0,
                "source": result.target,
            }
        self.active_chain_attack["damage"] += result.damage
        self.active_chain_attack["source"] = result.target

    def start_projectile(self, source, color, damage, delay=0.0):
        if source is None:
            return
        self.projectile_animations.append(
            {
                "source": source,
                "color": color,
                "damage": damage,
                "born": time.monotonic(),
                "delay": delay,
                "applied": False,
            }
        )

    def launch_active_chain_attack(self):
        if not self.active_chain_attack:
            return 0.0
        attack = self.active_chain_attack
        self.start_projectile(
            attack["source"], attack["color"], attack["damage"]
        )
        self.active_chain_attack = None
        return PROJECTILE_TRAVEL_DURATION

    def start_merge_animation(self, result):
        if result.source is None or result.target is None:
            return
        self.merge_animation = {
            "source": result.source,
            "target": result.target,
            "piece": Piece(result.color, result.source_level),
            "born": time.monotonic(),
        }

    def show_message(self, text, seconds=1.8):
        self.message = text
        self.message_until = time.monotonic() + seconds

    def board_busy(self):
        return bool(
            self.merge_animation
            or self.fall_animations
            or self.auto_merge_at
            or self.refill_at
            or self.settle_at
        )

    def events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_r:
                    self.state.reset()
                    self.selected = None
                    self.refill_at = 0.0
                    self.auto_merge_at = 0.0
                    self.auto_focus = None
                    self.merge_animation = None
                    self.fall_animations = []
                    self.projectile_animations = []
                    self.active_chain_attack = None
                    self.settle_at = 0.0
                    self.show_message("新游戏开始！")
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.board_busy():
                    self.show_message("正在结算，请稍候", 0.8)
                    continue
                cell = self.cell_at(event.pos)
                self.mouse_down = event.pos
                self.drag_start = cell
                self.drag_pos = event.pos
                self.is_dragging = False
                self.selected = cell
            elif event.type == pygame.MOUSEMOTION and self.mouse_down:
                self.drag_pos = event.pos
                self.is_dragging = math.dist(self.mouse_down, event.pos) > 10
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                target = self.cell_at(event.pos)
                if self.drag_start is not None and self.is_dragging:
                    if target is not None:
                        self.handle_cell_action(self.drag_start, target)
                    else:
                        self.show_message("已返回原位", 1.0)
                elif self.drag_start is not None:
                    result = self.state.activate(self.drag_start)
                    if result.kind == "attack":
                        self.handle_merge_result(result)
                        self.refill_at = (
                            time.monotonic()
                            + PROJECTILE_TRAVEL_DURATION
                            + 0.04
                        )
                    elif result.kind == "waiting":
                        self.show_message("这只怪物已击败，等待其他颜色", 1.5)
                self.selected = None
                self.drag_start = None
                self.drag_pos = None
                self.is_dragging = False
                self.mouse_down = None

    def update(self):
        now = time.monotonic()
        if self.merge_animation and now - self.merge_animation["born"] >= MERGE_ANIMATION_DURATION:
            self.merge_animation = None
        self.fall_animations = [
            item
            for item in self.fall_animations
            if now - item["born"] < item["delay"] + FALL_ANIMATION_DURATION
        ]
        for item in self.projectile_animations:
            if not item["applied"] and now - item["born"] >= item["delay"]:
                item["applied"] = True
                resolution = self.state.resolve_attack(
                    item["color"], item["damage"], item["source"]
                )
                self.show_attack_resolution(resolution)
        self.projectile_animations = [
            item
            for item in self.projectile_animations
            if now - item["born"]
            < item["delay"] + PROJECTILE_TRAVEL_DURATION + PROJECTILE_IMPACT_DURATION
        ]
        if self.settle_at and now >= self.settle_at:
            self.settle_at = 0.0
            self.settle_board()
        if self.auto_merge_at and now >= self.auto_merge_at:
            previous_focus = self.auto_focus
            result = self.state.auto_merge_once(self.auto_focus)
            self.auto_merge_at = 0.0
            if result.kind != "none":
                continues_chain = (
                    previous_focus is not None
                    and previous_focus in (result.source, result.target)
                )
                self.handle_merge_result(result, new_chain=not continues_chain)
                self.auto_focus = result.target
                self.auto_merge_at = now + MERGE_ANIMATION_DURATION + 0.04
            else:
                projectile_wait = self.launch_active_chain_attack()
                if any(piece is None for row in self.state.board for piece in row):
                    self.refill_at = now + max(0.07, projectile_wait + 0.04)
                elif projectile_wait:
                    self.settle_at = now + projectile_wait + 0.04
                else:
                    self.settle_board()
        if self.refill_at and now >= self.refill_at:
            moves = self.state.refill()
            self.refill_at = 0.0
            self.start_fall_animations(moves, now)
            new_moves = [move for move in moves if move.is_new]
            self.auto_focus = new_moves[-1].target if new_moves else None
            max_delay = max((item["delay"] for item in self.fall_animations), default=0.0)
            self.auto_merge_at = now + max_delay + FALL_ANIMATION_DURATION + 0.035

    def settle_board(self):
        if self.state.advance_wave():
            self.show_message("下一等级怪物一起出现！")
        else:
            self.state.check_failure()

    def start_fall_animations(self, moves, now):
        self.fall_animations = []
        new_count_by_col = {}
        for move in moves:
            if move.is_new:
                new_count_by_col[move.target[1]] = new_count_by_col.get(move.target[1], 0) + 1
        for move in moves:
            target_row, target_col = move.target
            delay = target_col * 0.005
            if move.is_new:
                last_new_row = new_count_by_col[target_col] - 1
                delay += (last_new_row - target_row) * 0.028
            self.fall_animations.append(
                {
                    "piece": move.piece,
                    "source": move.source,
                    "target": move.target,
                    "born": now,
                    "delay": delay,
                }
            )
    def draw_background(self):
        self.screen.fill(PALETTE["sky"])
        pygame.draw.circle(self.screen, (255, 242, 165), (455, 78), 45)
        for x, y, radius in [(35, 95, 32), (92, 76, 42), (145, 102, 29), (385, 130, 35)]:
            pygame.draw.circle(self.screen, (232, 250, 255), (x, y), radius)
        pygame.draw.rect(self.screen, (76, 190, 222), (0, 145, WIDTH, 100))
        for y in (172, 202, 228):
            pygame.draw.line(self.screen, (194, 244, 245), (0, y), (WIDTH, y), 4)
        pygame.draw.rect(self.screen, PALETTE["sand"], (0, 245, WIDTH, HEIGHT - 245))
        title = font(35, True).render("海滩合成大作战", True, PALETTE["white"])
        shadow = font(35, True).render("海滩合成大作战", True, PALETTE["shadow"])
        self.screen.blit(shadow, shadow.get_rect(center=(WIDTH // 2 + 2, 51)))
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 48)))

    def draw_monster(self, color, center, monster):
        x, y = center
        body = PALETTE[color]
        shadow = pygame.Rect(x - 42, y + 38, 84, 16)
        pygame.draw.ellipse(self.screen, (218, 191, 143), shadow)
        if monster.stage == 1:
            pygame.draw.circle(self.screen, body, (x, y), 38)
            pygame.draw.circle(self.screen, body, (x - 43, y + 8), 18)
            pygame.draw.circle(self.screen, body, (x + 43, y + 8), 18)
            for dx in (-18, 18):
                pygame.draw.circle(self.screen, PALETTE["white"], (x + dx, y - 8), 7)
                pygame.draw.circle(self.screen, PALETTE["ink"], (x + dx, y - 7), 3)
            pygame.draw.arc(self.screen, PALETTE["ink"], (x - 12, y + 5, 24, 16), 0.2, 2.9, 3)
        else:
            pygame.draw.ellipse(self.screen, body, (x - 31, y - 43, 62, 86))
            pygame.draw.circle(self.screen, body, (x, y - 43), 32)
            pygame.draw.arc(self.screen, body, (x - 34, y + 13, 58, 57), 3.5, 6.3, 15)
            for dx in (-11, 11):
                pygame.draw.circle(self.screen, PALETTE["white"], (x + dx, y - 48), 6)
                pygame.draw.circle(self.screen, PALETTE["ink"], (x + dx, y - 47), 3)
        badge = font(16, True).render(f"Lv.{monster.stage}", True, PALETTE["ink"])
        self.screen.blit(badge, badge.get_rect(center=(x, y + 66)))
        bar = pygame.Rect(x - 58, y + 82, 116, 17)
        rounded_rect(self.screen, (255, 255, 255), bar, 9)
        fill = bar.copy()
        fill.width = max(0, int(bar.width * monster.hp / monster.max_hp))
        rounded_rect(self.screen, body, fill, 9)
        hp = font(14, True).render(f"{monster.hp}/{monster.max_hp}", True, PALETTE["ink"])
        self.screen.blit(hp, hp.get_rect(center=bar.center))
        if monster.hp <= 0:
            defeated = font(18, True).render("已击败", True, PALETTE["ink"])
            badge_rect = defeated.get_rect(center=(x, y))
            rounded_rect(self.screen, (255, 255, 255), badge_rect.inflate(16, 8), 12)
            self.screen.blit(defeated, badge_rect)

    def draw_piece(self, piece: Piece, rect, selected=False):
        if selected:
            rounded_rect(self.screen, (255, 216, 91), rect.inflate(-5, -5), 14, 4)
        center = rect.center
        color = PALETTE[piece.color]
        if piece.level == 1:
            pygame.draw.circle(self.screen, (255, 255, 255), center, 22)
            pygame.draw.circle(self.screen, color, center, 18)
            pygame.draw.circle(self.screen, (255, 255, 255), (center[0] - 6, center[1] - 6), 5)
        elif piece.level == 2:
            pygame.draw.circle(self.screen, color, (center[0] - 10, center[1] + 2), 16)
            pygame.draw.circle(self.screen, color, (center[0] + 10, center[1] - 3), 16)
            pygame.draw.circle(self.screen, (255, 255, 255), (center[0] + 5, center[1] - 9), 4)
        elif piece.level == 3:
            pygame.draw.arc(self.screen, (151, 91, 49), rect.inflate(-23, -14), 0, math.pi, 5)
            pygame.draw.rect(self.screen, (225, 166, 92), (center[0] - 24, center[1] - 3, 48, 25), border_radius=8)
            for dx in (-12, 0, 12):
                pygame.draw.circle(self.screen, color, (center[0] + dx, center[1] - 7), 12)
        elif piece.level == 4:
            pygame.draw.circle(self.screen, (255, 247, 220), center, 25)
            pygame.draw.line(self.screen, (139, 91, 54), (center[0] - 17, center[1] + 19),
                             (center[0] + 15, center[1] - 18), 8)
            pygame.draw.arc(self.screen, color, (center[0] - 24, center[1] - 25, 35, 34),
                            4.7, 7.6, 7)
            pygame.draw.circle(self.screen, color, (center[0] + 17, center[1] - 19), 8)
        else:
            pygame.draw.circle(self.screen, (255, 218, 72), center, 28)
            pygame.draw.circle(self.screen, color, center, 21)
            points = []
            for index in range(10):
                angle = -math.pi / 2 + index * math.pi / 5
                radius = 15 if index % 2 == 0 else 7
                points.append((center[0] + math.cos(angle) * radius,
                               center[1] + math.sin(angle) * radius))
            pygame.draw.polygon(self.screen, (255, 244, 145), points)
        level = font(13, True).render(str(piece.level), True, PALETTE["white"])
        badge = pygame.Rect(rect.right - 23, rect.top + 5, 18, 18)
        pygame.draw.circle(self.screen, PALETTE["ink"], badge.center, 10)
        self.screen.blit(level, level.get_rect(center=badge.center))

    def draw_board(self):
        panel = pygame.Rect(14, 390, WIDTH - 28, BOARD_H + 30)
        rounded_rect(self.screen, PALETTE["panel"], panel, 24)
        rounded_rect(self.screen, PALETTE["line"], panel, 24, 4)
        for row in range(self.state.rows):
            for col in range(self.state.cols):
                rect = pygame.Rect(BOARD_X + col * CELL, BOARD_Y + row * CELL, CELL, CELL)
                cell_rect = rect.inflate(-5, -5)
                rounded_rect(self.screen, (248, 255, 255), cell_rect, 11)
                piece = self.state.board[row][col]
                hidden_by_drag = self.is_dragging and self.drag_start == (row, col)
                hidden_by_merge = (
                    self.merge_animation
                    and self.merge_animation["target"] == (row, col)
                )
                hidden_by_fall = any(
                    item["target"] == (row, col) for item in self.fall_animations
                )
                if piece and not hidden_by_drag and not hidden_by_merge and not hidden_by_fall:
                    self.draw_piece(piece, rect, self.selected == (row, col))

    def cell_center(self, cell):
        row, col = cell
        return (BOARD_X + col * CELL + CELL // 2, BOARD_Y + row * CELL + CELL // 2)

    def draw_merge_animation(self):
        animation = self.merge_animation
        if not animation:
            return
        progress = min(1.0, (time.monotonic() - animation["born"]) / MERGE_ANIMATION_DURATION)
        eased = progress * progress * (3.0 - 2.0 * progress)
        source_x, source_y = self.cell_center(animation["source"])
        target_x, target_y = self.cell_center(animation["target"])

        if progress < 0.76:
            target_rect = pygame.Rect(0, 0, CELL, CELL)
            target_rect.center = (target_x, target_y)
            self.draw_piece(animation["piece"], target_rect)

            moving_x = source_x + (target_x - source_x) * eased
            moving_y = source_y + (target_y - source_y) * eased - math.sin(math.pi * eased) * 18
            moving_rect = pygame.Rect(0, 0, CELL, CELL)
            moving_rect.center = (round(moving_x), round(moving_y))
            self.draw_piece(animation["piece"], moving_rect, True)
        else:
            row, col = animation["target"]
            result_piece = self.state.board[row][col]
            if result_piece:
                result_rect = pygame.Rect(0, 0, CELL, CELL)
                result_rect.center = (target_x, target_y)
                self.draw_piece(result_piece, result_rect, True)
            pulse = int(25 + 18 * (1.0 - progress))
            pygame.draw.circle(self.screen, (255, 224, 85), (target_x, target_y), pulse, 4)

    def draw_fall_animations(self):
        now = time.monotonic()
        previous_clip = self.screen.get_clip()
        self.screen.set_clip(pygame.Rect(BOARD_X, BOARD_Y, BOARD_W, BOARD_H))
        for animation in self.fall_animations:
            elapsed = now - animation["born"] - animation["delay"]
            if elapsed < 0:
                progress = 0.0
            else:
                progress = min(1.0, elapsed / FALL_ANIMATION_DURATION)

            if progress < 0.82:
                travel = (progress / 0.82) ** 2
            else:
                bounce_progress = (progress - 0.82) / 0.18
                travel = 1.0 - 0.055 * math.sin(math.pi * bounce_progress)

            source_x, source_y = self.cell_center(animation["source"])
            target_x, target_y = self.cell_center(animation["target"])
            x = source_x + (target_x - source_x) * travel
            y = source_y + (target_y - source_y) * travel
            rect = pygame.Rect(0, 0, CELL, CELL)
            rect.center = (round(x), round(y))
            self.draw_piece(animation["piece"], rect)
        self.screen.set_clip(previous_clip)

    def draw_projectiles(self):
        now = time.monotonic()
        targets = {"red": (105, 280), "blue": (270, 280), "green": (435, 280)}
        for animation in self.projectile_animations:
            elapsed = now - animation["born"] - animation["delay"]
            if elapsed < 0:
                continue
            color = PALETTE[animation["color"]]
            target_x, target_y = targets[animation["color"]]
            if elapsed < PROJECTILE_TRAVEL_DURATION:
                progress = elapsed / PROJECTILE_TRAVEL_DURATION
                eased = 1.0 - (1.0 - progress) ** 3
                source_x, source_y = self.cell_center(animation["source"])
                x = source_x + (target_x - source_x) * eased
                y = source_y + (target_y - source_y) * eased - math.sin(math.pi * eased) * 42
                previous = max(0.0, eased - 0.08)
                trail_x = source_x + (target_x - source_x) * previous
                trail_y = source_y + (target_y - source_y) * previous - math.sin(math.pi * previous) * 42
                pygame.draw.line(self.screen, (255, 236, 126), (trail_x, trail_y), (x, y), 7)
                pygame.draw.circle(self.screen, (255, 255, 255), (round(x), round(y)), 11)
                pygame.draw.circle(self.screen, color, (round(x), round(y)), 8)
            else:
                impact = min(1.0, (elapsed - PROJECTILE_TRAVEL_DURATION) / PROJECTILE_IMPACT_DURATION)
                radius = int(18 + impact * 34)
                ring_color = tuple(min(255, channel + 70) for channel in color)
                pygame.draw.circle(self.screen, ring_color, (target_x, target_y), radius, 5)
                damage = font(22, True).render(
                    f"攻击 +{animation['damage']}", True, color
                )
                damage_rect = damage.get_rect(
                    center=(target_x, target_y - 68 - impact * 7)
                )
                rounded_rect(
                    self.screen,
                    (255, 255, 255),
                    damage_rect.inflate(16, 8),
                    12,
                )
                self.screen.blit(
                    damage,
                    damage_rect,
                )

    def draw_dragged_piece(self):
        if not self.is_dragging or self.drag_start is None or self.drag_pos is None:
            return
        row, col = self.drag_start
        piece = self.state.board[row][col]
        if piece:
            rect = pygame.Rect(0, 0, CELL, CELL)
            rect.center = self.drag_pos
            self.draw_piece(piece, rect, True)

    def draw_hud(self):
        positions = [(105, 280), (270, 280), (435, 280)]
        for color, pos in zip(COLORS, positions):
            self.draw_monster(color, pos, self.state.monsters[color])
        score_panel = pygame.Rect(160, 104, 220, 38)
        rounded_rect(self.screen, (255, 255, 255), score_panel, 19)
        rounded_rect(self.screen, PALETTE["line"], score_panel, 19, 3)
        moves_color = PALETTE["red"] if self.state.moves_remaining <= 5 else PALETTE["ink"]
        moves = font(21, True).render(
            f"剩余拖拽 {self.state.moves_remaining}", True, moves_color
        )
        self.screen.blit(moves, moves.get_rect(center=score_panel.center))

        message = self.message if time.monotonic() < self.message_until else "拖拽合成；单击最高级物品发动攻击"
        text = font(19, True).render(message, True, PALETTE["ink"])
        self.screen.blit(text, text.get_rect(center=(WIDTH // 2, 854)))
        hint = font(15).render("R：重新开始    Esc：退出", True, (103, 103, 90))
        self.screen.blit(hint, hint.get_rect(center=(WIDTH // 2, 882)))

    def draw_game_over(self):
        if not self.state.game_over:
            return
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((24, 54, 68, 165))
        self.screen.blit(shade, (0, 0))
        panel = pygame.Rect(75, 325, 390, 210)
        rounded_rect(self.screen, (255, 248, 225), panel, 28)
        rounded_rect(self.screen, PALETTE["red"], panel, 28, 5)
        title = font(38, True).render("挑战失败", True, PALETTE["red"])
        detail = font(20).render("拖拽次数已用完", True, PALETTE["ink"])
        hint = font(18).render("按 R 重新开始", True, PALETTE["ink"])
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 380)))
        self.screen.blit(detail, detail.get_rect(center=(WIDTH // 2, 445)))
        self.screen.blit(hint, hint.get_rect(center=(WIDTH // 2, 492)))

    def draw(self):
        self.draw_background()
        self.draw_hud()
        self.draw_board()
        self.draw_fall_animations()
        self.draw_merge_animation()
        self.draw_projectiles()
        self.draw_dragged_piece()
        self.draw_game_over()
        pygame.display.flip()

    def run(self):
        while self.running:
            self.events()
            self.update()
            self.draw()
            self.clock.tick(FPS)
        pygame.quit()


if __name__ == "__main__":
    try:
        Game().run()
    except pygame.error as exc:
        print(f"Pygame 无法启动：{exc}")
        sys.exit(1)
