import asyncio
import random
import sys
from pathlib import Path

import pygame

IS_WEB = sys.platform == "emscripten"

# --- Setup (runs once) ---
pygame.init()
try:
    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
except pygame.error:
    pass
WIDTH, HEIGHT = 800, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Vida de Mae")
clock = pygame.time.Clock()
font = pygame.font.Font(None, 48)
small_font = pygame.font.Font(None, 32)

BEST_TIME_FILE = Path(__file__).with_name("best_time.txt")
BACKGROUND_PATH = Path(__file__).parent / "images" / "background-top-view.png"
TOYS_DIR = Path(__file__).parent / "images" / "toys"
PLAYER_PATH = Path(__file__).parent / "images" / "player" / "jacky.png"
SOUNDS_DIR = Path(__file__).parent / "sounds"
TOY_COUNT = 20
TOY_SIZE = 56
PLAYER_HEIGHT = 96
player_speed = 5

background = pygame.transform.scale(
    pygame.image.load(BACKGROUND_PATH).convert(),
    (WIDTH, HEIGHT),
)
HUD_POS = (10, 10)
HUD_SIZE = (210, 120)
hud_panel = pygame.Surface(HUD_SIZE, pygame.SRCALPHA)
hud_panel.fill((20, 20, 30, 160))
HUD_EXCLUSION = pygame.Rect(HUD_POS[0], HUD_POS[1], *HUD_SIZE).inflate(TOY_SIZE, TOY_SIZE)


def load_toy_images():
    images = []
    for path in sorted(TOYS_DIR.glob("*.png")):
        img = pygame.image.load(path).convert_alpha()
        images.append(pygame.transform.smoothscale(img, (TOY_SIZE, TOY_SIZE)))
    if not images:
        raise FileNotFoundError(f"No toy images found in {TOYS_DIR}")
    return images


toy_images = load_toy_images()

_player_raw = pygame.image.load(PLAYER_PATH).convert_alpha()
_player_w = int(_player_raw.get_width() * PLAYER_HEIGHT / _player_raw.get_height())
player_sprite = pygame.transform.smoothscale(_player_raw, (_player_w, PLAYER_HEIGHT))


def load_coin_sound():
    """Prefer coin.ogg (required for Pygbag); fall back to coin.mp3 on desktop."""
    ogg = SOUNDS_DIR / "coin.ogg"
    mp3 = SOUNDS_DIR / "coin.mp3"
    for path in (ogg, mp3):
        if not path.is_file():
            continue
        if IS_WEB and path.suffix.lower() == ".mp3":
            continue
        try:
            return pygame.mixer.Sound(path)
        except pygame.error:
            continue
    return None


coin_sound = load_coin_sound()


class VirtualJoystick:
    """On-screen joystick for touch devices. Hidden until the first finger touch."""

    def __init__(self, center, radius=70, knob_radius=28):
        self.center = pygame.Vector2(center)
        self.radius = radius
        self.knob_radius = knob_radius
        self.knob_pos = self.center.copy()
        self.direction = pygame.Vector2(0, 0)
        self.active = False
        self.visible = False
        self._pointer_id = None

    def _event_pos(self, event):
        if event.type in (pygame.FINGERDOWN, pygame.FINGERMOTION, pygame.FINGERUP):
            return pygame.Vector2(event.x * WIDTH, event.y * HEIGHT)
        return pygame.Vector2(event.pos)

    def _in_base(self, pos):
        return pos.distance_to(self.center) <= self.radius * 1.4

    def _press(self, pos, pointer_id=None):
        if not self._in_base(pos):
            return
        self.visible = True
        self.active = True
        self._pointer_id = pointer_id
        self._move_knob(pos)

    def _release(self, pointer_id=None):
        if pointer_id is not None and pointer_id != self._pointer_id:
            return
        self.active = False
        self._pointer_id = None
        self.knob_pos = self.center.copy()
        self.direction.update(0, 0)

    def _move_knob(self, pos):
        offset = pos - self.center
        if offset.length() > self.radius:
            offset.scale_to_length(self.radius)
        self.knob_pos = self.center + offset
        if offset.length() > 8:
            self.direction = offset.normalize()
        else:
            self.direction.update(0, 0)

    def handle_event(self, event):
        if event.type == pygame.FINGERDOWN:
            self._press(self._event_pos(event), event.finger_id)
        elif event.type == pygame.FINGERMOTION and self.active:
            if event.finger_id == self._pointer_id:
                self._move_knob(self._event_pos(event))
        elif event.type == pygame.FINGERUP:
            self._release(event.finger_id)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._press(pygame.Vector2(event.pos))
        elif event.type == pygame.MOUSEMOTION and self.active and self._pointer_id is None:
            self._move_knob(pygame.Vector2(event.pos))
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._release()

    def draw(self, surface):
        if not self.visible:
            return
        pygame.draw.circle(surface, (35, 35, 50), self.center, self.radius)
        pygame.draw.circle(surface, (90, 90, 110), self.center, self.radius, 3)
        pygame.draw.circle(surface, (100, 200, 255), self.knob_pos, self.knob_radius)
        pygame.draw.circle(surface, (70, 150, 210), self.knob_pos, self.knob_radius, 2)


JOYSTICK_MARGIN = 100
joystick = VirtualJoystick((WIDTH - JOYSTICK_MARGIN, HEIGHT - JOYSTICK_MARGIN))


def event_pos(event):
    if event.type in (pygame.FINGERDOWN, pygame.FINGERMOTION, pygame.FINGERUP):
        return pygame.Vector2(event.x * WIDTH, event.y * HEIGHT)
    return pygame.Vector2(event.pos)


