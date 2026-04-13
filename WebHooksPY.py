import customtkinter as ctk
from customtkinter import filedialog
from CTkColorPicker import AskColor
import requests
import json
import os
import sys
import re
from PIL import Image, ImageDraw, ImageTk, ImageGrab
import io
import time
from datetime import datetime
import ctypes
import uuid
import threading

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

DATA_FILE = "dados_webhooks.json"
DEFAULT_AVATAR_URL = "[https://cdn.discordapp.com/embed/avatars/0.png](https://cdn.discordapp.com/embed/avatars/0.png)"

# --- FORÇAR O ÍCONE NA BARRA DE TAREFAS DO WINDOWS ---
try:
    myappid = 'heitor.webhookspy.desktop.pro.final'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except:
    pass


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class WebHooksPY(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("WebHooksPY")
        self.geometry("1300x800")

        try:
            caminho_icone = resource_path("icon.png")
            if os.path.exists(caminho_icone):
                self.icon_image = ImageTk.PhotoImage(Image.open(caminho_icone))
                self.wm_iconphoto(True, self.icon_image)
        except Exception as e:
            print(f"Aviso: Não foi possível carregar o ícone. Detalhes: {e}")

        self.dados = self.load_data()
        self.webhook_atual = None
        self.mensagem_editando_id = None

        self.preview_timer = None

        # --- CACHE E CONTROLE DE DOWNLOADS ---
        self.image_cache = {}
        self.fetching_images = set()

        self.webhook_default_name = "WebHooksPY"
        self.webhook_default_avatar = ""
        self.avatar_url_cache = ""

        self.embed_uis = []
        self.arquivos_anexados = []

        self.setup_ui()
        self.atualizar_lista_webhooks()
        self.update_preview()

    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                return {"webhooks": {}}
        return {"webhooks": {}}

    def save_data(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.dados, f, indent=4)

    def mostrar_notificacao(self, mensagem, tipo="sucesso"):
        cores = {
            "sucesso": ("#57F287", "#000000"),
            "erro": ("#ED4245", "#FFFFFF"),
            "aviso": ("#FEE75C", "#000000"),
            "info": ("#5865F2", "#FFFFFF")
        }
        cor_fundo, cor_texto = cores.get(tipo, ("#5865F2", "#FFFFFF"))

        noti_frame = ctk.CTkFrame(self, fg_color=cor_fundo, corner_radius=8)
        noti_frame.place(relx=0.5, rely=0.05, anchor="center")

        lbl = ctk.CTkLabel(noti_frame, text=mensagem, text_color=cor_texto, font=ctk.CTkFont(size=14, weight="bold"))
        lbl.pack(padx=20, pady=10)

        self.after(3000, noti_frame.destroy)

    # ==========================================
    # LÓGICA DE SUAVIZAÇÃO E REDIMENSIONAMENTO
    # ==========================================
    def agendar_update_preview(self, event=None):
        if self.preview_timer is not None:
            self.after_cancel(self.preview_timer)
        # Espera 350ms após parar de digitar para atualizar (Suaviza MUITO a experiência)
        self.preview_timer = self.after(350, self.update_preview)

    def adicionar_alca_redimensionamento(self, parent_frame, textbox):
        handle = ctk.CTkFrame(parent_frame, height=8, fg_color="#4e5058", corner_radius=4, cursor="sb_v_double_arrow")
        handle.pack(fill="x", padx=20, pady=(0, 10))

        def start_resize(event):
            handle.startY = event.y_root
            handle.startH = textbox.cget("height")

        def do_resize(event):
            delta = event.y_root - handle.startY
            new_h = max(40, handle.startH + delta)
            textbox.configure(height=new_h)

        handle.bind("<ButtonPress-1>", start_resize)
        handle.bind("<B1-Motion>", do_resize)

    def setup_ui(self):
        self.grid_columnconfigure(1, weight=4)
        self.grid_columnconfigure(2, weight=5)
        self.grid_rowconfigure(0, weight=1)

        self.setup_painel_esquerdo()
        self.setup_painel_editor()
        self.setup_painel_preview()

    def colar_imagem(self, event, entry_widget):
        try:
            clip = ImageGrab.grabclipboard()
            if clip:
                if isinstance(clip, list) and len(clip) > 0:
                    filepath = clip[0]
                    filename = os.path.basename(filepath)
                    if filepath not in self.arquivos_anexados:
                        self.arquivos_anexados.append(filepath)
                        self.atualizar_ui_anexos()
                    entry_widget.delete(0, "end")
                    entry_widget.insert(0, f"attachment://{filename}")
                    self.agendar_update_preview()
                    return "break"
                elif isinstance(clip, Image.Image):
                    filename = f"pasted_{int(time.time())}.png"
                    filepath = os.path.abspath(filename)
                    clip.save(filepath, "PNG")
                    if filepath not in self.arquivos_anexados:
                        self.arquivos_anexados.append(filepath)
                        self.atualizar_ui_anexos()
                    entry_widget.delete(0, "end")
                    entry_widget.insert(0, f"attachment://{filename}")
                    self.agendar_update_preview()
                    return "break"
        except Exception as e:
            print(f"Erro ao capturar clipboard: {e}")

    # ==========================================
    # PAINEL 1: ESQUERDA (Webhooks e Histórico)
    # ==========================================
    def setup_painel_esquerdo(self):
        self.frame_esq = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color="#1e1f22")
        self.frame_esq.grid(row=0, column=0, sticky="nsew")
        self.frame_esq.grid_rowconfigure(5, weight=1)

        ctk.CTkLabel(self.frame_esq, text="Webhooks", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#f2f3f5").grid(row=0, column=0, padx=15, pady=(15, 5), sticky="w")

        self.entry_nome_perfil = ctk.CTkEntry(self.frame_esq, placeholder_text="Nome p/ salvar", height=30,
                                              fg_color="#2b2d31", border_width=0)
        self.entry_nome_perfil.grid(row=1, column=0, padx=15, pady=(0, 5), sticky="ew")

        self.entry_url = ctk.CTkEntry(self.frame_esq, placeholder_text="URL do Webhook", height=30, fg_color="#2b2d31",
                                      border_width=0)
        self.entry_url.grid(row=2, column=0, padx=15, pady=(0, 5), sticky="ew")
        self.entry_url.bind("<FocusOut>", self.fetch_webhook_defaults)

        btn_row = ctk.CTkFrame(self.frame_esq, fg_color="transparent")
        btn_row.grid(row=3, column=0, padx=15, pady=(0, 10), sticky="ew")
        ctk.CTkButton(btn_row, text="Limpar", width=60, height=28, fg_color="#4e5058", hover_color="#6d6f78",
                      command=self.limpar_editor).pack(side="left", padx=(0, 5))
        ctk.CTkButton(btn_row, text="Salvar", width=60, height=28, fg_color="#5865F2", hover_color="#4752C4",
                      command=self.salvar_perfil).pack(side="left", expand=True, fill="x")

        self.scroll_perfis = ctk.CTkScrollableFrame(self.frame_esq, fg_color="transparent", height=150)
        self.scroll_perfis.grid(row=4, column=0, sticky="nsew", padx=5, pady=0)

        ctk.CTkLabel(self.frame_esq, text="Recuperar / Editar", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#f2f3f5").grid(row=6, column=0, padx=15, pady=(20, 5), sticky="w")

        frame_import = ctk.CTkFrame(self.frame_esq, fg_color="transparent")
        frame_import.grid(row=7, column=0, padx=15, pady=0, sticky="ew")
        self.entry_import_id = ctk.CTkEntry(frame_import, placeholder_text="ID da Mensagem", height=30,
                                            fg_color="#2b2d31", border_width=0)
        self.entry_import_id.pack(side="left", fill="x", expand=True, padx=(0, 5))
        ctk.CTkButton(frame_import, text="Puxar", width=50, height=30, fg_color="#4e5058", hover_color="#6d6f78",
                      command=self.importar_msg_antiga).pack(side="left")

        ctk.CTkLabel(self.frame_esq, text="Histórico / Rascunhos", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#b5bac1").grid(row=8, column=0, padx=15, pady=(10, 0), sticky="w")
        self.scroll_historico = ctk.CTkScrollableFrame(self.frame_esq, fg_color="transparent")
        self.scroll_historico.grid(row=9, column=0, sticky="nsew", padx=5, pady=(0, 10))

    # ==========================================
    # PAINEL 2: CENTRO (Editor Dinâmico)
    # ==========================================
    def setup_painel_editor(self):
        self.frame_editor = ctk.CTkScrollableFrame(self, fg_color="#313338")
        self.frame_editor.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)

        top_bar = ctk.CTkFrame(self.frame_editor, fg_color="transparent")
        top_bar.pack(fill="x", padx=20, pady=(20, 10))

        self.btn_enviar = ctk.CTkButton(top_bar, text="Enviar", width=100, height=32, fg_color="#5865F2",
                                        hover_color="#4752C4", font=ctk.CTkFont(weight="bold"),
                                        command=self.enviar_mensagem)
        self.btn_enviar.pack(side="right")

        self.btn_rascunho = ctk.CTkButton(top_bar, text="Salvar Rascunho", width=120, height=32, fg_color="#ca8a04",
                                          hover_color="#a16207", font=ctk.CTkFont(weight="bold"),
                                          command=self.salvar_como_rascunho)
        self.btn_rascunho.pack(side="right", padx=10)

        self.btn_editar = ctk.CTkButton(top_bar, text="Salvar Edição", width=110, height=32, fg_color="#4e5058",
                                        text_color="#ffffff", hover_color="#6d6f78", font=ctk.CTkFont(weight="bold"),
                                        state="disabled", command=self.editar_mensagem)
        self.btn_editar.pack(side="right")

        ctk.CTkLabel(self.frame_editor, text="Content", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#dbdee1").pack(anchor="w", padx=20)
        self.text_content = ctk.CTkTextbox(self.frame_editor, height=120, fg_color="#2b2d31", border_color="#1e1f22",
                                           border_width=1, text_color="#dbdee1")
        self.text_content.pack(fill="x", padx=20, pady=(0, 0))
        self.text_content.bind("<KeyRelease>", self.agendar_update_preview)

        self.adicionar_alca_redimensionamento(self.frame_editor, self.text_content)

        self.btn_profile_toggle = ctk.CTkButton(self.frame_editor, text="> Profile", fg_color="transparent",
                                                text_color="#dbdee1", hover_color="#2b2d31", anchor="w",
                                                command=self.toggle_profile)
        self.btn_profile_toggle.pack(fill="x", padx=20)
        self.frame_profile = ctk.CTkFrame(self.frame_editor, fg_color="#2b2d31", corner_radius=5)

        ctk.CTkLabel(self.frame_profile, text="Username", text_color="#b5bac1", font=ctk.CTkFont(size=11)).pack(
            anchor="w", padx=10, pady=(5, 0))
        self.entry_username = ctk.CTkEntry(self.frame_profile, fg_color="#1e1f22", border_width=0, text_color="#dbdee1")
        self.entry_username.pack(fill="x", padx=10, pady=(0, 5))
        self.entry_username.bind("<KeyRelease>", self.agendar_update_preview)

        ctk.CTkLabel(self.frame_profile, text="Avatar URL (Suporta Ctrl+V Imagem)", text_color="#b5bac1",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=10)
        self.entry_avatar = ctk.CTkEntry(self.frame_profile, fg_color="#1e1f22", border_width=0, text_color="#dbdee1")
        self.entry_avatar.pack(fill="x", padx=10, pady=(0, 10))
        self.entry_avatar.bind("<FocusOut>", self.agendar_update_preview)
        self.entry_avatar.bind("<Control-v>", lambda e: self.colar_imagem(e, self.entry_avatar))

        self.frame_anexos_container = ctk.CTkFrame(self.frame_editor, fg_color="transparent")
        self.frame_anexos_container.pack(fill="x", padx=20, pady=(15, 0))

        self.btn_anexar = ctk.CTkButton(self.frame_anexos_container, text="📎 Anexar Arquivos", fg_color="#4e5058",
                                        hover_color="#6d6f78", command=self.selecionar_anexos)
        self.btn_anexar.pack(anchor="w")

        self.lista_anexos_ui = ctk.CTkFrame(self.frame_anexos_container, fg_color="transparent")
        self.lista_anexos_ui.pack(fill="x", pady=(5, 0))

        self.embeds_container = ctk.CTkFrame(self.frame_editor, fg_color="transparent")
        self.embeds_container.pack(fill="x", pady=5)

        self.btn_add_embed = ctk.CTkButton(self.frame_editor, text="+ Adicionar Embed", fg_color="#5865F2",
                                           hover_color="#4752C4", command=self.add_embed_ui)
        self.btn_add_embed.pack(anchor="w", padx=20, pady=(10, 30))

    def selecionar_anexos(self):
        arquivos = filedialog.askopenfilenames(title="Selecione os arquivos", filetypes=[("Todos os arquivos", "*.*")])
        if arquivos:
            for arq in arquivos:
                if arq not in self.arquivos_anexados and len(self.arquivos_anexados) < 10:
                    self.arquivos_anexados.append(arq)
            if len(self.arquivos_anexados) >= 10:
                self.mostrar_notificacao("Máximo de 10 arquivos atingido.", "aviso")
            self.atualizar_ui_anexos()
            self.agendar_update_preview()

    def remover_anexo(self, caminho):
        if caminho in self.arquivos_anexados:
            self.arquivos_anexados.remove(caminho)
            self.atualizar_ui_anexos()
            self.agendar_update_preview()

    def atualizar_ui_anexos(self):
        for widget in self.lista_anexos_ui.winfo_children():
            widget.destroy()

        for caminho in self.arquivos_anexados:
            nome_arquivo = os.path.basename(caminho)
            row = ctk.CTkFrame(self.lista_anexos_ui, fg_color="#2b2d31", corner_radius=4)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=f"📄 {nome_arquivo}", text_color="#dbdee1", font=ctk.CTkFont(size=12)).pack(
                side="left", padx=10, pady=5)
            btn_del = ctk.CTkButton(row, text="X", width=25, height=25, fg_color="#ed4245", hover_color="#c9383b",
                                    command=lambda c=caminho: self.remover_anexo(c))
            btn_del.pack(side="right", padx=5)

    def toggle_profile(self):
        if self.frame_profile.winfo_ismapped():
            self.frame_profile.pack_forget()
            self.btn_profile_toggle.configure(text="> Profile")
        else:
            self.frame_profile.pack(fill="x", padx=20, pady=(0, 10), after=self.btn_profile_toggle)
            self.btn_profile_toggle.configure(text="v Profile")

    def add_embed_ui(self, embed_data=None):
        ativos = [e for e in self.embed_uis if e["active"]]
        if len(ativos) >= 10:
            return self.mostrar_notificacao("O Discord permite no máximo 10 embeds.", "aviso")

        idx = len(self.embed_uis) + 1

        btn_toggle = ctk.CTkButton(self.embeds_container, text=f"v Embed {idx}", fg_color="transparent",
                                   text_color="#dbdee1", hover_color="#2b2d31", anchor="w")
        btn_toggle.pack(fill="x", padx=20, pady=(5, 0))

        frame_embed = ctk.CTkFrame(self.embeds_container, fg_color="#2b2d31", corner_radius=5)
        frame_embed.pack(fill="x", padx=20, pady=(0, 10))

        def toggle_func(f=frame_embed, b=btn_toggle, i=idx):
            if f.winfo_ismapped():
                f.pack_forget()
                b.configure(text=f"> Embed {i}")
            else:
                f.pack(fill="x", padx=20, pady=(0, 10), after=b)
                b.configure(text=f"v Embed {i}")

        btn_toggle.configure(command=toggle_func)

        row1 = ctk.CTkFrame(frame_embed, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=(10, 0))

        col_color = ctk.CTkFrame(row1, fg_color="transparent")
        col_color.pack(side="left", fill="x", expand=True, padx=(0, 5))
        ctk.CTkLabel(col_color, text="Color (Hex)", text_color="#b5bac1", font=ctk.CTkFont(size=11)).pack(anchor="w")

        color_input_frame = ctk.CTkFrame(col_color, fg_color="transparent")
        color_input_frame.pack(fill="x")

        entry_color = ctk.CTkEntry(color_input_frame, fg_color="#1e1f22", border_width=0, placeholder_text="#5865F2")
        entry_color.pack(side="left", fill="x", expand=True, padx=(0, 5))

        btn_color_picker = ctk.CTkButton(color_input_frame, text="🎨", width=30, fg_color="#5865F2",
                                         hover_color="#4752C4")
        btn_color_picker.pack(side="right")

        def abrir_paleta(entry=entry_color, btn=btn_color_picker):
            cor_atual = entry.get() or "#5865F2"
            if not cor_atual.startswith("#") or len(cor_atual) != 7:
                cor_atual = "#5865F2"
            paleta = AskColor(title="Selecione a Cor", initial_color=cor_atual)
            cor_selecionada = paleta.get()
            if cor_selecionada:
                entry.delete(0, "end")
                entry.insert(0, cor_selecionada)
                btn.configure(fg_color=cor_selecionada, hover_color=cor_selecionada)
                self.agendar_update_preview()

        btn_color_picker.configure(command=abrir_paleta)
        entry_color.bind("<KeyRelease>", self.agendar_update_preview)

        col_author = ctk.CTkFrame(row1, fg_color="transparent")
        col_author.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(col_author, text="Author Name", text_color="#b5bac1", font=ctk.CTkFont(size=11)).pack(anchor="w")
        entry_author = ctk.CTkEntry(col_author, fg_color="#1e1f22", border_width=0)
        entry_author.pack(fill="x")
        entry_author.bind("<KeyRelease>", self.agendar_update_preview)

        ctk.CTkLabel(frame_embed, text="Title", text_color="#b5bac1", font=ctk.CTkFont(size=11)).pack(anchor="w",
                                                                                                      padx=10,
                                                                                                      pady=(5, 0))
        entry_title = ctk.CTkEntry(frame_embed, fg_color="#1e1f22", border_width=0)
        entry_title.pack(fill="x", padx=10)
        entry_title.bind("<KeyRelease>", self.agendar_update_preview)

        ctk.CTkLabel(frame_embed, text="Description", text_color="#b5bac1", font=ctk.CTkFont(size=11)).pack(anchor="w",
                                                                                                            padx=10,
                                                                                                            pady=(5, 0))
        text_desc = ctk.CTkTextbox(frame_embed, height=80, fg_color="#1e1f22", border_width=0)
        text_desc.pack(fill="x", padx=10)
        text_desc.bind("<KeyRelease>", self.agendar_update_preview)

        self.adicionar_alca_redimensionamento(frame_embed, text_desc)

        # === SISTEMA DE FIELDS ===
        lbl_fields_title = ctk.CTkLabel(frame_embed, text="Fields (Campos)", text_color="#b5bac1",
                                        font=ctk.CTkFont(size=12, weight="bold"))
        lbl_fields_title.pack(anchor="w", padx=10, pady=(10, 0))

        container_fields = ctk.CTkFrame(frame_embed, fg_color="transparent")
        container_fields.pack(fill="x", padx=10, pady=(0, 5))

        lista_fields_obj = []

        def adicionar_field_ui(f_data=None):
            f_ativos = [f for f in lista_fields_obj if f["active"]]
            if len(f_ativos) >= 25:
                return self.mostrar_notificacao("Máximo de 25 fields por Embed.", "aviso")

            f_frame = ctk.CTkFrame(container_fields, fg_color="#1e1f22", corner_radius=5)
            f_frame.pack(fill="x", pady=5)

            row_f1 = ctk.CTkFrame(f_frame, fg_color="transparent")
            row_f1.pack(fill="x", padx=5, pady=(5, 2))

            entry_fname = ctk.CTkEntry(row_f1, placeholder_text="Nome do Field", border_width=0, fg_color="#2b2d31",
                                       height=28)
            entry_fname.pack(side="left", fill="x", expand=True, padx=(0, 5))
            entry_fname.bind("<KeyRelease>", self.agendar_update_preview)

            chk_inline = ctk.CTkCheckBox(row_f1, text="Inline", checkbox_width=20, checkbox_height=20,
                                         font=ctk.CTkFont(size=11), width=60)
            chk_inline.pack(side="left", padx=(0, 5))
            chk_inline.configure(command=self.agendar_update_preview)

            def remover_este_field(f=f_frame, obj_list=lista_fields_obj):
                f.destroy()
                for item in obj_list:
                    if item["frame"] == f:
                        item["active"] = False
                self.agendar_update_preview()

            btn_del_field = ctk.CTkButton(row_f1, text="X", width=28, height=28, fg_color="#ed4245",
                                          hover_color="#c9383b", command=remover_este_field)
            btn_del_field.pack(side="right")

            entry_fval = ctk.CTkTextbox(f_frame, border_width=0, fg_color="#2b2d31", height=60)
            entry_fval.pack(fill="x", padx=5, pady=(0, 0))
            entry_fval.bind("<KeyRelease>", self.agendar_update_preview)

            self.adicionar_alca_redimensionamento(f_frame, entry_fval)

            f_obj = {"active": True, "frame": f_frame, "name": entry_fname, "value": entry_fval, "inline": chk_inline}
            lista_fields_obj.append(f_obj)

            if f_data:
                if f_data.get("name"): entry_fname.insert(0, f_data["name"])
                if f_data.get("value"): entry_fval.insert("1.0", f_data["value"])
                if f_data.get("inline"): chk_inline.select()

            self.agendar_update_preview()

        btn_add_field = ctk.CTkButton(frame_embed, text="+ Adicionar Field", fg_color="#00a8fc", hover_color="#0080c0",
                                      height=24, width=120, command=adicionar_field_ui)
        btn_add_field.pack(anchor="w", padx=10, pady=(0, 10))

        row2 = ctk.CTkFrame(frame_embed, fg_color="transparent")
        row2.pack(fill="x", padx=10, pady=(5, 0))
        col_img = ctk.CTkFrame(row2, fg_color="transparent")
        col_img.pack(side="left", fill="x", expand=True, padx=(0, 5))
        ctk.CTkLabel(col_img, text="Image URL (Ctrl+V)", text_color="#b5bac1", font=ctk.CTkFont(size=11)).pack(
            anchor="w")
        entry_image = ctk.CTkEntry(col_img, fg_color="#1e1f22", border_width=0)
        entry_image.pack(fill="x")
        entry_image.bind("<KeyRelease>", self.agendar_update_preview)
        entry_image.bind("<Control-v>", lambda e: self.colar_imagem(e, entry_image))

        col_thm = ctk.CTkFrame(row2, fg_color="transparent")
        col_thm.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(col_thm, text="Thumbnail URL (Ctrl+V)", text_color="#b5bac1", font=ctk.CTkFont(size=11)).pack(
            anchor="w")
        entry_thumb = ctk.CTkEntry(col_thm, fg_color="#1e1f22", border_width=0)
        entry_thumb.pack(fill="x")
        entry_thumb.bind("<KeyRelease>", self.agendar_update_preview)
        entry_thumb.bind("<Control-v>", lambda e: self.colar_imagem(e, entry_thumb))

        ctk.CTkLabel(frame_embed, text="Footer Text", text_color="#b5bac1", font=ctk.CTkFont(size=11)).pack(anchor="w",
                                                                                                            padx=10,
                                                                                                            pady=(5, 0))
        entry_footer = ctk.CTkEntry(frame_embed, fg_color="#1e1f22", border_width=0)
        entry_footer.pack(fill="x", padx=10, pady=(0, 5))
        entry_footer.bind("<KeyRelease>", self.agendar_update_preview)

        row_ts = ctk.CTkFrame(frame_embed, fg_color="transparent")
        row_ts.pack(fill="x", padx=10, pady=(5, 10))

        col_ts_input = ctk.CTkFrame(row_ts, fg_color="transparent")
        col_ts_input.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(col_ts_input, text="Timestamp (YYYY-MM-DD HH:MM:SS)", text_color="#b5bac1",
                     font=ctk.CTkFont(size=11)).pack(anchor="w")

        input_ts_wrapper = ctk.CTkFrame(col_ts_input, fg_color="transparent")
        input_ts_wrapper.pack(fill="x")

        entry_timestamp = ctk.CTkEntry(input_ts_wrapper, fg_color="#1e1f22", border_width=0,
                                       placeholder_text="Ex: 2026-04-09 20:00:00")
        entry_timestamp.pack(side="left", fill="x", expand=True, padx=(0, 5))

        def set_current_timestamp(entry=entry_timestamp):
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            entry.delete(0, "end")
            entry.insert(0, agora)
            self.agendar_update_preview()

        btn_ts_now = ctk.CTkButton(input_ts_wrapper, text="Atual", width=60, fg_color="#4e5058", hover_color="#6d6f78",
                                   command=set_current_timestamp)
        btn_ts_now.pack(side="right")
        entry_timestamp.bind("<KeyRelease>", self.agendar_update_preview)

        btn_remover = ctk.CTkButton(frame_embed, text="Remover Embed", fg_color="#ed4245", hover_color="#c9383b",
                                    height=24, width=120)
        btn_remover.pack(anchor="e", padx=10, pady=(0, 10))

        embed_obj = {
            "active": True, "frame": frame_embed, "btn_toggle": btn_toggle,
            "color": entry_color, "author": entry_author, "title": entry_title,
            "desc": text_desc, "image": entry_image, "thumb": entry_thumb, "footer": entry_footer,
            "timestamp": entry_timestamp, "fields": lista_fields_obj
        }

        def remover_embed(obj=embed_obj):
            obj["frame"].destroy()
            obj["btn_toggle"].destroy()
            obj["active"] = False
            self.agendar_update_preview()

        btn_remover.configure(command=remover_embed)
        self.embed_uis.append(embed_obj)

        if embed_data:
            if embed_data.get("title"): entry_title.insert(0, embed_data["title"])
            if embed_data.get("description"): text_desc.insert("1.0", embed_data["description"])
            if embed_data.get("color"):
                cor_hex = f"#{embed_data['color']:06x}"
                entry_color.insert(0, cor_hex)
                btn_color_picker.configure(fg_color=cor_hex, hover_color=cor_hex)
            if embed_data.get("author"): entry_author.insert(0, embed_data["author"].get("name", ""))
            if embed_data.get("footer"): entry_footer.insert(0, embed_data["footer"].get("text", ""))
            if embed_data.get("image"): entry_image.insert(0, embed_data["image"].get("url", ""))
            if embed_data.get("thumbnail"): entry_thumb.insert(0, embed_data["thumbnail"].get("url", ""))
            if embed_data.get("timestamp"):
                try:
                    dt = datetime.fromisoformat(embed_data["timestamp"].replace("Z", "+00:00"))
                    entry_timestamp.insert(0, dt.strftime("%Y-%m-%d %H:%M:%S"))
                except:
                    entry_timestamp.insert(0, embed_data["timestamp"])
            if embed_data.get("fields"):
                for f_data in embed_data["fields"]: adicionar_field_ui(f_data)

        self.agendar_update_preview()

    # ==========================================
    # DOWNLOAD ASSÍNCRONO E PREVIEW (Sem Travar)
    # ==========================================
    def get_cached_image(self, url, max_size=(400, 300), circular=False):
        if not url: return None

        # Arquivo colado/local
        if url.startswith("attachment://"):
            filename = url.replace("attachment://", "")
            local_path = next((p for p in self.arquivos_anexados if os.path.basename(p) == filename), None)
            if local_path and os.path.exists(local_path):
                return self._process_image(local_path, max_size, circular)

        # Imagem Web com Cache/Thread
        cache_key = f"{url}_{circular}"
        if cache_key in self.image_cache:
            return self.image_cache[cache_key]

        if cache_key not in self.fetching_images:
            self.fetching_images.add(cache_key)

            def download_task():
                try:
                    res = requests.get(url, timeout=3)
                    if res.status_code == 200:
                        img_data = io.BytesIO(res.content)
                        ctk_img = self._process_image(img_data, max_size, circular)
                        if ctk_img:
                            self.image_cache[cache_key] = ctk_img
                            self.after(0, self.update_preview)  # Avisa a interface pra atualizar quando a imagem chegar
                except:
                    pass
                finally:
                    self.fetching_images.discard(cache_key)

            threading.Thread(target=download_task, daemon=True).start()

        return None

    def _process_image(self, source, max_size, circular):
        try:
            img = Image.open(source).convert("RGBA")
            if circular:
                mask = Image.new('L', img.size, 0)
                draw = ImageDraw.Draw(mask)
                draw.ellipse((0, 0) + img.size, fill=255)
                circular_img = Image.new('RGBA', img.size, (0, 0, 0, 0))
                circular_img.paste(img, (0, 0), mask=mask)
                circular_img = circular_img.resize((40, 40), Image.Resampling.LANCZOS)
                return ctk.CTkImage(light_image=circular_img, dark_image=circular_img, size=(40, 40))
            else:
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                return ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
        except:
            return None

    def inserir_texto_markdown(self, textbox_widget, texto):
        partes = texto.split("```")
        for i, parte in enumerate(partes):
            if i % 2 == 1:
                linhas = parte.split('\n', 1)
                codigo = linhas[1] if len(linhas) > 1 and not linhas[0].isspace() and ' ' not in linhas[0] else parte
                textbox_widget.insert("end", "\n" + codigo.strip('\n') + "\n", "codeblock")
            else:
                subpartes = re.split(r'(<@!?\d+>|<@&\d+>|<#\d+>|@everyone|@here)', parte)
                for sub in subpartes:
                    if re.match(r'(<@!?\d+>|<@&\d+>|<#\d+>|@everyone|@here)', sub):
                        if sub == "@everyone" or sub == "@here":
                            nome = sub
                        elif sub.startswith("<@&"):
                            nome = "@Role"
                        elif sub.startswith("<#"):
                            nome = "#channel"
                        else:
                            nome = "@User"
                        textbox_widget.insert("end", f" {nome} ", "mention")
                    else:
                        textbox_widget.insert("end", sub)

    def setup_painel_preview(self):
        self.frame_preview_container = ctk.CTkFrame(self, fg_color="#313338", corner_radius=0, border_color="#1e1f22",
                                                    border_width=1)
        self.frame_preview_container.grid(row=0, column=2, sticky="nsew")

        header = ctk.CTkFrame(self.frame_preview_container, fg_color="#313338", height=48, corner_radius=0,
                              border_color="#1e1f22", border_width=1)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(header, text="# channel-preview", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#f2f3f5").pack(side="left", padx=15, pady=12)

        self.frame_preview = ctk.CTkScrollableFrame(self.frame_preview_container, fg_color="transparent")
        self.frame_preview.pack(fill="both", expand=True, padx=0, pady=0)

    def fetch_webhook_defaults(self, event=None):
        url = self.entry_url.get().strip()
        if not url: return
        try:
            res = requests.get(url, timeout=3)
            if res.status_code == 200:
                data = res.json()
                self.webhook_default_name = data.get("name", "WebHooksPY")
                avatar_hash = data.get("avatar")
                if avatar_hash:
                    self.webhook_default_avatar = f"https://cdn.discordapp.com/avatars/{data['id']}/{avatar_hash}.png"
                else:
                    self.webhook_default_avatar = ""
                self.agendar_update_preview()
        except:
            pass

    def update_preview(self):
        # A Mágica do Double Buffering (Fim do Flicker!)
        new_inner = ctk.CTkFrame(self.frame_preview, fg_color="transparent")

        username = self.entry_username.get().strip() or self.webhook_default_name or "WebHooksPY"
        avatar_url = self.entry_avatar.get().strip() or self.webhook_default_avatar
        content = self.text_content.get("1.0", "end").strip()

        msg_frame = ctk.CTkFrame(new_inner, fg_color="transparent")
        msg_frame.pack(fill="x", padx=15, pady=15)

        avatar_col = ctk.CTkFrame(msg_frame, width=50, fg_color="transparent")
        avatar_col.pack(side="left", fill="y")

        avatar_img = self.get_cached_image(avatar_url, circular=True)
        if avatar_img:
            ctk.CTkLabel(avatar_col, image=avatar_img, text="").pack(anchor="n")
        else:
            ctk.CTkLabel(avatar_col, text="🤖", font=("Arial", 25)).pack(anchor="n")

        content_col = ctk.CTkFrame(msg_frame, fg_color="transparent")
        content_col.pack(side="left", fill="both", expand=True, padx=(10, 0))

        header_row = ctk.CTkFrame(content_col, fg_color="transparent")
        header_row.pack(fill="x")
        ctk.CTkLabel(header_row, text=username, font=ctk.CTkFont(size=14, weight="bold"), text_color="#f2f3f5").pack(
            side="left")

        badge = ctk.CTkFrame(header_row, fg_color="#5865F2", corner_radius=3, height=15)
        badge.pack(side="left", padx=5, pady=3)
        ctk.CTkLabel(badge, text="APP", font=ctk.CTkFont(size=10, weight="bold"), text_color="white", width=30).pack(
            padx=2, pady=0)

        hora_agora = datetime.now().strftime("Hoje às %H:%M")
        ctk.CTkLabel(header_row, text=hora_agora, font=ctk.CTkFont(size=11), text_color="#949ba4").pack(side="left")

        if content:
            estimativa = content.count('\n') + (len(content) // 50) + 1
            txt_prev = ctk.CTkTextbox(content_col, fg_color="transparent", text_color="#dbdee1", wrap="word",
                                      height=estimativa * 22)
            txt_prev.pack(fill="x", pady=(2, 5))
            txt_prev._textbox.tag_configure("mention", background="#3c4270", foreground="#c9cdfb",
                                            font=ctk.CTkFont(weight="bold"))
            txt_prev._textbox.tag_configure("codeblock", background="#1e1f22", font=("Consolas", 12), spacing1=5,
                                            spacing3=5)
            self.inserir_texto_markdown(txt_prev, content)
            txt_prev.configure(state="disabled")

        for embed_data in self.embed_uis:
            if not embed_data["active"]: continue

            e_auth = embed_data["author"].get()
            e_title = embed_data["title"].get()
            e_desc = embed_data["desc"].get("1.0", "end").strip()
            e_color = embed_data["color"].get() or "#202225"
            e_foot = embed_data["footer"].get()
            e_img_url = embed_data["image"].get()
            e_ts = embed_data["timestamp"].get()
            e_fields = [f for f in embed_data.get("fields", []) if f["active"]]

            if any([e_auth, e_title, e_desc, e_foot, e_img_url, e_ts]) or len(e_fields) > 0:
                embed_bg = ctk.CTkFrame(content_col, fg_color="#2b2d31", border_width=0, corner_radius=4)
                embed_bg.pack(anchor="w", fill="x", pady=5)

                try:
                    if e_color.startswith("#") and len(e_color) == 7:
                        ctk.CTkFrame(embed_bg, width=4, fg_color=e_color, corner_radius=4).pack(side="left", fill="y")
                except:
                    pass

                embed_inner = ctk.CTkFrame(embed_bg, fg_color="transparent")
                embed_inner.pack(side="left", fill="both", expand=True, padx=12, pady=10)

                if e_auth: ctk.CTkLabel(embed_inner, text=e_auth, text_color="white",
                                        font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w")
                if e_title: ctk.CTkLabel(embed_inner, text=e_title, text_color="#00a8fc",
                                         font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(2, 0))

                if e_desc:
                    est = e_desc.count('\n') + (len(e_desc) // 50) + 1
                    txt_desc_prev = ctk.CTkTextbox(embed_inner, fg_color="transparent", text_color="#dbdee1",
                                                   wrap="word", height=est * 22)
                    txt_desc_prev.pack(fill="x", pady=(2, 0))
                    txt_desc_prev._textbox.tag_configure("mention", background="#3c4270", foreground="#c9cdfb",
                                                         font=ctk.CTkFont(weight="bold"))
                    txt_desc_prev._textbox.tag_configure("codeblock", background="#1e1f22", font=("Consolas", 12))
                    self.inserir_texto_markdown(txt_desc_prev, e_desc)
                    txt_desc_prev.configure(state="disabled")

                # GRADES DE FIELDS DO DISCORD
                if e_fields:
                    f_container = ctk.CTkFrame(embed_inner, fg_color="transparent")
                    f_container.pack(fill="x", pady=(10, 0))
                    cur_row = None
                    i_count = 0

                    for f in e_fields:
                        fname = f["name"].get().strip() or "\u200b"
                        fval = f["value"].get("1.0", "end").strip() or "\u200b"
                        finline = f["inline"].get() == 1

                        if finline:
                            if cur_row is None or i_count >= 3:
                                cur_row = ctk.CTkFrame(f_container, fg_color="transparent")
                                cur_row.pack(fill="x", pady=(0, 8))
                                i_count = 0

                            f_box = ctk.CTkFrame(cur_row, fg_color="transparent")
                            f_box.pack(side="left", fill="x", expand=True, padx=(0, 10))
                            ctk.CTkLabel(f_box, text=fname, font=ctk.CTkFont(size=12, weight="bold"),
                                         text_color="#dbdee1", justify="left", wraplength=130).pack(anchor="w")

                            est_v = fval.count('\n') + (len(fval) // 18) + 1
                            txt_v = ctk.CTkTextbox(f_box, fg_color="transparent", text_color="#dbdee1", wrap="word",
                                                   height=est_v * 22, width=130)
                            txt_v.pack(fill="x", pady=(0, 0))
                            txt_v._textbox.tag_configure("mention", background="#3c4270", foreground="#c9cdfb",
                                                         font=ctk.CTkFont(weight="bold"))
                            self.inserir_texto_markdown(txt_v, fval)
                            txt_v.configure(state="disabled")
                            i_count += 1
                        else:
                            cur_row = None
                            i_count = 0
                            f_box = ctk.CTkFrame(f_container, fg_color="transparent")
                            f_box.pack(fill="x", pady=(0, 8))
                            ctk.CTkLabel(f_box, text=fname, font=ctk.CTkFont(size=12, weight="bold"),
                                         text_color="#dbdee1", justify="left", wraplength=400).pack(anchor="w")

                            est_v = fval.count('\n') + (len(fval) // 50) + 1
                            txt_v = ctk.CTkTextbox(f_box, fg_color="transparent", text_color="#dbdee1", wrap="word",
                                                   height=est_v * 22)
                            txt_v.pack(fill="x", pady=(0, 0))
                            txt_v._textbox.tag_configure("mention", background="#3c4270", foreground="#c9cdfb",
                                                         font=ctk.CTkFont(weight="bold"))
                            self.inserir_texto_markdown(txt_v, fval)
                            txt_v.configure(state="disabled")

                # IMAGENS REAIS NA EMBED!
                if e_img_url:
                    emb_img = self.get_cached_image(e_img_url, max_size=(400, 300))
                    if emb_img:
                        ctk.CTkLabel(embed_inner, image=emb_img, text="").pack(anchor="w", pady=(10, 0))
                    else:
                        ctk.CTkLabel(embed_inner, text="⏳ Carregando Imagem...", text_color="#b5bac1").pack(anchor="w",
                                                                                                            pady=(
                                                                                                            10, 0))

                footer_str = e_foot
                if e_ts:
                    try:
                        ts_f = datetime.strptime(e_ts, "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M")
                    except:
                        ts_f = e_ts
                    footer_str += f" • {ts_f}" if footer_str else ts_f
                if footer_str: ctk.CTkLabel(embed_inner, text=footer_str, text_color="#949ba4",
                                            font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(10, 0))

        # Exclui os filhos antigos só DEPOIS de desenhar o novo (evita flicker)
        for child in self.frame_preview.winfo_children():
            if child != new_inner: child.destroy()

        new_inner.pack(fill="both", expand=True)

    # ==========================================
    # LÓGICA DE DADOS E API
    # ==========================================
    def montar_payload(self):
        payload = {"embeds": []}
        username = self.entry_username.get().strip()
        avatar = self.entry_avatar.get().strip()
        content = self.text_content.get("1.0", "end").strip()

        if username: payload["username"] = username
        if avatar: payload["avatar_url"] = avatar
        if content: payload["content"] = content

        for embed_data in self.embed_uis:
            if not embed_data["active"]: continue
            embed = {}
            if embed_data["title"].get(): embed["title"] = embed_data["title"].get()
            if embed_data["desc"].get("1.0", "end").strip(): embed["description"] = embed_data["desc"].get("1.0",
                                                                                                           "end").strip()
            if embed_data["author"].get(): embed["author"] = {"name": embed_data["author"].get()}
            if embed_data["footer"].get(): embed["footer"] = {"text": embed_data["footer"].get()}
            if embed_data["image"].get(): embed["image"] = {"url": embed_data["image"].get()}
            if embed_data["thumb"].get(): embed["thumbnail"] = {"url": embed_data["thumb"].get()}

            color_hex = embed_data["color"].get().strip()
            if color_hex:
                try:
                    embed["color"] = int(color_hex.lstrip('#'), 16)
                except:
                    pass

            ts_input = embed_data["timestamp"].get().strip()
            if ts_input:
                try:
                    embed["timestamp"] = datetime.strptime(ts_input, "%Y-%m-%d %H:%M:%S").isoformat()
                except ValueError:
                    embed["timestamp"] = ts_input

            fields_payload = []
            for f_obj in embed_data.get("fields", []):
                if not f_obj["active"]: continue
                fname = f_obj["name"].get().strip()
                fval = f_obj["value"].get("1.0", "end").strip()
                finline = f_obj["inline"].get() == 1
                if fname or fval:
                    fields_payload.append({"name": fname or "\u200b", "value": fval or "\u200b", "inline": finline})
            if fields_payload: embed["fields"] = fields_payload

            if embed: payload["embeds"].append(embed)

        return payload

    def salvar_como_rascunho(self):
        if not self.webhook_atual:
            return self.mostrar_notificacao("Selecione ou salve um Webhook primeiro.", "aviso")

        payload = self.montar_payload()

        if self.mensagem_editando_id and str(self.mensagem_editando_id).startswith("draft_"):
            draft_id = self.mensagem_editando_id
            historico = self.dados["webhooks"][self.webhook_atual].get("history", [])
            self.dados["webhooks"][self.webhook_atual]["history"] = [m for m in historico if m["id"] != draft_id]
        else:
            draft_id = f"draft_{str(uuid.uuid4())[:8]}"

        self.mensagem_editando_id = draft_id
        self.dados["webhooks"][self.webhook_atual]["history"].append({
            "id": draft_id, "status": "rascunho", "content": payload.get("content", "Rascunho..."),
            "full_payload": payload
        })
        self.save_data()
        self.atualizar_lista_historico()
        self.mostrar_notificacao("Rascunho salvo localmente!", "info")

    def enviar_mensagem(self):
        url = self.entry_url.get().strip()
        if not url: return self.mostrar_notificacao("Insira a URL do Webhook.", "erro")

        payload = self.montar_payload()
        arquivos_abertos = []
        arquivos_api = {}

        try:
            if self.arquivos_anexados:
                for i, caminho in enumerate(self.arquivos_anexados):
                    f = open(caminho, 'rb')
                    arquivos_abertos.append(f)
                    arquivos_api[f"file{i}"] = (os.path.basename(caminho), f)

                res = requests.post(url + "?wait=true", data={"payload_json": json.dumps(payload)}, files=arquivos_api)
            else:
                res = requests.post(url + "?wait=true", json=payload)

            if res.status_code in [200, 204]:
                msg_id = res.json().get("id") if res.status_code == 200 else "AnexoEnviado"

                if self.webhook_atual:
                    if self.mensagem_editando_id and str(self.mensagem_editando_id).startswith("draft_"):
                        draft_id = self.mensagem_editando_id
                        hist = self.dados["webhooks"][self.webhook_atual]["history"]
                        self.dados["webhooks"][self.webhook_atual]["history"] = [m for m in hist if m["id"] != draft_id]

                    self.dados["webhooks"][self.webhook_atual]["history"].append({
                        "id": msg_id, "status": "enviado", "content": payload.get("content", "Embed/Anexo...")
                    })
                    self.save_data()
                    self.atualizar_lista_historico()

                self.mostrar_notificacao("Enviado com sucesso!", "sucesso")
                self.mensagem_editando_id = None
                self.btn_editar.configure(state="disabled")
                self.arquivos_anexados = []
                self.atualizar_ui_anexos()
            else:
                self.mostrar_notificacao(f"Erro: {res.status_code} - {res.text[:30]}", "erro")

        except Exception as e:
            self.mostrar_notificacao(f"Erro: {str(e)}", "erro")
        finally:
            for f in arquivos_abertos: f.close()

    def editar_mensagem(self):
        if not self.mensagem_editando_id or str(self.mensagem_editando_id).startswith("draft_"):
            return self.mostrar_notificacao("Ação inválida. Rascunhos devem ser enviados.", "aviso")

        url = self.entry_url.get().strip()
        try:
            res = requests.patch(f"{url}/messages/{self.mensagem_editando_id}", json=self.montar_payload())
            if res.status_code == 200:
                self.mostrar_notificacao("Mensagem editada com sucesso!", "sucesso")
                self.mensagem_editando_id = None
                self.btn_editar.configure(state="disabled")
                self.atualizar_lista_historico()
            else:
                self.mostrar_notificacao("Erro ao editar mensagem.", "erro")
        except Exception as e:
            self.mostrar_notificacao(f"Erro: {str(e)}", "erro")

    def importar_msg_antiga(self):
        url = self.entry_url.get().strip()
        msg_id = self.entry_import_id.get().strip()
        if not url or not msg_id: return self.mostrar_notificacao("Insira a URL e o ID da Mensagem.", "aviso")

        if msg_id.startswith("draft_"):
            historico = self.dados["webhooks"].get(self.webhook_atual, {}).get("history", [])
            draft = next((m for m in historico if m["id"] == msg_id), None)
            if draft and "full_payload" in draft:
                self.preencher_editor_com_dados(draft["full_payload"])
                self.mensagem_editando_id = msg_id
                self.btn_editar.configure(state="disabled")
                self.atualizar_lista_historico()
                return self.mostrar_notificacao("Rascunho carregado!", "sucesso")

        try:
            res = requests.get(f"{url}/messages/{msg_id}")
            if res.status_code == 200:
                data = res.json()
                self.preencher_editor_com_dados(data)
                self.mensagem_editando_id = msg_id
                self.btn_editar.configure(state="normal")
                self.atualizar_lista_historico()
            else:
                self.mostrar_notificacao(f"Mensagem não encontrada (Erro {res.status_code})", "erro")
        except Exception as e:
            self.mostrar_notificacao(f"Erro: {str(e)}", "erro")

    def limpar_embeds(self):
        for e in self.embed_uis:
            if e["active"]:
                e["frame"].destroy()
                e["btn_toggle"].destroy()
                e["active"] = False
        self.embed_uis = []

    def preencher_editor_com_dados(self, data):
        self.text_content.delete("1.0", "end")
        self.entry_username.delete(0, 'end')
        self.entry_avatar.delete(0, 'end')

        self.limpar_embeds()
        self.arquivos_anexados = []
        self.atualizar_ui_anexos()

        if data.get("username"): self.entry_username.insert(0, data["username"])
        if data.get("avatar_url"): self.entry_avatar.insert(0, data["avatar_url"])
        if data.get("content"): self.text_content.insert("1.0", data["content"])

        if data.get("embeds"):
            for e_data in data["embeds"]: self.add_embed_ui(e_data)

        if data.get("username") or data.get("avatar_url"):
            if not self.frame_profile.winfo_ismapped(): self.toggle_profile()

        self.agendar_update_preview()

    def limpar_editor(self):
        self.webhook_atual = None
        self.mensagem_editando_id = None
        self.entry_nome_perfil.delete(0, 'end')
        self.entry_url.delete(0, 'end')
        self.btn_editar.configure(state="disabled")
        self.atualizar_lista_historico()
        self.preencher_editor_com_dados({})
        self.webhook_default_name = "WebHooksPY"
        self.webhook_default_avatar = ""
        self.avatar_url_cache = ""
        self.agendar_update_preview()

    def salvar_perfil(self):
        nome = self.entry_nome_perfil.get().strip()
        url = self.entry_url.get().strip()
        if not nome or not url: return self.mostrar_notificacao("Nome e URL são necessários.", "aviso")

        if nome not in self.dados["webhooks"]:
            self.dados["webhooks"][nome] = {"url": url, "history": []}
        else:
            self.dados["webhooks"][nome]["url"] = url

        self.save_data()
        self.atualizar_lista_webhooks()
        self.webhook_atual = nome
        self.atualizar_lista_historico()
        self.mostrar_notificacao("Perfil salvo com sucesso!", "sucesso")

    def atualizar_lista_webhooks(self):
        for w in self.scroll_perfis.winfo_children(): w.destroy()
        for nome in self.dados["webhooks"].keys():
            ctk.CTkButton(self.scroll_perfis, text=nome, fg_color="#2b2d31", hover_color="#4e5058", height=25,
                          command=lambda n=nome: self.carregar_perfil(n)).pack(fill="x", pady=2)

    def carregar_perfil(self, nome):
        self.limpar_editor()
        self.webhook_atual = nome
        self.entry_nome_perfil.insert(0, nome)
        url = self.dados["webhooks"][nome]["url"]
        self.entry_url.insert(0, url)
        self.fetch_webhook_defaults()
        self.atualizar_lista_historico()

    def atualizar_lista_historico(self):
        for w in self.scroll_historico.winfo_children(): w.destroy()
        if not self.webhook_atual: return

        for msg in reversed(self.dados["webhooks"][self.webhook_atual].get("history", [])):
            status = msg.get("status", "enviado")
            msg_id = msg['id']

            cor_fundo = "#2b2d31"
            cor_hover = "#4e5058"

            if msg_id == self.mensagem_editando_id:
                cor_fundo = "#5865F2"
                cor_hover = "#4752C4"
            elif status == "rascunho":
                cor_fundo = "#ca8a04"
                cor_hover = "#a16207"
            elif status == "enviado":
                cor_fundo = "#217a3f"
                cor_hover = "#166534"

            prefixo = "[R] " if status == "rascunho" else ""
            display_id = msg_id if not str(msg_id).startswith("draft_") else msg_id[:13]

            btn = ctk.CTkButton(self.scroll_historico, text=f"{prefixo}{display_id}\n{msg['content'][:15]}...",
                                fg_color=cor_fundo, hover_color=cor_hover, height=40,
                                command=lambda id=msg_id: self.carregar_msg_historico(id))
            btn.pack(fill="x", pady=2)

    def carregar_msg_historico(self, msg_id):
        self.entry_import_id.delete(0, 'end')
        self.entry_import_id.insert(0, msg_id)
        self.importar_msg_antiga()


if __name__ == "__main__":
    app = WebHooksPY()
    app.mainloop()
