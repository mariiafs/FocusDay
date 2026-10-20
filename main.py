
"""FocusDay — rotina e foco de estudo com Flet.

Execução local:
    pip install -U flet
    python main.py

Armazenamento:
    - Computador: ~/.focusday/data.json
    - Web: armazenamento local do navegador de cada visitante
"""

import asyncio
import json
import sys
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import flet as ft


# ============================================================
# PALETA
# ============================================================

BG = "#F7F7F5"
WHITE = "#FFFFFF"
INK = "#252525"
MUTED = "#6B6B68"
INDIGO = "#4B49D1"
INDIGO_LIGHT = "#E4E3FA"
GREEN = "#30B35A"
GREEN_DARK = "#1E8A3E"
GREEN_LIGHT = "#DDF3E3"
ORANGE = "#C2410C"
LINK = "#0062CC"
SEPARATOR = "#E5E5E0"
CHIP = "#E5E5EA"
DANGER = "#C62828"

DIAS = [
    "Segunda", "Terça", "Quarta", "Quinta",
    "Sexta", "Sábado", "Domingo"
]
INICIAIS = ["S", "T", "Q", "Q", "S", "S", "D"]
MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio",
    "junho", "julho", "agosto", "setembro", "outubro",
    "novembro", "dezembro"
]

DATA_DIR = Path.home() / ".focusday"
DATA_FILE = DATA_DIR / "data.json"
STORAGE_KEY = "focusday.data.v1"


# ============================================================
# COMPATIBILIDADE COM FLET
# ============================================================

def pad_only(left=0, top=0, right=0, bottom=0):
    return ft.Padding(
        left=left, top=top, right=right, bottom=bottom
    )


def pad_sym(horizontal=0, vertical=0):
    return ft.Padding(
        left=horizontal,
        top=vertical,
        right=horizontal,
        bottom=vertical,
    )


ALIGN_CENTER = ft.Alignment(0, 0)
ALIGN_LEFT = ft.Alignment(-1, 0)


def Option(key, text):
    cls = getattr(ft, "DropdownOption", None) or ft.dropdown.Option
    return cls(key=key, text=text)


def show_dialog(page, ctrl):
    if hasattr(page, "show_dialog"):
        page.show_dialog(ctrl)
    else:
        page.open(ctrl)


def close_dialog(page, ctrl):
    if hasattr(page, "pop_dialog"):
        page.pop_dialog()
    else:
        page.close(ctrl)


def btn_style(bg):
    return ft.ButtonStyle(
        bgcolor=bg,
        color=WHITE,
        shape=ft.RoundedRectangleBorder(radius=24),
    )


def action_button(label, on_click, icon=None, bg=INDIGO, height=44):
    parts = []

    if icon:
        parts.append(ft.Icon(icon, color=WHITE, size=20))

    parts.append(
        ft.Text(
            label,
            color=WHITE,
            size=16,
            weight=ft.FontWeight.W_600,
        )
    )

    return ft.FilledButton(
        content=ft.Row(parts, tight=True, spacing=6),
        height=height,
        on_click=on_click,
        style=btn_style(bg),
    )


# ============================================================
# DADOS E ARMAZENAMENTO
# ============================================================

def default_data():
    return {
        "nome": "",
        "welcomed": False,
        "meta_min": 240,
        "foco_min": 25,
        "pausa_min": 5,
        "tarefas": [],
        "sessoes": [],
    }


async def load_data(prefs=None):
    """Carrega os dados do navegador ou do arquivo local."""
    data = default_data()

    if prefs is not None:
        try:
            raw = await prefs.get(STORAGE_KEY)
            if raw:
                loaded = json.loads(raw)
                if isinstance(loaded, dict):
                    data.update(loaded)
        except Exception:
            pass
    else:
        try:
            loaded = json.loads(
                DATA_FILE.read_text(encoding="utf-8")
            )
            if isinstance(loaded, dict):
                data.update(loaded)
        except (OSError, ValueError, TypeError):
            pass

    return data


