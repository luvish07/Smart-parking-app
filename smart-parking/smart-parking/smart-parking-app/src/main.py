import asyncio
import math
from datetime import datetime

import flet as ft
import requests

# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------
SUPABASE_URL = "https://gysrguqvtnudohnmxrvj.supabase.co"
SUPABASE_KEY = "sb_publishable_ZRMSLIAOXXfcLoSrQqEUDw_ZGX-bMF3"

API_URL = f"{SUPABASE_URL}/rest/v1/parking_slots"
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}

REFRESH_SECONDS = 3

# ------------------------------------------------------------------
# Palette (hex strings only, so nothing depends on constant names)
# ------------------------------------------------------------------
BG = "#0b1220"
PANEL = "#131c2e"
PANEL_BORDER = "#22304a"
ASPHALT = "#2a303c"
LANE = "#1c212b"
LINE = "#e8ecf3"
FREE_BAY = "#173a31"
OCC_BAY = "#3b2430"
GREEN = "#2ee6a6"
RED = "#ff5a6e"
CYAN = "#38bdf8"
TEXT = "#e8ecf3"
MUTED = "#8a97b1"
GLASS = "#141a24"
LIGHT_Y = "#ffe08a"
LIGHT_R = "#ff3b4d"

CAR_COLORS = [
    "#ef4444", "#3b82f6", "#f59e0b", "#a855f7",
    "#14b8a6", "#f97316", "#ec4899", "#6366f1",
    "#84cc16", "#e2e8f0",
]

BAY_W = 96
BAY_H = 150


def alpha(opacity, color):
    return ft.Colors.with_opacity(opacity, color)


