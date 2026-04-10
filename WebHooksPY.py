import customtkinter as ctk
from CTkColorPicker import AskColor
import requests
import json
import os
import re
from PIL import Image, ImageDraw, ImageTk
import io
from datetime import datetime

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

DATA_FILE = "dados_webhooks.json"
DEFAULT_AVATAR_URL = "https://cdn.discordapp.com/embed/avatars/0.png"


def formatar_mencoes(texto):
    """Converte os IDs brutos do Discord em texto legível para o preview"""
    if not texto: return ""
    texto = re.sub(r'<@!?(\d+)>', r'@User', texto)  # Usuários
    texto = re.sub(r'<@&(\d+)>', r'@Role', texto)  # Cargos
    texto = re.sub(r'<#(\d+)>', r'#channel', texto)  # Canais
    return texto


class WebHooksPY(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("WebHooksPY")
        self.geometry("1300x800")

        # --- LÓGICA DO ÍCONE ---
        try:
            if os.path.exists("icon.ico"):
                self.icon_image = ImageTk.PhotoImage(Image.open("icon.ico"))
                self.wm_iconphoto(True, self.icon_image)
        except Exception as e:
            print(f"Aviso: Não foi possível carregar o ícone. Detalhes: {e}")
        # ------------------------

        self.dados = self.load_data()
        self.webhook_atual = None
        self.mensagem_editando_id = None

        self.webhook_default_name = "WebHooksPY"
        self.webhook_default_avatar = ""
        self.avatar_image_cache = None
        self.avatar_url_cache = ""

        self.embed_uis = []

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

    # ==========================================
    # SISTEMA DE NOTIFICAÇÕES (TOASTS)
    # ==========================================
    def mostrar_notificacao(self, mensagem, tipo="sucesso"):
        cores = {
            "sucesso": ("#57F287", "#000000"),
            "erro": ("#ED4245", "#FFFFFF"),
            "aviso": ("#FEE75C", "#000000")
        }
        cor_fundo, cor_texto = cores.get(tipo, ("#5865F2", "#FFFFFF"))

        noti_frame = ctk.CTkFrame(self, fg_color=cor_fundo, corner_radius=8)
        noti_frame.place(relx=0.5, rely=0.05, anchor="center")

        lbl = ctk.CTkLabel(noti_frame, text=mensagem, text_color=cor_texto, font=ctk.CTkFont(size=14, weight="bold"))
        lbl.pack(padx=20, pady=10)

        self.after(3000, noti_frame.destroy)

    def setup_ui(self):
        self.grid_columnconfigure(1, weight=4)
        self.grid_columnconfigure(2, weight=5)
        self.grid_rowconfigure(0, weight=1)

        self.setup_painel_esquerdo()
        self.setup_painel_editor()
        self.setup_painel_preview()

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

        ctk.CTkLabel(self.frame_esq, text="Histórico", font=ctk.CTkFont(size=12, weight="bold"),
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

        self.btn_enviar = ctk.CTkButton(top_bar, text="Enviar Mensagem", height=32, fg_color="#5865F2",
                                        hover_color="#4752C4", font=ctk.CTkFont(weight="bold"),
                                        command=self.enviar_mensagem)
        self.btn_enviar.pack(side="right")

        self.btn_editar = ctk.CTkButton(top_bar, text="Salvar Edição", height=32, fg_color="#4e5058",
                                        text_color="#ffffff", hover_color="#6d6f78", font=ctk.CTkFont(weight="bold"),
                                        state="disabled", command=self.editar_mensagem)
        self.btn_editar.pack(side="right", padx=10)

        ctk.CTkLabel(self.frame_editor, text="Content", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#dbdee1").pack(anchor="w", padx=20)
        self.text_content = ctk.CTkTextbox(self.frame_editor, height=120, fg_color="#2b2d31", border_color="#1e1f22",
                                           border_width=1, text_color="#dbdee1")
        self.text_content.pack(fill="x", padx=20, pady=(0, 15))
        self.text_content.bind("<KeyRelease>", self.update_preview)

        self.btn_profile_toggle = ctk.CTkButton(self.frame_editor, text="> Profile", fg_color="transparent",
                                                text_color="#dbdee1", hover_color="#2b2d31", anchor="w",
                                                command=self.toggle_profile)
        self.btn_profile_toggle.pack(fill="x", padx=20)
        self.frame_profile = ctk.CTkFrame(self.frame_editor, fg_color="#2b2d31", corner_radius=5)

        ctk.CTkLabel(self.frame_profile, text="Username", text_color="#b5bac1", font=ctk.CTkFont(size=11)).pack(
            anchor="w", padx=10, pady=(5, 0))
        self.entry_username = ctk.CTkEntry(self.frame_profile, fg_color="#1e1f22", border_width=0, text_color="#dbdee1")
        self.entry_username.pack(fill="x", padx=10, pady=(0, 5))
        self.entry_username.bind("<KeyRelease>", self.update_preview)

        ctk.CTkLabel(self.frame_profile, text="Avatar URL", text_color="#b5bac1", font=ctk.CTkFont(size=11)).pack(
            anchor="w", padx=10)
        self.entry_avatar = ctk.CTkEntry(self.frame_profile, fg_color="#1e1f22", border_width=0, text_color="#dbdee1")
        self.entry_avatar.pack(fill="x", padx=10, pady=(0, 10))
        self.entry_avatar.bind("<FocusOut>", self.update_preview)

        self.embeds_container = ctk.CTkFrame(self.frame_editor, fg_color="transparent")
        self.embeds_container.pack(fill="x", pady=5)

        self.btn_add_embed = ctk.CTkButton(self.frame_editor, text="+ Adicionar Embed", fg_color="#5865F2",
                                           hover_color="#4752C4", command=self.add_embed_ui)
        self.btn_add_embed.pack(anchor="w", padx=20, pady=(10, 30))

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
            return self.mostrar_notificacao("O Discord permite no máximo 10 embeds por mensagem.", "aviso")

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
                self.update_preview()

        btn_color_picker.configure(command=abrir_paleta)
        entry_color.bind("<KeyRelease>", self.update_preview)

        col_author = ctk.CTkFrame(row1, fg_color="transparent")
        col_author.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(col_author, text="Author Name", text_color="#b5bac1", font=ctk.CTkFont(size=11)).pack(anchor="w")
        entry_author = ctk.CTkEntry(col_author, fg_color="#1e1f22", border_width=0)
        entry_author.pack(fill="x")
        entry_author.bind("<KeyRelease>", self.update_preview)

        ctk.CTkLabel(frame_embed, text="Title", text_color="#b5bac1", font=ctk.CTkFont(size=11)).pack(anchor="w",
                                                                                                      padx=10,
                                                                                                      pady=(5, 0))
        entry_title = ctk.CTkEntry(frame_embed, fg_color="#1e1f22", border_width=0)
        entry_title.pack(fill="x", padx=10)
        entry_title.bind("<KeyRelease>", self.update_preview)

        ctk.CTkLabel(frame_embed, text="Description", text_color="#b5bac1", font=ctk.CTkFont(size=11)).pack(anchor="w",
                                                                                                            padx=10,
                                                                                                            pady=(5, 0))
        text_desc = ctk.CTkTextbox(frame_embed, height=80, fg_color="#1e1f22", border_width=0)
        text_desc.pack(fill="x", padx=10)
        text_desc.bind("<KeyRelease>", self.update_preview)

        row2 = ctk.CTkFrame(frame_embed, fg_color="transparent")
        row2.pack(fill="x", padx=10, pady=(5, 0))
        col_img = ctk.CTkFrame(row2, fg_color="transparent")
        col_img.pack(side="left", fill="x", expand=True, padx=(0, 5))
        ctk.CTkLabel(col_img, text="Image URL", text_color="#b5bac1", font=ctk.CTkFont(size=11)).pack(anchor="w")
        entry_image = ctk.CTkEntry(col_img, fg_color="#1e1f22", border_width=0)
        entry_image.pack(fill="x")
        entry_image.bind("<KeyRelease>", self.update_preview)

        col_thm = ctk.CTkFrame(row2, fg_color="transparent")
        col_thm.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(col_thm, text="Thumbnail URL", text_color="#b5bac1", font=ctk.CTkFont(size=11)).pack(anchor="w")
        entry_thumb = ctk.CTkEntry(col_thm, fg_color="#1e1f22", border_width=0)
        entry_thumb.pack(fill="x")
        entry_thumb.bind("<KeyRelease>", self.update_preview)

        ctk.CTkLabel(frame_embed, text="Footer Text", text_color="#b5bac1", font=ctk.CTkFont(size=11)).pack(anchor="w",
                                                                                                            padx=10,
                                                                                                            pady=(5, 0))
        entry_footer = ctk.CTkEntry(frame_embed, fg_color="#1e1f22", border_width=0)
        entry_footer.pack(fill="x", padx=10, pady=(0, 5))
        entry_footer.bind("<KeyRelease>", self.update_preview)

        # === NOVO SISTEMA DE TIMESTAMP ===
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
            self.update_preview()

        btn_ts_now = ctk.CTkButton(input_ts_wrapper, text="Atual", width=60, fg_color="#4e5058", hover_color="#6d6f78",
                                   command=set_current_timestamp)
        btn_ts_now.pack(side="right")
        entry_timestamp.bind("<KeyRelease>", self.update_preview)
        # ==================================

        btn_remover = ctk.CTkButton(frame_embed, text="Remover Embed", fg_color="#ed4245", hover_color="#c9383b",
                                    height=24, width=120)
        btn_remover.pack(anchor="e", padx=10, pady=(0, 10))

        embed_obj = {
            "active": True, "frame": frame_embed, "btn_toggle": btn_toggle,
            "color": entry_color, "author": entry_author, "title": entry_title,
            "desc": text_desc, "image": entry_image, "thumb": entry_thumb, "footer": entry_footer,
            "timestamp": entry_timestamp
        }

        def remover_embed(obj=embed_obj):
            obj["frame"].destroy()
            obj["btn_toggle"].destroy()
            obj["active"] = False
            self.update_preview()

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

            # Carregar Timestamp do Histórico
            if embed_data.get("timestamp"):
                try:
                    # Converte o padrão ISO da API do Discord para nosso formato legível
                    dt = datetime.fromisoformat(embed_data["timestamp"].replace("Z", "+00:00"))
                    entry_timestamp.insert(0, dt.strftime("%Y-%m-%d %H:%M:%S"))
                except:
                    entry_timestamp.insert(0, embed_data["timestamp"])

        self.update_preview()

    # ==========================================
    # PAINEL 3: DIREITA (Preview)
    # ==========================================
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
                self.update_preview()
        except:
            pass

    def fetch_avatar_image(self, url):
        if url == self.avatar_url_cache and self.avatar_image_cache is not None:
            return self.avatar_image_cache
        try:
            target_url = url if url else DEFAULT_AVATAR_URL
            response = requests.get(target_url, stream=True, timeout=3)
            if response.status_code == 200:
                img_data = response.content
                img = Image.open(io.BytesIO(img_data)).convert("RGBA")
                mask = Image.new('L', img.size, 0)
                draw = ImageDraw.Draw(mask)
                draw.ellipse((0, 0) + img.size, fill=255)
                circular_img = Image.new('RGBA', img.size, (0, 0, 0, 0))
                circular_img.paste(img, (0, 0), mask=mask)
                circular_img = circular_img.resize((40, 40), Image.Resampling.LANCZOS)

                ctk_img = ctk.CTkImage(light_image=circular_img, dark_image=circular_img, size=(40, 40))
                self.avatar_image_cache = ctk_img
                self.avatar_url_cache = url
                return ctk_img
        except:
            pass
        return None

    def update_preview(self, event=None):
        for widget in self.frame_preview.winfo_children():
            widget.destroy()

        username = self.entry_username.get().strip() or self.webhook_default_name or "WebHooksPY"
        avatar_url = self.entry_avatar.get().strip() or self.webhook_default_avatar
        content = self.text_content.get("1.0", "end").strip()

        msg_frame = ctk.CTkFrame(self.frame_preview, fg_color="transparent")
        msg_frame.pack(fill="x", padx=15, pady=15)

        avatar_col = ctk.CTkFrame(msg_frame, width=50, fg_color="transparent")
        avatar_col.pack(side="left", fill="y")

        avatar_img = self.fetch_avatar_image(avatar_url)
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

        # Mostra a hora atual no preview da mensagem principal
        hora_agora = datetime.now().strftime("Hoje às %H:%M")
        ctk.CTkLabel(header_row, text=hora_agora, font=ctk.CTkFont(size=11), text_color="#949ba4").pack(
            side="left")

        content_formatado = formatar_mencoes(content)
        if content_formatado:
            ctk.CTkLabel(content_col, text=content_formatado, font=ctk.CTkFont(size=14), text_color="#dbdee1",
                         justify="left", wraplength=450).pack(anchor="w", pady=(2, 5))

        for embed_data in self.embed_uis:
            if not embed_data["active"]: continue

            e_author = embed_data["author"].get()
            e_title = embed_data["title"].get()
            e_desc = embed_data["desc"].get("1.0", "end").strip()
            e_color = embed_data["color"].get() or "#202225"
            e_footer = embed_data["footer"].get()
            e_image = embed_data["image"].get()
            e_timestamp = embed_data["timestamp"].get()

            # Precisamos checar se tem pelo menos algum dado para desenhar o embed
            if any([e_author, e_title, e_desc, e_footer, e_image, e_timestamp]):
                embed_bg = ctk.CTkFrame(content_col, fg_color="#2b2d31", border_width=0, corner_radius=4)
                embed_bg.pack(anchor="w", fill="x", pady=5)

                try:
                    if e_color.startswith("#") and len(e_color) == 7: ctk.CTkFrame(embed_bg, width=4, fg_color=e_color,
                                                                                   corner_radius=4).pack(side="left",
                                                                                                         fill="y")
                except:
                    pass

                embed_inner = ctk.CTkFrame(embed_bg, fg_color="transparent")
                embed_inner.pack(side="left", fill="both", expand=True, padx=12, pady=10)

                if e_author: ctk.CTkLabel(embed_inner, text=e_author, text_color="white",
                                          font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w")
                if e_title: ctk.CTkLabel(embed_inner, text=e_title, text_color="#00a8fc",
                                         font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(2, 0))

                e_desc_formatada = formatar_mencoes(e_desc)
                if e_desc_formatada: ctk.CTkLabel(embed_inner, text=e_desc_formatada, text_color="#dbdee1",
                                                  font=ctk.CTkFont(size=13), justify="left", wraplength=400).pack(
                    anchor="w", pady=(2, 0))

                if e_image: ctk.CTkLabel(embed_inner, text="", fg_color="#1e1f22", corner_radius=5, height=100,
                                         width=200).pack(anchor="w", pady=(10, 0))

                # Monta a string do footer + timestamp para o preview
                footer_final = e_footer
                if e_timestamp:
                    # Tenta formatar a string de timestamp apenas pegando a parte da data/hora (Ex: 09/04/2026 20:00)
                    try:
                        dt = datetime.strptime(e_timestamp, "%Y-%m-%d %H:%M:%S")
                        ts_str = dt.strftime("%d/%m/%Y %H:%M")
                    except:
                        ts_str = e_timestamp  # Falback se a pessoa digitar algo customizado

                    if footer_final:
                        footer_final += f" • {ts_str}"
                    else:
                        footer_final = ts_str

                if footer_final:
                    ctk.CTkLabel(embed_inner, text=footer_final, text_color="#949ba4",
                                 font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(10, 0))

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

            # --- Tratamento do Timestamp para a API do Discord ---
            ts_input = embed_data["timestamp"].get().strip()
            if ts_input:
                try:
                    # Converte o nosso formato fácil para o ISO 8601 exigido pelo Discord
                    dt = datetime.strptime(ts_input, "%Y-%m-%d %H:%M:%S")
                    embed["timestamp"] = dt.isoformat()
                except ValueError:
                    # Se falhar, tenta mandar como está (vai que a pessoa colou um formato ISO direto)
                    embed["timestamp"] = ts_input

            if embed: payload["embeds"].append(embed)

        return payload

    def enviar_mensagem(self):
        url = self.entry_url.get().strip()
        if not url: return self.mostrar_notificacao("Insira a URL do Webhook.", "erro")
        payload = self.montar_payload()
        try:
            res = requests.post(url + "?wait=true", json=payload)
            if res.status_code in [200, 204]:
                msg_id = res.json().get("id")
                if self.webhook_atual:
                    self.dados["webhooks"][self.webhook_atual]["history"].append(
                        {"id": msg_id, "content": payload.get("content", "Embed...")})
                    self.save_data()
                    self.atualizar_lista_historico()
                self.mostrar_notificacao("Mensagem enviada com sucesso!", "sucesso")
            else:
                self.mostrar_notificacao(f"Erro da API: {res.status_code}", "erro")
        except Exception as e:
            self.mostrar_notificacao(f"Erro: {str(e)}", "erro")

    def editar_mensagem(self):
        if not self.mensagem_editando_id: return
        url = self.entry_url.get().strip()
        payload = self.montar_payload()
        try:
            res = requests.patch(f"{url}/messages/{self.mensagem_editando_id}", json=payload)
            if res.status_code == 200:
                self.mostrar_notificacao("Mensagem editada com sucesso!", "sucesso")
                self.btn_editar.configure(state="disabled")
                self.mensagem_editando_id = None
            else:
                self.mostrar_notificacao("Erro ao editar mensagem.", "erro")
        except Exception as e:
            self.mostrar_notificacao(f"Erro: {str(e)}", "erro")

    def importar_msg_antiga(self):
        url = self.entry_url.get().strip()
        msg_id = self.entry_import_id.get().strip()
        if not url or not msg_id: return self.mostrar_notificacao("Insira a URL e o ID da Mensagem.", "aviso")

        try:
            res = requests.get(f"{url}/messages/{msg_id}")
            if res.status_code == 200:
                data = res.json()
                self.preencher_editor_com_dados(data)
                self.mensagem_editando_id = msg_id
                self.btn_editar.configure(state="normal", text=f"Salvar Edição ({msg_id[-4:]})")
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

        if data.get("username"): self.entry_username.insert(0, data["username"])
        if data.get("avatar_url"): self.entry_avatar.insert(0, data["avatar_url"])
        if data.get("content"): self.text_content.insert("1.0", data["content"])

        if data.get("embeds"):
            for e_data in data["embeds"]:
                self.add_embed_ui(e_data)

        if data.get("username") or data.get("avatar_url"):
            if not self.frame_profile.winfo_ismapped(): self.toggle_profile()

        self.update_preview()

    def limpar_editor(self):
        self.webhook_atual = None
        self.mensagem_editando_id = None
        self.entry_nome_perfil.delete(0, 'end')
        self.entry_url.delete(0, 'end')
        self.btn_editar.configure(state="disabled", text="Salvar Edição")
        self.atualizar_lista_historico()
        self.preencher_editor_com_dados({})
        self.webhook_default_name = "WebHooksPY"
        self.webhook_default_avatar = ""
        self.avatar_url_cache = ""
        self.update_preview()

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
            btn = ctk.CTkButton(self.scroll_historico, text=f"{msg['id']}\n{msg['content'][:15]}...",
                                fg_color="#2b2d31", hover_color="#4e5058", height=40,
                                command=lambda id=msg['id']: self.carregar_msg_historico(id))
            btn.pack(fill="x", pady=2)

    def carregar_msg_historico(self, msg_id):
        self.entry_import_id.delete(0, 'end')
        self.entry_import_id.insert(0, msg_id)
        self.importar_msg_antiga()


if __name__ == "__main__":
    app = WebHooksPY()
    app.mainloop()