def save_data_file(data):
    """Salva os dados no computador."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def today_str():
    return date.today().isoformat()


def fmt_min(m):
    h, mm = divmod(int(m), 60)

    if h and mm:
        return f"{h}h{mm:02d}"
    if h:
        return f"{h}h"
    return f"{mm} min"


def friendly_date(iso):
    d = date.fromisoformat(iso)
    diff = (d - date.today()).days

    if diff == 0:
        return "Hoje"
    if diff == 1:
        return "Amanhã"
    if diff == -1:
        return "Ontem"

    return f"{DIAS[d.weekday()]}, {d.day} de {MESES[d.month - 1]}"


# ============================================================
# APLICATIVO
# ============================================================

class FocusDay:
    def __init__(self, page: ft.Page, data, prefs=None):
        self.page = page
        self.d = data
        self.prefs = prefs

        # Temporizador
        self.modo = "foco"
        self.restante = self.d["foco_min"] * 60
        self.rodando = False
        self.fim = 0.0
        self.gen = 0
        self.sel_task = "free"

        page.title = "FocusDay"
        page.bgcolor = BG
        page.padding = 0

        # Propriedades da janela para execução no computador.
        if sys.platform != "emscripten":
            try:
                page.window.width = 393
                page.window.height = 852
            except Exception:
                pass

        # Controles do temporizador
        self.t_text = ft.Text(
            "", size=52, weight=ft.FontWeight.BOLD, color=INK
        )
        self.t_label = ft.Text("", size=15, color=MUTED)

        self.t_ring = ft.ProgressRing(
            value=0,
            width=240,
            height=240,
            stroke_width=12,
            color=INDIGO,
            bgcolor=INDIGO_LIGHT,
        )

        self.t_btn_txt = ft.Text(
            "Iniciar", color=WHITE, size=16,
            weight=ft.FontWeight.W_600
        )
        self.t_icon_play = ft.Icon(
            ft.Icons.PLAY_ARROW, color=WHITE, size=20
        )
        self.t_icon_pause = ft.Icon(
            ft.Icons.PAUSE, color=WHITE, size=20, visible=False
        )

        self.t_btn = ft.FilledButton(
            content=ft.Row(
                [
                    self.t_icon_play,
                    self.t_icon_pause,
                    self.t_btn_txt,
                ],
                tight=True,
                spacing=6,
            ),
            height=48,
            on_click=self.toggle_timer,
            style=btn_style(INDIGO),
        )

        self.dd = ft.Dropdown(
            label="O que você vai estudar?",
            value="free",
            expand=True,
        )

        self.materia_tf = ft.TextField(
            label="Matéria (sessão livre)",
            border_radius=12,
            bgcolor=WHITE,
        )

        self.mode_row = ft.Row(
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=8,
        )

        self.sessoes_hoje_txt = ft.Text("", size=15, color=MUTED)

        self.body = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=0,
        )

        self.nav = ft.NavigationBar(
            bgcolor="#F9F9F9",
            indicator_color=INDIGO_LIGHT,
            selected_index=0,
            on_change=lambda e: self.go(e.control.selected_index),
            destinations=[
                ft.NavigationBarDestination(
                    icon=ft.Icons.GRID_VIEW, label="Resumo"
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.CALENDAR_MONTH_OUTLINED,
                    label="Rotina",
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.TIMER_OUTLINED, label="Foco"
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.BAR_CHART, label="Progresso"
                ),
            ],
        )

        page.navigation_bar = self.nav
        page.add(self.body)

        self.sync_timer()
        self.render()

        if not self.d["welcomed"]:
            self.open_settings(welcome=True)

    # --------------------------------------------------------
    # UTILITÁRIOS
    # --------------------------------------------------------

    async def save(self):
        """Salva no navegador ou no arquivo local."""
        if self.prefs is not None:
            await self.prefs.set(
                STORAGE_KEY,
                json.dumps(self.d, ensure_ascii=False),
            )
        else:
            save_data_file(self.d)

    def snack(self, msg):
        show_dialog(self.page, ft.SnackBar(ft.Text(msg)))

    def go(self, i):
        self.nav.selected_index = i
        self.render()

    def render(self):
        views = [
            self.view_resumo,
            self.view_rotina,
            self.view_foco,
            self.view_progresso,
        ]
        self.body.controls = views[self.nav.selected_index]()
        self.page.update()

    def card(self, content, expand=None, padding=16):
        return ft.Container(
            content=content,
            bgcolor=WHITE,
            border_radius=20,
            padding=padding,
            expand=expand,
        )

    def card_header(self, icon, label, color):
        return ft.Row(
            [
                ft.Icon(icon, color=color, size=18),
                ft.Text(
                    label, size=15,
                    weight=ft.FontWeight.W_600, color=color
                ),
            ],
            spacing=6,
        )

    def header(self, titulo, subtitulo):
        nome = self.d["nome"].strip()

        return ft.Container(
            padding=pad_only(left=20, right=20, top=24),
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(subtitulo, size=14, color=MUTED),
                            ft.Text(
                                titulo,
                                size=34,
                                weight=ft.FontWeight.BOLD,
                                color=INK,
                            ),
                        ],
                        spacing=0,
                    ),
                    ft.Container(
                        content=ft.Text(
                            nome[:1].upper() if nome else "?",
                            size=16,
                            weight=ft.FontWeight.W_600,
                            color="#3A3A3C",
                        ),
                        width=44,
                        height=44,
                        border_radius=22,
                        bgcolor="#D1D1D6",
                        alignment=ALIGN_CENTER,
                        tooltip="Configurações",
                        on_click=lambda e: self.open_settings(),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
        )

    def section(self, titulo, action_label=None, on_action=None):
        row = [
            ft.Text(
                titulo, size=20,
                weight=ft.FontWeight.BOLD, color=INK
            )
        ]

        if action_label:
            row.append(
                ft.TextButton(
                    action_label,
                    on_click=on_action,
                    style=ft.ButtonStyle(color=LINK),
                )
            )

        return ft.Row(
            row, alignment=ft.MainAxisAlignment.SPACE_BETWEEN
        )

    def empty(self, texto, botao=None, on_click=None):
        items = [
            ft.Text(
                texto,
                size=15,
                color=MUTED,
                text_align=ft.TextAlign.CENTER,
            )
        ]

        if botao:
            items.append(
                ft.TextButton(
                    botao,
                    on_click=on_click,
                    style=ft.ButtonStyle(color=LINK),
                )
            )

        return ft.Container(
            padding=20,
            alignment=ALIGN_CENTER,
            content=ft.Column(
                items,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=4,
            ),
        )

    def wrap(self, *controls):
        return ft.Container(
            padding=pad_only(
                left=16, right=16, top=12, bottom=24
            ),
            content=ft.Column(list(controls), spacing=12),
        )

    # --------------------------------------------------------
    # ESTATÍSTICAS
    # --------------------------------------------------------

    def minutos_em(self, iso):
        return sum(
            s["minutos"]
            for s in self.d["sessoes"]
            if s["data"] == iso
        )

    def sessoes_em(self, iso):
        return [
            s for s in self.d["sessoes"]
            if s["data"] == iso
        ]

    def streak(self):
        dias = {
            s["data"]
            for s in self.d["sessoes"]
            if s["minutos"] > 0
        }

        d = date.today()
        if d.isoformat() not in dias:
            d -= timedelta(days=1)

        n = 0
        while d.isoformat() in dias:
            n += 1
            d -= timedelta(days=1)

        return n

    def tarefas_do_dia(self, iso):
        ts = [
            t for t in self.d["tarefas"]
            if t["data"] == iso
        ]
        return sorted(
            ts, key=lambda t: (t["hora"] == "", t["hora"])
        )

    def pendentes_hoje(self):
        return [
            t for t in self.tarefas_do_dia(today_str())
            if not t["feito"]
        ]

    # --------------------------------------------------------
    # TAREFAS
    # --------------------------------------------------------

    def task_row(self, t, deletar=False):
        feito = t["feito"]
        sub = " · ".join(
            x for x in [
                t.get("materia", ""),
                fmt_min(t["duracao"]),
            ]
            if x
        )

        async def toggle(e):
            t["feito"] = not t["feito"]
            await self.save()
            self.render()

        async def delete(e):
            self.d["tarefas"] = [
                x for x in self.d["tarefas"]
                if x["id"] != t["id"]
            ]
            await self.save()
            self.render()
            self.snack("Tarefa removida")

        controls = [
            ft.IconButton(
                icon=(
                    ft.Icons.CHECK_CIRCLE
                    if feito
                    else ft.Icons.RADIO_BUTTON_UNCHECKED
                ),
                icon_color=GREEN if feito else INDIGO,
                icon_size=26,
                on_click=toggle,
                tooltip="Desmarcar" if feito else "Marcar como feita",
            ),
            ft.Column(
                [
                    ft.Text(
                        t["titulo"],
                        size=17,
                        color=MUTED if feito else INK,
                        weight=(
                            ft.FontWeight.NORMAL
                            if feito
                            else ft.FontWeight.W_500
                        ),
                        style=ft.TextStyle(
                            decoration=(
                                ft.TextDecoration.LINE_THROUGH
                                if feito
                                else ft.TextDecoration.NONE
                            )
                        ),
                    ),
                    ft.Text(sub, size=13, color=MUTED),
                ],
                spacing=0,
                expand=True,
            ),
            ft.Text(t["hora"], size=15, color=MUTED),
        ]

        if deletar:
            controls.append(
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    icon_color=MUTED,
                    tooltip="Excluir",
                    on_click=delete,
                )
            )
        else:
            controls.append(ft.Container(width=8))

        return ft.Container(
            padding=pad_sym(horizontal=8, vertical=4),
            content=ft.Row(
                controls,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def task_list_card(self, tarefas, deletar=False):
        rows = []

        for i, t in enumerate(tarefas):
            if i:
                rows.append(
                    ft.Divider(
                        height=0.5,
                        thickness=0.5,
                        color=SEPARATOR,
                    )
                )
            rows.append(self.task_row(t, deletar))

        return ft.Container(
            content=ft.Column(rows, spacing=0),
            bgcolor=WHITE,
            border_radius=20,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )

    def open_add_task(self, e=None):
        titulo = ft.TextField(label="Tarefa", autofocus=True)
        materia = ft.TextField(label="Matéria (opcional)")
        duracao = ft.TextField(
            label="Duração (min)",
            value="45",
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        hora = ft.TextField(
            label="Horário (HH:MM, opcional)",
            hint_text="09:30",
        )

        opcoes = []
        for i in range(7):
            d = date.today() + timedelta(days=i)
            opcoes.append(
                Option(
                    key=str(i),
                    text=friendly_date(d.isoformat()),
                )
            )

        dia = ft.Dropdown(label="Dia", value="0", options=opcoes)

        async def salvar(ev):
            ok = True
            titulo.error_text = None
            duracao.error_text = None
            hora.error_text = None

            if not (titulo.value or "").strip():
                titulo.error_text = "Informe o nome da tarefa"
                ok = False

            try:
                dur = int(duracao.value)
                if dur <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                duracao.error_text = "Use um número maior que 0"
                ok = False

            h = (hora.value or "").strip()
            if h:
                try:
                    h = datetime.strptime(h, "%H:%M").strftime("%H:%M")
                except ValueError:
                    hora.error_text = "Use o formato HH:MM"
                    ok = False

            if not ok:
                self.page.update()
                return

            dia_iso = (
                date.today()
                + timedelta(days=int(dia.value or 0))
            ).isoformat()

            self.d["tarefas"].append(
                {
                    "id": uuid.uuid4().hex,
                    "titulo": titulo.value.strip(),
                    "materia": (materia.value or "").strip(),
                    "duracao": dur,
                    "hora": h,
                    "data": dia_iso,
                    "feito": False,
                }
            )

            await self.save()
            close_dialog(self.page, dlg)
            self.render()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Nova tarefa"),
            content=ft.Column(
                [titulo, materia, duracao, hora, dia],
                tight=True,
                spacing=8,
                width=320,
                scroll=ft.ScrollMode.AUTO,
            ),
            actions=[
                ft.TextButton(
                    "Cancelar",
                    on_click=lambda ev: close_dialog(self.page, dlg),
                ),
                ft.FilledButton("Salvar", on_click=salvar),
            ],
        )

        show_dialog(self.page, dlg)

    # --------------------------------------------------------
    # CONFIGURAÇÕES
    # --------------------------------------------------------

    def open_settings(self, welcome=False):
        nome = ft.TextField(
            label="Seu nome",
            value=self.d["nome"],
            autofocus=True,
        )
        meta = ft.TextField(
            label="Meta diária (horas)",
            value=f"{self.d['meta_min'] / 60:g}",
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        foco = ft.TextField(
            label="Foco (min)",
            value=str(self.d["foco_min"]),
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        pausa = ft.TextField(
            label="Pausa (min)",
            value=str(self.d["pausa_min"]),
            keyboard_type=ft.KeyboardType.NUMBER,
        )

        async def salvar(ev):
            nome.error_text = None
            meta.error_text = None
            foco.error_text = None
            pausa.error_text = None
            ok = True

            try:
                meta_min = round(
                    float(meta.value.replace(",", ".")) * 60
                )
                if not 15 <= meta_min <= 1440:
                    raise ValueError
            except (ValueError, TypeError, AttributeError):
                meta.error_text = "Entre 0,25 e 24 horas"
                ok = False

            try:
                foco_min = int(foco.value)
                if not 1 <= foco_min <= 180:
                    raise ValueError
            except (ValueError, TypeError):
                foco.error_text = "Entre 1 e 180"
                ok = False

            try:
                pausa_min = int(pausa.value)
                if not 1 <= pausa_min <= 60:
                    raise ValueError
            except (ValueError, TypeError):
                pausa.error_text = "Entre 1 e 60"
                ok = False

            if not ok:
                self.page.update()
                return

            self.d.update(
                nome=nome.value.strip(),
                meta_min=meta_min,
                foco_min=foco_min,
                pausa_min=pausa_min,
                welcomed=True,
            )

            await self.save()

            if not self.rodando:
                self.restante = self._total()

            self.sync_timer()
            close_dialog(self.page, dlg)
            self.render()

        async def fechar(ev):
            self.d["welcomed"] = True
            await self.save()
            close_dialog(self.page, dlg)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "Bem-vindo ao FocusDay"
                if welcome
                else "Configurações"
            ),
            content=ft.Column(
                [nome, meta, foco, pausa],
                tight=True,
                spacing=8,
                width=320,
                scroll=ft.ScrollMode.AUTO,
            ),
            actions=[
                ft.TextButton(
                    "Agora não" if welcome else "Cancelar",
                    on_click=fechar,
                ),
                ft.FilledButton("Salvar", on_click=salvar),
            ],
        )

        show_dialog(self.page, dlg)

    # --------------------------------------------------------
    # TEMPORIZADOR
    # --------------------------------------------------------

    def _total(self):
        minutos = (
            self.d["foco_min"]
            if self.modo == "foco"
            else self.d["pausa_min"]
        )
        return minutos * 60

    def sync_timer(self):
        total = self._total()
        m, s = divmod(max(self.restante, 0), 60)

        self.t_text.value = f"{m:02d}:{s:02d}"
        self.t_ring.value = (
            min(max(1 - self.restante / total, 0), 1)
            if total
            else 0
        )

        em_foco = self.modo == "foco"
        self.t_ring.color = INDIGO if em_foco else GREEN_DARK
        self.t_ring.bgcolor = (
            INDIGO_LIGHT if em_foco else GREEN_LIGHT
        )
        self.t_label.value = (
            "Hora de focar" if em_foco else "Hora da pausa"
        )

        self.t_btn_txt.value = (
            "Pausar"
            if self.rodando
            else "Continuar"
            if self.restante != total
            else "Iniciar"
        )

        self.t_icon_play.visible = not self.rodando
        self.t_icon_pause.visible = self.rodando
        self.t_btn.style = btn_style(
            INDIGO if em_foco else GREEN_DARK
        )

        hoje = self.sessoes_em(today_str())
        self.sessoes_hoje_txt.value = (
            f"Hoje: {len(hoje)} sessão(ões) · "
            f"{fmt_min(self.minutos_em(today_str()))}"
        )

    def toggle_timer(self, e=None):
        if self.rodando:
            self.restante = max(
                0, round(self.fim - time.time())
            )
            self.rodando = False
            self.gen += 1
        else:
            self.rodando = True
            self.fim = time.time() + self.restante
            self.gen += 1

            # Agenda a contagem assíncrona sem bloquear a interface.
            self.page.run_task(self._loop, self.gen)

        self.sync_timer()
        self.page.update()

    async def _loop(self, gen):
        while self.rodando and self.gen == gen:
            rest = round(self.fim - time.time())

            if rest <= 0:
                break

            if rest != self.restante:
                self.restante = rest
                self.sync_timer()
                self.page.update()

            await asyncio.sleep(0.2)

        if self.rodando and self.gen == gen:
            await self._finish()

    async def _finish(self):
        self.rodando = False
        self.gen += 1

        if self.modo == "foco":
            minutos = self.d["foco_min"]

            task = next(
                (
                    t for t in self.d["tarefas"]
                    if t["id"] == self.dd.value
                ),
                None,
            )

            if task:
                materia = task.get("materia") or task["titulo"]
            else:
                materia = (
                    (self.materia_tf.value or "").strip()
                    or "Geral"
                )

            self.d["sessoes"].append(
                {
                    "data": today_str(),
                    "minutos": minutos,
                    "materia": materia,
                    "hora": datetime.now().strftime("%H:%M"),
                }
            )

            await self.save()
            self.modo = "pausa"
            self.snack(
                f"Sessão concluída! +{minutos} min. Hora da pausa."
            )
        else:
            self.modo = "foco"
            self.snack("Pausa encerrada. Vamos focar?")

        self.restante = self._total()
        self.sync_timer()
        self.render()

    def set_mode(self, modo):
        if self.rodando:
            self.rodando = False
            self.gen += 1

        self.modo = modo
        self.restante = self._total()
        self.sync_timer()
        self.render()

    def reset_timer(self, e=None):
        self.rodando = False
        self.gen += 1
        self.restante = self._total()
        self.sync_timer()
        self.page.update()

    # --------------------------------------------------------
    # TELA: RESUMO
    # --------------------------------------------------------

    def view_resumo(self):
        hora = datetime.now().hour
        saud = (
            "Bom dia" if hora < 12
            else "Boa tarde" if hora < 18
            else "Boa noite"
        )

        nome = self.d["nome"].strip()
        sub = f"{saud}, {nome}" if nome else saud

        pend = self.pendentes_hoje()
        proxima = pend[0] if pend else None

        def iniciar(e):
            self.sel_task = (
                proxima["id"] if proxima else "free"
            )
            self.go(2)

        focus_card = self.card(
            ft.Column(
                [
                    self.card_header(
                        ft.Icons.TIMER_OUTLINED, "Foco", INDIGO
                    ),
                    ft.Text(
                        f"Próxima: {proxima['titulo']}"
                        if proxima
                        else "Nenhuma tarefa pendente para hoje",
                        size=15,
                        color=MUTED,
                    ),
                    ft.Row(
                        [
                            ft.Row(
                                [
                                    ft.Text(
                                        str(self.d["foco_min"]),
                                        size=44,
                                        weight=ft.FontWeight.BOLD,
                                        color=INK,
                                    ),
                                    ft.Text(
                                        "min", size=17,
                                        weight=ft.FontWeight.W_600,
                                        color=MUTED,
                                    ),
                                ],
                                spacing=4,
                                vertical_alignment=(
                                    ft.CrossAxisAlignment.END
                                ),
                            ),
                            action_button("Iniciar", iniciar),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.END,
                    ),
                ],
                spacing=8,
            )
        )

        estudado = self.minutos_em(today_str())
        meta = max(self.d["meta_min"], 1)

        goal_card = self.card(
            ft.Column(
                [
                    self.card_header(
                        ft.Icons.TRACK_CHANGES, "Meta", GREEN_DARK
                    ),
                    ft.Row(
                        [
                            ft.ProgressRing(
                                value=min(estudado / meta, 1),
                                width=52,
                                height=52,
                                stroke_width=7,
                                color=GREEN,
                                bgcolor=GREEN_LIGHT,
                            ),
                            ft.Column(
                                [
                                    ft.Text(
                                        fmt_min(estudado),
                                        size=24,
                                        weight=ft.FontWeight.BOLD,
                                        color=INK,
                                    ),
                                    ft.Text(
                                        f"de {fmt_min(self.d['meta_min'])}",
                                        size=13,
                                        color=MUTED,
                                    ),
                                ],
                                spacing=0,
                            ),
                        ],
                        spacing=12,
                    ),
                ],
                spacing=10,
            ),
            expand=True,
        )

        n = self.streak()
        streak_card = self.card(
            ft.Column(
                [
                    self.card_header(
                        ft.Icons.LOCAL_FIRE_DEPARTMENT_OUTLINED,
                        "Sequência",
                        ORANGE,
                    ),
                    ft.Container(
                        height=52,
                        alignment=ALIGN_LEFT,
                        content=ft.Row(
                            [
                                ft.Text(
                                    str(n),
                                    size=44,
                                    weight=ft.FontWeight.BOLD,
                                    color=INK,
                                ),
                                ft.Text(
                                    "dia" if n == 1 else "dias",
                                    size=17,
                                    weight=ft.FontWeight.W_600,
                                    color=MUTED,
                                ),
                            ],
                            spacing=4,
                            vertical_alignment=ft.CrossAxisAlignment.END,
                        ),
                    ),
                ],
                spacing=10,
            ),
            expand=True,
        )

        hoje = self.tarefas_do_dia(today_str())
        lista = (
            self.task_list_card(hoje)
            if hoje
            else self.card(
                self.empty(
                    "Você ainda não planejou o dia.",
                    "Adicionar tarefa",
                    self.open_add_task,
                )
            )
        )

        return [
            self.header("Resumo", sub),
            self.wrap(
                self.section("Hoje"),
                focus_card,
                ft.Row([goal_card, streak_card], spacing=12),
                self.section(
                    "Rotina de hoje",
                    "Ver tudo",
                    lambda e: self.go(1),
                ),
                lista,
            ),
        ]

    # --------------------------------------------------------
    # TELA: ROTINA
    # --------------------------------------------------------

    def view_rotina(self):
        hoje = today_str()
        grupos = {}

        for t in self.d["tarefas"]:
            grupos.setdefault(t["data"], []).append(t)

        blocos = [
            ft.Row(
                [
                    action_button(
                        "Nova tarefa",
                        self.open_add_task,
                        icon=ft.Icons.ADD,
                    )
                ]
            )
        ]

        if not grupos:
            blocos.append(
                self.card(
                    self.empty(
                        "Sua rotina está vazia. "
                        "Adicione as tarefas de estudo do dia."
                    )
                )
            )

        for dia in sorted(grupos):
            titulo = friendly_date(dia)
            atrasada = (
                dia < hoje
                and any(not t["feito"] for t in grupos[dia])
            )

            blocos.append(
                ft.Text(
                    titulo + (" (atrasadas)" if atrasada else ""),
                    size=20,
                    weight=ft.FontWeight.BOLD,
                    color=DANGER if atrasada else INK,
                )
            )

            ordenadas = sorted(
                grupos[dia],
                key=lambda t: (t["hora"] == "", t["hora"]),
            )
            blocos.append(
                self.task_list_card(ordenadas, deletar=True)
            )

        return [
            self.header("Rotina", "FocusDay"),
            self.wrap(*blocos),
        ]

    # --------------------------------------------------------
    # TELA: FOCO
    # --------------------------------------------------------

    def view_foco(self):
        pend = self.pendentes_hoje()

        self.dd.options = [
            Option(key="free", text="Sessão livre")
        ] + [
            Option(key=t["id"], text=t["titulo"])
            for t in pend
        ]

        validos = {"free"} | {t["id"] for t in pend}

        self.dd.value = (
            self.sel_task
            if self.sel_task in validos
            else self.dd.value
            if self.dd.value in validos
            else "free"
        )

        self.sel_task = self.dd.value

        def chip(label, modo):
            ativo = self.modo == modo
            cor = INDIGO if modo == "foco" else GREEN_DARK

            return ft.Container(
                content=ft.Text(
                    label,
                    size=15,
                    weight=ft.FontWeight.W_600,
                    color=WHITE if ativo else INK,
                ),
                padding=pad_sym(horizontal=18, vertical=10),
                border_radius=999,
                bgcolor=cor if ativo else CHIP,
                on_click=lambda e, m=modo: self.set_mode(m),
            )

        self.mode_row.controls = [
            chip("Foco", "foco"),
            chip("Pausa", "pausa"),
        ]

        self.sync_timer()

        ring = ft.Stack(
            [
                self.t_ring,
                ft.Container(
                    width=240,
                    height=240,
                    alignment=ALIGN_CENTER,
                    content=ft.Column(
                        [self.t_text, self.t_label],
                        spacing=0,
                        alignment=ft.MainAxisAlignment.CENTER,
                        horizontal_alignment=(
                            ft.CrossAxisAlignment.CENTER
                        ),
                    ),
                ),
            ],
            width=240,
            height=240,
        )

        controles = ft.Row(
            [
                self.t_btn,
                ft.IconButton(
                    icon=ft.Icons.REPLAY,
                    icon_color=MUTED,
                    tooltip="Reiniciar",
                    on_click=self.reset_timer,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=12,
        )

        return [
            self.header("Foco", "FocusDay"),
            self.wrap(
                self.mode_row,
                ft.Container(
                    content=ring,
                    alignment=ALIGN_CENTER,
                    padding=16,
                ),
                controles,
                ft.Container(
                    content=self.sessoes_hoje_txt,
                    alignment=ALIGN_CENTER,
                ),
                ft.Row([self.dd]),
                self.materia_tf,
            ),
        ]

    # --------------------------------------------------------
    # TELA: PROGRESSO
    # --------------------------------------------------------

    def view_progresso(self):
        sessoes = self.d["sessoes"]
        total_min = sum(s["minutos"] for s in sessoes)

        def stat(icon, cor, valor, rotulo):
            return self.card(
                ft.Column(
                    [
                        self.card_header(icon, rotulo, cor),
                        ft.Text(
                            valor,
                            size=28,
                            weight=ft.FontWeight.BOLD,
                            color=INK,
                        ),
                    ],
                    spacing=8,
                ),
                expand=True,
            )

        n = self.streak()

        linha1 = ft.Row(
            [
                stat(
                    ft.Icons.TIMER_OUTLINED,
                    INDIGO,
                    fmt_min(self.minutos_em(today_str())),
                    "Hoje",
                ),
                stat(
                    ft.Icons.LOCAL_FIRE_DEPARTMENT_OUTLINED,
                    ORANGE,
                    f"{n} {'dia' if n == 1 else 'dias'}",
                    "Sequência",
                ),
            ],
            spacing=12,
        )

        linha2 = ft.Row(
            [
                stat(
                    ft.Icons.SCHEDULE,
                    GREEN_DARK,
                    fmt_min(total_min),
                    "Total",
                ),
                stat(
                    ft.Icons.CHECK_CIRCLE_OUTLINE,
                    INDIGO,
                    str(len(sessoes)),
                    "Sessões",
                ),
            ],
            spacing=12,
        )

        # Gráfico dos últimos sete dias
        dias = [
            date.today() - timedelta(days=i)
            for i in range(6, -1, -1)
        ]
        valores = [
            self.minutos_em(d.isoformat())
            for d in dias
        ]
        maximo = max(max(valores), self.d["meta_min"], 1)

        barras = []

        for d, v in zip(dias, valores):
            altura = max(4, round(120 * v / maximo)) if v else 4

            barras.append(
                ft.Column(
                    [
                        ft.Text(
                            str(v) if v else "",
                            size=11,
                            color=MUTED,
                        ),
                        ft.Container(
                            width=28,
                            height=altura,
                            border_radius=8,
                            bgcolor=INDIGO if v else CHIP,
                        ),
                        ft.Text(
                            INICIAIS[d.weekday()],
                            size=13,
                            weight=(
                                ft.FontWeight.BOLD
                                if d == date.today()
                                else ft.FontWeight.NORMAL
                            ),
                            color=INK if d == date.today() else MUTED,
                        ),
                    ],
                    spacing=4,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    alignment=ft.MainAxisAlignment.END,
                )
            )

        grafico = self.card(
            ft.Column(
                [
                    ft.Text(
                        "Minutos por dia (7 dias)",
                        size=15,
                        weight=ft.FontWeight.W_600,
                        color=INK,
                    ),
                    ft.Container(
                        height=170,
                        content=ft.Row(
                            barras,
                            alignment=ft.MainAxisAlignment.SPACE_AROUND,
                            vertical_alignment=ft.CrossAxisAlignment.END,
                        ),
                    ),
                ],
                spacing=8,
            )
        )

        # Progresso por matéria
        por_materia = {}

        for s in sessoes:
            materia = s["materia"]
            por_materia[materia] = (
                por_materia.get(materia, 0) + s["minutos"]
            )

        if por_materia:
            linhas = []
            topo = max(por_materia.values())

            for nome, mins in sorted(
                por_materia.items(),
                key=lambda kv: -kv[1],
            ):
                linhas.append(
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(nome, size=15, color=INK),
                                    ft.Text(
                                        fmt_min(mins),
                                        size=15,
                                        color=MUTED,
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            ),
                            ft.ProgressBar(
                                value=mins / topo,
                                color=INDIGO,
                                bgcolor=INDIGO_LIGHT,
                                height=8,
                                border_radius=4,
                            ),
                        ],
                        spacing=4,
                    )
                )

            materias = self.card(
                ft.Column(linhas, spacing=12)
            )
        else:
            materias = self.card(
                self.empty(
                    "Conclua uma sessão de foco para ver "
                    "seu progresso por matéria."
                )
            )

        return [
            self.header("Progresso", "FocusDay"),
            self.wrap(
                linha1,
                linha2,
                grafico,
                self.section("Por matéria"),
                materias,
            ),
        ]


# ============================================================
# INICIALIZAÇÃO
# ============================================================

async def main(page: ft.Page):
    # Na versão web, SharedPreferences usa o armazenamento
    # do navegador. No computador, continuamos usando o arquivo.
    prefs = (
        ft.SharedPreferences()
        if sys.platform == "emscripten"
        else None
    )

    data = await load_data(prefs)
    FocusDay(page, data, prefs)


if __name__ == "__main__":
    if hasattr(ft, "run"):
        ft.run(main)
    else:
        ft.app(target=main)