def apply_movement(player, keys, direction):
    move = pygame.Vector2(0, 0)
    if keys[pygame.K_LEFT] or keys[pygame.K_a]:
        move.x -= 1
    if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
        move.x += 1
    if keys[pygame.K_UP] or keys[pygame.K_w]:
        move.y -= 1
    if keys[pygame.K_DOWN] or keys[pygame.K_s]:
        move.y += 1
    if direction.length() > 0:
        move += direction
    if move.length() > 0:
        move.scale_to_length(player_speed)
        player.x += int(move.x)
        player.y += int(move.y)


def format_time(seconds):
    minutes, secs = divmod(seconds, 60)
    if minutes:
        return f"{int(minutes)}:{secs:05.2f}"
    return f"{secs:.2f}s"


def load_best_time():
    if IS_WEB:
        return None
    if BEST_TIME_FILE.exists():
        try:
            return float(BEST_TIME_FILE.read_text().strip())
        except ValueError:
            pass
    return None


def save_best_time(seconds):
    if IS_WEB:
        return
    try:
        BEST_TIME_FILE.write_text(f"{seconds:.4f}\n")
    except OSError:
        pass


def draw_button(surface, rect, label, hovered=False):
    color = (90, 160, 220) if hovered else (70, 130, 200)
    pygame.draw.rect(surface, color, rect, border_radius=8)
    pygame.draw.rect(surface, (120, 180, 240), rect, 2, border_radius=8)
    text = font.render(label, True, (255, 255, 255))
    surface.blit(text, text.get_rect(center=rect.center))


def spawn_toys():
    toys = []
    margin = TOY_SIZE // 2 + 10
    attempts = 0
    while len(toys) < TOY_COUNT:
        attempts += 1
        if attempts > 5000:
            raise RuntimeError("Could not place all toys — try a smaller TOY_COUNT")
        x = random.randint(margin, WIDTH - margin)
        y = random.randint(margin, HEIGHT - margin)
        image = random.choice(toy_images)
        rect = image.get_rect(center=(x, y))
        if rect.colliderect(HUD_EXCLUSION):
            continue
        if all(not rect.colliderect(other["rect"].inflate(24, 24)) for other in toys):
            toys.append({"image": image, "rect": rect})
    return toys


def draw_hud(score, elapsed, best_time):
    screen.blit(hud_panel, HUD_POS)
    score_text = small_font.render(f"Score: {score}/{TOY_COUNT}", True, (220, 220, 240))
    screen.blit(score_text, (20, 20))

    time_text = small_font.render(f"Time: {format_time(elapsed)}", True, (220, 220, 240))
    screen.blit(time_text, (20, 55))

    if best_time is not None:
        best_text = small_font.render(f"Best: {format_time(best_time)}", True, (255, 210, 80))
        screen.blit(best_text, (20, 90))


def draw_win_screen(win_msg, color, restart_rect, restart_hovered):
    win_text = font.render(win_msg, True, color)
    panel_w = max(win_text.get_width(), restart_rect.width) + 48
    panel_h = win_text.get_height() + restart_rect.height + 52
    panel_x = WIDTH // 2 - panel_w // 2
    panel_y = HEIGHT // 2 - panel_h // 2

    win_panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    win_panel.fill((20, 20, 30, 200))
    screen.blit(win_panel, (panel_x, panel_y))
    screen.blit(win_text, (WIDTH // 2 - win_text.get_width() // 2, panel_y + 16))

    restart_rect.centerx = WIDTH // 2
    restart_rect.y = panel_y + 24 + win_text.get_height()
    draw_button(screen, restart_rect, "Play again", restart_hovered)


async def main():
    best_time = load_best_time()
    restart_rect = pygame.Rect(0, 0, 180, 44)

    playing = True
    while playing:
        player = player_sprite.get_rect(center=(WIDTH // 2, HEIGHT // 2))
        toys = spawn_toys()
        score = 0
        start_ticks = pygame.time.get_ticks()
        finished = False
        finish_time = None
        new_best = False
        restart_hovered = False

        round_running = True
        while round_running:
            restart_hovered = False
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    playing = False
                    round_running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_r and finished:
                    round_running = False
                elif finished and event.type in (pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN):
                    if restart_rect.collidepoint(event_pos(event)):
                        round_running = False
                elif finished and event.type == pygame.MOUSEMOTION:
                    restart_hovered = restart_rect.collidepoint(event.pos)
                else:
                    joystick.handle_event(event)

            if not playing:
                break

            keys = pygame.key.get_pressed()
            if not finished:
                apply_movement(player, keys, joystick.direction)
                player.clamp_ip(screen.get_rect())

            for toy in toys[:]:
                if toy["rect"].colliderect(player):
                    toys.remove(toy)
                    score += 1
                    if coin_sound is not None:
                        coin_sound.play()

            if not toys and not finished:
                finish_time = (pygame.time.get_ticks() - start_ticks) / 1000.0
                finished = True
                if best_time is None or finish_time < best_time:
                    best_time = finish_time
                    save_best_time(best_time)
                    new_best = True

            elapsed = finish_time if finished else (pygame.time.get_ticks() - start_ticks) / 1000.0

            screen.blit(background, (0, 0))

            for toy in toys:
                screen.blit(toy["image"], toy["rect"])

            screen.blit(player_sprite, player)
            draw_hud(score, elapsed, best_time)
            joystick.draw(screen)

            if finished:
                if new_best:
                    win_msg = f"New best! {format_time(finish_time)}"
                    color = (255, 220, 80)
                else:
                    win_msg = f"Done in {format_time(finish_time)}"
                    color = (120, 255, 120)
                draw_win_screen(win_msg, color, restart_rect, restart_hovered)

            pygame.display.flip()
            clock.tick(60)
            await asyncio.sleep(0)

    pygame.quit()


asyncio.run(main())