def fetch_slots():
    """Blocking network call (run in a thread so the UI never freezes)."""
    response = requests.get(
        API_URL,
        headers=HEADERS,
        params={"select": "id,status", "order": "id.asc"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def shadow(blur=12, opacity=0.35):
    return ft.BoxShadow(
        blur_radius=blur,
        color=alpha(opacity, "#000000"),
        offset=ft.Offset(0, 4),
    )


# ------------------------------------------------------------------
# Virtual car (drawn top-down from simple shapes)
# ------------------------------------------------------------------
def build_car(color, facing_down):
    def lights(c):
        return ft.Row(
            [
                ft.Container(width=9, height=4, bgcolor=c, border_radius=2),
                ft.Container(width=9, height=4, bgcolor=c, border_radius=2),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            spacing=0,
        )

    def glass(h):
        return ft.Container(
            width=32, height=h, bgcolor=GLASS, border_radius=6
        )

    roof = ft.Container(
        width=32, height=22, bgcolor=alpha(0.55, "#000000"), border_radius=5
    )

    # Order from the top of the screen downwards when the car faces DOWN
    parts = [
        lights(LIGHT_R),   # tail lights
        glass(12),         # rear window
        roof,
        glass(16),         # windshield
        lights(LIGHT_Y),   # head lights
    ]
    if not facing_down:
        parts.reverse()

    return ft.Container(
        width=46,
        height=96,
        bgcolor=color,
        border_radius=16,
        padding=6,
        shadow=shadow(10, 0.5),
        content=ft.Column(
            parts,
            spacing=0,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )


# ------------------------------------------------------------------
# App
# ------------------------------------------------------------------
def main(page: ft.Page):
    page.title = "Smart Parking - Digital Twin"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = BG
    page.padding = 20
    page.scroll = ft.ScrollMode.AUTO

    state = {
        "previous": {},      # slot id -> status from the last refresh
        "selected": None,    # slot id currently selected
        "slots": {},         # slot id -> status
        "first_load": True,
    }

    # ---------- Dynamic controls ----------
    total_text = ft.Text("0", size=30, weight=ft.FontWeight.BOLD, color=CYAN)
    available_text = ft.Text("0", size=30, weight=ft.FontWeight.BOLD, color=GREEN)
    occupied_text = ft.Text("0", size=30, weight=ft.FontWeight.BOLD, color=RED)

    occupancy_label = ft.Text("Occupancy 0%", size=13, color=MUTED)
    occupancy_bar = ft.ProgressBar(
        value=0, height=8, color=RED, bgcolor=alpha(0.35, GREEN)
    )

    status_text = ft.Text("Connecting to sensors...", size=12, color=MUTED)
    loader = ft.ProgressRing(width=14, height=14, stroke_width=2, visible=False)
    live_dot = ft.Icon(ft.Icons.CIRCLE, size=10, color=GREEN)

    selected_title = ft.Text(
        "Tap any bay", size=18, weight=ft.FontWeight.BOLD, color=TEXT
    )
    selected_detail = ft.Text(
        "Select a slot in the twin to inspect it.", size=13, color=MUTED
    )

    events_column = ft.Column(spacing=6)

    lot_holder = ft.Container()

    # ---------- Builders ----------
    def card(content, padding=16, expand=False):
        return ft.Container(
            content=content,
            bgcolor=PANEL,
            border_radius=18,
            padding=padding,
            expand=expand,
            shadow=shadow(14, 0.3),
        )

    def stat_card(title, value_control, icon, color):
        return card(
            ft.Column(
                [
                    ft.Icon(icon, color=color, size=24),
                    value_control,
                    ft.Text(title, size=12, color=MUTED),
                ],
                spacing=4,
            ),
            expand=True,
        )

    def legend_item(color, label):
        return ft.Row(
            [
                ft.Container(width=12, height=12, bgcolor=color, border_radius=3),
                ft.Text(label, size=12, color=MUTED),
            ],
            spacing=6,
        )

    def select_slot(slot_id):
        state["selected"] = slot_id
        refresh_selected()
        render_lot()
        page.update()

    def make_bay(slot, facing_down):
        slot_id = slot.get("id", "?")
        occupied = slot.get("status") == 1
        selected = state["selected"] == slot_id

        label = ft.Container(
            content=ft.Text(
                f"{slot_id}",
                size=13,
                weight=ft.FontWeight.BOLD,
                color=RED if occupied else GREEN,
            ),
            alignment=ft.Alignment.CENTER,
            height=22,
        )

        if occupied:
            body = build_car(CAR_COLORS[sum(ord(ch) for ch in str(slot_id)) % len(CAR_COLORS)], facing_down)
        else:
            body = ft.Container(
                width=46,
                height=96,
                alignment=ft.Alignment.CENTER,
                content=ft.Icon(
                    ft.Icons.LOCAL_PARKING, size=40, color=alpha(0.75, GREEN)
                ),
            )

        # Label sits at the far (back) end of the bay, away from the lane
        items = [label, body] if facing_down else [body, label]

        inner = ft.Container(
            expand=True,
            bgcolor=OCC_BAY if occupied else FREE_BAY,
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                items,
                spacing=4,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        # Outer container acts as the painted bay lines
        return ft.Container(
            width=BAY_W,
            height=BAY_H,
            padding=2,
            bgcolor=CYAN if selected else LINE,
            border_radius=4,
            content=inner,
            on_click=lambda e, sid=slot_id: select_slot(sid),
            ink=True,
        )

    def render_lot():
        slots = [{"id": k, "status": v} for k, v in state["slots"].items()]
        if not slots:
            lot_holder.content = ft.Text("No parking slots found.", color=MUTED)
            return

        per_row = math.ceil(len(slots) / 2)
        top_slots = slots[:per_row]
        bottom_slots = slots[per_row:]
        lot_width = per_row * BAY_W

        top_row = ft.Row(
            [make_bay(s, facing_down=True) for s in top_slots],
            spacing=0,
        )
        bottom_row = ft.Row(
            [make_bay(s, facing_down=False) for s in bottom_slots],
            spacing=0,
        )

        arrows = [
            ft.Icon(ft.Icons.ARROW_FORWARD, size=22, color=alpha(0.35, LINE))
            for _ in range(max(3, per_row))
        ]
        lane = ft.Container(
            width=lot_width,
            height=74,
            bgcolor=LANE,
            content=ft.Row(
                [
                    ft.Text("ENTRY", size=12, weight=ft.FontWeight.BOLD, color=CYAN),
                    *arrows,
                    ft.Text("EXIT", size=12, weight=ft.FontWeight.BOLD, color=CYAN),
                ],
                alignment=ft.MainAxisAlignment.SPACE_AROUND,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        lot = ft.Container(
            width=lot_width + 40,
            bgcolor=ASPHALT,
            border_radius=14,
            padding=20,
            shadow=shadow(18, 0.45),
            content=ft.Column(
                [top_row, lane, bottom_row],
                spacing=0,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        lot_holder.content = ft.Row([lot], scroll=ft.ScrollMode.AUTO)

    def refresh_selected():
        sid = state["selected"]
        if sid is None or sid not in state["slots"]:
            selected_title.value = "Tap any bay"
            selected_detail.value = "Select a slot in the twin to inspect it."
            return
        occupied = state["slots"][sid] == 1
        selected_title.value = f"Slot {sid}"
        selected_detail.value = (
            "Status: Occupied - a vehicle is detected."
            if occupied
            else "Status: Available - the bay is free."
        )

    def add_event(text, color):
        events_column.controls.insert(
            0,
            ft.Row(
                [
                    ft.Icon(ft.Icons.CIRCLE, size=8, color=color),
                    ft.Text(text, size=12, color=TEXT),
                ],
                spacing=8,
            ),
        )
        del events_column.controls[8:]

    # ---------- Data loading ----------
    async def load_parking_slots(e=None):
        loader.visible = True
        page.update()

        try:
            data = await asyncio.to_thread(fetch_slots)

            current = {}
            for row in data:
                if "id" in row:
                    current[row["id"]] = row.get("status")

            # Detect changes since the last refresh and log them
            now = datetime.now().strftime("%H:%M:%S")
            if not state["first_load"]:
                for sid, status in current.items():
                    old = state["previous"].get(sid)
                    if old is not None and old != status:
                        if status == 1:
                            add_event(f"{now}  Slot {sid} became occupied", RED)
                        else:
                            add_event(f"{now}  Slot {sid} is now free", GREEN)
            state["first_load"] = False
            state["previous"] = dict(current)
            state["slots"] = current

            total = len(current)
            occupied = sum(1 for v in current.values() if v == 1)
            available = total - occupied
            ratio = occupied / total if total else 0

            total_text.value = str(total)
            available_text.value = str(available)
            occupied_text.value = str(occupied)
            occupancy_bar.value = ratio
            occupancy_label.value = f"Occupancy {ratio * 100:.0f}%"

            render_lot()
            refresh_selected()

            status_text.value = f"Synced at {now}"
            status_text.color = GREEN
            live_dot.color = GREEN

        except Exception as error:
            status_text.value = f"Unable to load parking data: {error}"
            status_text.color = RED
            live_dot.color = RED

        loader.visible = False
        page.update()

    async def auto_refresh():
        try:
            while True:
                await asyncio.sleep(REFRESH_SECONDS)
                await load_parking_slots()
        except Exception:
            # Page closed; stop quietly
            pass

    # ---------- Layout ----------
    header = ft.Container(
        bgcolor=PANEL,
        border_radius=18,
        padding=20,
        shadow=shadow(14, 0.3),
        content=ft.Row(
            [
                ft.Row(
                    [
                        ft.Container(
                            width=52,
                            height=52,
                            bgcolor=alpha(0.15, CYAN),
                            border_radius=14,
                            alignment=ft.Alignment.CENTER,
                            content=ft.Icon(
                                ft.Icons.LOCAL_PARKING, size=32, color=CYAN
                            ),
                        ),
                        ft.Column(
                            [
                                ft.Text(
                                    "Smart Parking",
                                    size=26,
                                    weight=ft.FontWeight.BOLD,
                                    color=TEXT,
                                ),
                                ft.Text(
                                    "Digital twin - live view of every slot",
                                    size=13,
                                    color=MUTED,
                                ),
                            ],
                            spacing=2,
                        ),
                    ],
                    spacing=14,
                ),
                ft.Row(
                    [
                        live_dot,
                        ft.Text(
                            "LIVE",
                            size=12,
                            weight=ft.FontWeight.BOLD,
                            color=GREEN,
                        ),
                    ],
                    spacing=6,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            wrap=True,
        ),
    )

    stats_row = ft.Row(
        [
            stat_card("Total slots", total_text, ft.Icons.GRID_VIEW, CYAN),
            stat_card("Available", available_text, ft.Icons.CHECK_CIRCLE, GREEN),
            stat_card("Occupied", occupied_text, ft.Icons.DIRECTIONS_CAR, RED),
        ],
        spacing=12,
    )

    occupancy_card = card(
        ft.Column([occupancy_label, occupancy_bar], spacing=8), padding=16
    )

    twin_card = card(
        ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(
                            "Lot Overview",
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=TEXT,
                        ),
                        ft.Row(
                            [
                                legend_item(GREEN, "Available"),
                                legend_item(RED, "Occupied"),
                                legend_item(CYAN, "Selected"),
                            ],
                            spacing=14,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    wrap=True,
                ),
                lot_holder,
            ],
            spacing=14,
        )
    )

    inspector_card = card(
        ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.SENSORS, size=18, color=CYAN),
                        ft.Text(
                            "Slot Inspector",
                            size=15,
                            weight=ft.FontWeight.BOLD,
                            color=TEXT,
                        ),
                    ],
                    spacing=8,
                ),
                selected_title,
                selected_detail,
            ],
            spacing=6,
        )
    )

    events_card = card(
        ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.HISTORY, size=18, color=CYAN),
                        ft.Text(
                            "Live Events",
                            size=15,
                            weight=ft.FontWeight.BOLD,
                            color=TEXT,
                        ),
                    ],
                    spacing=8,
                ),
                events_column,
                ft.Text(
                    "Changes appear here as sensors report them.",
                    size=11,
                    color=MUTED,
                ),
            ],
            spacing=10,
        )
    )

    footer = ft.Row(
        [
            ft.Row([loader, status_text], spacing=8),
            ft.Button(
                "Refresh now",
                icon=ft.Icons.REFRESH,
                on_click=load_parking_slots,
            ),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        wrap=True,
    )

    page.add(
        ft.SafeArea(
            content=ft.Column(
                [
                    header,
                    stats_row,
                    occupancy_card,
                    twin_card,
                    ft.Row(
                        [
                            ft.Container(inspector_card, expand=True),
                            ft.Container(events_card, expand=True),
                        ],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                    footer,
                ],
                spacing=16,
            ),
        )
    )

    page.run_task(load_parking_slots)
    page.run_task(auto_refresh)


if __name__ == "__main__":
    ft.run(main)