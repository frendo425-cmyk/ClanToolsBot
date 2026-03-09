import disnake
from disnake.ext import commands
from disnake.ext.commands import InteractionBot
from disnake.ui import View, Modal, TextInput, button
import datetime
import json
import os
from dotenv import load_dotenv

# ===================== CONFIG =====================

load_dotenv()

TOKEN = os.getenv("TOKEN")
DATA_FILE = "guild_data.json"

intents = disnake.Intents.default()
intents.members = True
intents.voice_states = True

bot: InteractionBot = commands.InteractionBot(intents=intents)

# ===================== STORAGE =====================

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(guild_data, f, indent=4, ensure_ascii=False)

guild_data = load_data()

def get_guild(guild_id):
    gid = str(guild_id)

    default_structure = {
        "admin_role": None,
        "apps_channel": None,
        "accepted_role": None,
        "welcome_role": None,
        "voice_trigger": None,
        "voice_category": None,
        "temp_voices": {},
        "warns": {},
        "complaints_channel": None,
        "complaints_category": None,
        "open_complaints": {}
    }

    if gid not in guild_data:
        guild_data[gid] = default_structure
        save_data()
    else:
        # 🔥 Авто-добавление недостающих ключей
        for key, value in default_structure.items():
            if key not in guild_data[gid]:
                guild_data[gid][key] = value
                save_data()

    return guild_data[gid]

def is_admin(member):
    data = get_guild(member.guild.id)
    if member.guild_permissions.administrator:
        return True
    if data["admin_role"]:
        role = member.guild.get_role(data["admin_role"])
        return role in member.roles if role else False
    return False

# ===================== PERSISTENT VIEWS =====================

class ApplyView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @button(label="📝 Подать заявку", style=disnake.ButtonStyle.primary, custom_id="apply_btn")
    async def apply(self, button, inter):
        await inter.response.send_modal(ApplicationModal())

class AdminView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @button(label="✅ Принять", style=disnake.ButtonStyle.green, custom_id="admin_accept")
    async def accept(self, button, inter):
        if not is_admin(inter.author):
            return await inter.response.send_message("❌ Нет прав", ephemeral=True)

        embed = inter.message.embeds[0]
        user_id = int(embed.footer.text.replace("ID: ", ""))
        member = inter.guild.get_member(user_id)

        data = get_guild(inter.guild.id)
        role = inter.guild.get_role(data["accepted_role"])
 
        if member and role:
            await member.add_roles(role)

        embed.title = "✅ ЗАЯВКА ПРИНЯТА"
        embed.color = disnake.Color.green()
        await inter.message.edit(embed=embed, view=None)
        await inter.response.send_message("Принято", ephemeral=True)

    @button(label="❌ Отклонить", style=disnake.ButtonStyle.red, custom_id="admin_reject")
    async def reject(self, button, inter):
        if not is_admin(inter.author):
            return await inter.response.send_message("❌ Нет прав", ephemeral=True)

        embed = inter.message.embeds[0]
        embed.title = "❌ ЗАЯВКА ОТКЛОНЕНА"
        embed.color = disnake.Color.red()
        await inter.message.edit(embed=embed, view=None)
        await inter.response.send_message("Отклонено", ephemeral=True)

class VoiceControlView(View):
    def __init__(self):
        super().__init__(timeout=None)

    def get_voice(self, inter):
        if not inter.channel.topic:
            return None
        voice_id = int(inter.channel.topic)
        return inter.guild.get_channel(voice_id)

    def is_owner(self, inter, voice_id):
        data = get_guild(inter.guild.id)
        if str(voice_id) not in data["temp_voices"]:
            return False
        return data["temp_voices"][str(voice_id)]["owner"] == inter.author.id

    @button(label="🔒 Закрыть", style=disnake.ButtonStyle.red, custom_id="vc_lock")
    async def lock(self, button, inter):
        voice = self.get_voice(inter)
        if not voice:
            return await inter.response.send_message("❌ Ошибка", ephemeral=True)

        await voice.set_permissions(inter.guild.default_role, connect=False)
        await inter.response.send_message("🔒 Канал закрыт", ephemeral=True)

    @button(label="🔓 Открыть", style=disnake.ButtonStyle.green, custom_id="vc_unlock")
    async def unlock(self, button, inter):
        voice = self.get_voice(inter)
        if not voice:
            return await inter.response.send_message("❌ Ошибка", ephemeral=True)

        await voice.set_permissions(inter.guild.default_role, connect=True)
        await inter.response.send_message("🔓 Канал открыт", ephemeral=True)

    @button(label="🔢 Лимит", style=disnake.ButtonStyle.secondary, custom_id="vc_limit")
    async def limit(self, button, inter):
        voice = self.get_voice(inter)
        if not voice:
            return await inter.response.send_message("❌ Ошибка", ephemeral=True)

        if not self.is_owner(inter, voice.id):
            return await inter.response.send_message("❌ Вы не владелец канала", ephemeral=True)

        await inter.response.send_modal(VoiceLimitModal(voice.id))

    @button(label="✏ Переименовать", style=disnake.ButtonStyle.primary, custom_id="vc_rename")
    async def rename(self, button, inter):
        voice = self.get_voice(inter)
        if not voice:
            return await inter.response.send_message("❌ Ошибка", ephemeral=True)

        if not self.is_owner(inter, voice.id):
            return await inter.response.send_message("❌ Вы не владелец канала", ephemeral=True)

        await inter.response.send_modal(VoiceRenameModal(voice.id))

    @button(label="🗑 Удалить", style=disnake.ButtonStyle.danger, custom_id="vc_delete")
    async def delete(self, button, inter):
        voice = self.get_voice(inter)
        if not voice:
            return await inter.response.send_message("❌ Ошибка", ephemeral=True)

        if not self.is_owner(inter, voice.id):
            return await inter.response.send_message("❌ Вы не владелец канала", ephemeral=True)

        data = get_guild(inter.guild.id)
        data["temp_voices"].pop(str(voice.id), None)
        save_data()

        await voice.delete()
        await inter.channel.delete()

class ComplaintModal(Modal):
    def __init__(self):
        super().__init__(
            title="📩 Подать жалобу",
            custom_id="complaint_modal",
            components=[
                TextInput(
                    label="На кого жалоба?",
                    custom_id="target"
                ),
                TextInput(
                    label="Описание проблемы",
                    custom_id="reason",
                    style=disnake.TextInputStyle.paragraph
                )
            ]
        )

    async def callback(self, inter):
        data = get_guild(inter.guild.id)

        channel = inter.guild.get_channel(data["complaints_channel"])
        if not channel:
            return await inter.response.send_message(
                "❌ Канал жалоб не настроен",
                ephemeral=True
            )

        embed = disnake.Embed(
            title="🚨 Новая жалоба",
            color=disnake.Color.red(),
            timestamp=datetime.datetime.now()
        )

        embed.add_field(name="👤 От", value=inter.author.mention)
        embed.add_field(name="🎯 На кого", value=inter.text_values["target"])
        embed.add_field(name="📝 Причина",
                        value=inter.text_values["reason"],
                        inline=False)

        embed.set_footer(text=f"ID: {inter.author.id}")

        await channel.send(embed=embed, view=ComplaintAdminView())
        await inter.response.send_message(
            "✅ Ваша жалоба отправлена администрации",
            ephemeral=True
        )

class ComplaintAdminView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @button(label="✅ Принять", style=disnake.ButtonStyle.green, custom_id="complaint_accept")
    async def accept(self, button, inter):
        if not inter.author.guild_permissions.moderate_members:
            return await inter.response.send_message("❌ Нет прав", ephemeral=True)

        embed = inter.message.embeds[0]
        embed.title = "✅ Жалоба рассмотрена"
        embed.color = disnake.Color.green()

        await inter.message.edit(embed=embed, view=None)
        await inter.response.send_message("Жалоба принята", ephemeral=True)

    @button(label="❌ Отклонить", style=disnake.ButtonStyle.red, custom_id="complaint_reject")
    async def reject(self, button, inter):
        if not inter.author.guild_permissions.moderate_members:
            return await inter.response.send_message("❌ Нет прав", ephemeral=True)

        embed = inter.message.embeds[0]
        embed.title = "❌ Жалоба отклонена"
        embed.color = disnake.Color.dark_red()

        await inter.message.edit(embed=embed, view=None)
        await inter.response.send_message("Жалоба отклонена", ephemeral=True)

class ComplaintPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @button(label="📩 Подать жалобу",
            style=disnake.ButtonStyle.danger,
            custom_id="complaint_create")
    async def create(self, button, inter):
        await inter.response.send_modal(ComplaintModal())

class ComplaintManageView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @button(label="🔒 Закрыть", style=disnake.ButtonStyle.gray, custom_id="complaint_close")
    async def close(self, button, inter):
        if not inter.author.guild_permissions.manage_channels:
            return await inter.response.send_message("❌ Нет прав", ephemeral=True)

        await inter.channel.edit(name=f"закрыто-{inter.channel.name}")
        await inter.response.send_message("🔒 Жалоба закрыта")

    @button(label="🗑 Удалить", style=disnake.ButtonStyle.danger, custom_id="complaint_delete")
    async def delete(self, button, inter):
        if not inter.author.guild_permissions.manage_channels:
            return await inter.response.send_message("❌ Нет прав", ephemeral=True)

        data = get_guild(inter.guild.id)
        data["open_complaints"].pop(str(inter.channel.id), None)
        save_data()

        await inter.response.send_message("🗑 Жалоба удаляется...")
        await inter.channel.delete()

# ===================== MODALS =====================

class ApplicationModal(Modal):
    def __init__(self):
        super().__init__(
            title="📝 Заявка",
            custom_id="application_modal",
            components=[
                TextInput(label="Ник", custom_id="nick"),
                TextInput(label="K/D", custom_id="kd"),
                TextInput(label="Отряд", custom_id="squad"),
                TextInput(label="Дополнительно", custom_id="info", required=False,
                          style=disnake.TextInputStyle.paragraph)
            ]
        )

    async def callback(self, inter):
        data = get_guild(inter.guild.id)
        channel = inter.guild.get_channel(data["apps_channel"])
        if not channel:
            return await inter.response.send_message("❌ Канал заявок не настроен", ephemeral=True)

        embed = disnake.Embed(
            title="🎖️ НОВАЯ ЗАЯВКА",
            color=disnake.Color.blue(),
            timestamp=datetime.datetime.now()
        )

        embed.add_field(name="Ник", value=inter.text_values["nick"])
        embed.add_field(name="K/D", value=inter.text_values["kd"])
        embed.add_field(name="Отряд", value=inter.text_values["squad"])
        embed.add_field(name="Дополнительно",
                        value=inter.text_values.get("info", "—"),
                        inline=False)

        embed.set_footer(text=f"ID: {inter.author.id}")

        await channel.send(embed=embed, view=AdminView())
        await inter.response.send_message("✅ Заявка отправлена", ephemeral=True)

class VoiceLimitModal(Modal):
    def __init__(self, voice_id: int):
        self.voice_id = voice_id

        super().__init__(
            title="🔢 Установить лимит",
            custom_id=f"voice_limit_{voice_id}",
            components=[
                TextInput(
                    label="Введите лимит (0 = без лимита)",
                    custom_id="limit",
                    max_length=2
                )
            ]
        )

    async def callback(self, inter):
        data = get_guild(inter.guild.id)

        if str(self.voice_id) not in data["temp_voices"]:
            return await inter.response.send_message("❌ Канал не найден", ephemeral=True)

        if data["temp_voices"][str(self.voice_id)]["owner"] != inter.author.id:
            return await inter.response.send_message("❌ Вы не владелец канала", ephemeral=True)

        try:
            limit = int(inter.text_values["limit"])
            if limit < 0 or limit > 99:
                raise ValueError
        except:
            return await inter.response.send_message("⚠ Введите число от 0 до 99", ephemeral=True)

        voice = inter.guild.get_channel(self.voice_id)
        if voice:
            await voice.edit(user_limit=limit)

        await inter.response.send_message(
            f"✅ Лимит установлен: {limit}",
            ephemeral=True
        )

class VoiceRenameModal(Modal):
    def __init__(self, voice_id: int):
        self.voice_id = voice_id

        super().__init__(
            title="✏ Переименовать канал",
            custom_id=f"voice_rename_{voice_id}",
            components=[
                TextInput(
                    label="Новое название",
                    custom_id="name",
                    max_length=30
                )
            ]
        )

    async def callback(self, inter):
        data = get_guild(inter.guild.id)

        if str(self.voice_id) not in data["temp_voices"]:
            return await inter.response.send_message("❌ Канал не найден", ephemeral=True)

        if data["temp_voices"][str(self.voice_id)]["owner"] != inter.author.id:
            return await inter.response.send_message("❌ Вы не владелец канала", ephemeral=True)

        new_name = inter.text_values["name"]

        voice = inter.guild.get_channel(self.voice_id)
        if voice:
            await voice.edit(name=f"🔊 {new_name}")

        await inter.response.send_message(
            f"✅ Канал переименован в {new_name}",
            ephemeral=True
        )

# ===================== EVENTS =====================

@bot.event
async def on_ready():
    bot.add_view(ApplyView())
    bot.add_view(AdminView())
    bot.add_view(VoiceControlView())
    bot.add_view(ComplaintPanelView())
    bot.add_view(ComplaintAdminView())
    print(f"✅ Бот запущен как {bot.user}")

@bot.event
async def on_member_join(member: disnake.Member):

    data = get_guild(member.guild.id)

    role_id = data.get("welcome_role")
    if role_id:
        role = member.guild.get_role(role_id)
        if role:
            try:
                await member.add_roles(role)
            except Exception as e:
                print(f"Ошибка выдачи роли: {e}")

    channel = member.guild.system_channel
    if not channel:
        return

    now = datetime.datetime.now()
    account_created = member.created_at.replace(tzinfo=None)
    account_age_days = (now - account_created).days

    embed = disnake.Embed(
        title="✨ Добро пожаловать на сервер!",
        description=f"Рады видеть тебя, {member.mention} 💜",
        color=disnake.Color.from_rgb(138, 43, 226),  # фиолетовый
        timestamp=datetime.datetime.now()
    )

    embed.add_field(
        name="👤 Имя пользователя",
        value=f"`{member}`",
        inline=False
    )

    embed.add_field(
        name="🆔 ID пользователя",
        value=f"`{member.id}`",
        inline=True
    )

    embed.add_field(
        name="📅 Возраст аккаунта",
        value=f"`{account_age_days} дней`",
        inline=True
    )

    embed.add_field(
        name="👥 Участников на сервере",
        value=f"`{member.guild.member_count}`",
        inline=False
    )

    embed.add_field(
        name="⏰ Время входа",
        value=datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        inline=False
    )

    # Аватар пользователя
    embed.set_thumbnail(url=member.display_avatar.url)

    # GIF анимация
    embed.set_image(
        url="https://media.giphy.com/media/OkJat1YNdoD3W/giphy.gif"
    )

    embed.set_footer(text="Мы рады каждому новому участнику 💜")

    await channel.send(embed=embed)

@bot.event
async def on_voice_state_update(member, before, after):
    data = get_guild(member.guild.id)

    # Создание временного канала
    if after.channel and after.channel.id == data["voice_trigger"]:
        category = member.guild.get_channel(data["voice_category"])
        voice = await member.guild.create_voice_channel(
            f"🔊 {member.name}",
            category=category
        )

        text = await member.guild.create_text_channel(
            f"💬・{member.name}",
            category=category,
            topic=str(voice.id)
        )

        await text.set_permissions(member.guild.default_role, view_channel=False)
        await text.set_permissions(member, view_channel=True, send_messages=True)

        await member.move_to(voice)

        data["temp_voices"][str(voice.id)] = {
            "owner": member.id,
            "text_id": text.id
        }
        save_data()

        await text.send(embed=disnake.Embed(title="🎛 Управление"),
                        view=VoiceControlView())

    # Удаление пустого канала
    if before.channel and str(before.channel.id) in data["temp_voices"]:
        if len(before.channel.members) == 0:
            info = data["temp_voices"].pop(str(before.channel.id))
            save_data()

            txt = member.guild.get_channel(info["text_id"])
            if txt:
                await txt.delete()

            await before.channel.delete()

# ===================== COMMANDS =====================

@bot.slash_command(description="Установить роль для новых участников")
async def setup_welcome_role(
    inter: disnake.ApplicationCommandInteraction,
    role: disnake.Role
):
    if not inter.author.guild_permissions.administrator:
        return await inter.response.send_message(
            "❌ Только администратор может использовать эту команду.",
            ephemeral=True
        )

    data = get_guild(inter.guild.id)
    data["welcome_role"] = role.id
    save_data()

    await inter.response.send_message(
        f"✅ Теперь новым участникам будет выдаваться роль {role.mention}",
        ephemeral=True
    )

@bot.slash_command()
async def setup(inter, apps_channel: disnake.TextChannel,
                admin_role: disnake.Role,
                accepted_role: disnake.Role):
    data = get_guild(inter.guild.id)
    data["apps_channel"] = apps_channel.id
    data["admin_role"] = admin_role.id
    data["accepted_role"] = accepted_role.id
    save_data()
    await inter.response.send_message("✅ Настройка завершена", ephemeral=True)

@bot.slash_command()
async def panel(inter):
    await inter.channel.send(embed=disnake.Embed(title="🎖️ Набор открыт"),
                             view=ApplyView())
    await inter.response.send_message("✅ Панель создана", ephemeral=True)

@bot.slash_command()
async def voice_setup(inter,
                      trigger: disnake.VoiceChannel,
                      category: disnake.CategoryChannel):
    data = get_guild(inter.guild.id)
    data["voice_trigger"] = trigger.id
    data["voice_category"] = category.id
    save_data()
    await inter.response.send_message("🔊 Временные войсы включены", ephemeral=True)

@bot.slash_command(description="Настроить канал для жалоб")
async def complaints_setup(
    inter,
    channel: disnake.TextChannel
):
    if not inter.author.guild_permissions.administrator:
        return await inter.response.send_message("❌ Нет прав", ephemeral=True)

    data = get_guild(inter.guild.id)
    data["complaints_channel"] = channel.id
    save_data()

    await inter.response.send_message(
        f"✅ Канал жалоб установлен: {channel.mention}",
        ephemeral=True
    )

@bot.slash_command(description="Создать панель жалоб")
async def complaints_panel(inter):
    await inter.channel.send(
        embed=disnake.Embed(
            title="📩 Панель жалоб",
            description="Нажмите кнопку ниже чтобы отправить жалобу администрации",
            color=disnake.Color.red()
        ),
        view=ComplaintPanelView()
    )

    await inter.response.send_message("✅ Панель создана", ephemeral=True)

# ===================== MODERATION COMMANDS =====================

@bot.slash_command(description="Очистить сообщения в канале")
async def clear(
    inter: disnake.ApplicationCommandInteraction,
    amount: int
):
    if not inter.author.guild_permissions.manage_messages:
        return await inter.response.send_message(
            "❌ У вас нет прав на управление сообщениями.",
            ephemeral=True
        )

    if amount < 1 or amount > 100:
        return await inter.response.send_message(
            "⚠ Укажите число от 1 до 100.",
            ephemeral=True
        )

    await inter.response.defer(ephemeral=True)

    deleted = await inter.channel.purge(limit=amount)

    await inter.followup.send(
        f"🧹 Удалено сообщений: {len(deleted)}",
        ephemeral=True
    )


@bot.slash_command(description="Забанить пользователя")
async def ban(
    inter: disnake.ApplicationCommandInteraction,
    member: disnake.Member,
    reason: str = "Не указана"
):
    if not inter.author.guild_permissions.ban_members:
        return await inter.response.send_message(
            "❌ У вас нет прав на бан.",
            ephemeral=True
        )

    await member.ban(reason=reason)

    await inter.response.send_message(
        f"🔨 {member.mention} был забанен.\nПричина: {reason}"
    )


@bot.slash_command(description="Разбанить пользователя по ID")
async def unban(
    inter: disnake.ApplicationCommandInteraction,
    user_id: str
):
    if not inter.author.guild_permissions.ban_members:
        return await inter.response.send_message(
            "❌ У вас нет прав на разбан.",
            ephemeral=True
        )

    try:
        user = await bot.fetch_user(int(user_id))
        await inter.guild.unban(user)

        await inter.response.send_message(
            f"✅ Пользователь {user} разбанен."
        )
    except:
        await inter.response.send_message(
            "❌ Пользователь не найден в бане.",
            ephemeral=True
        )


@bot.slash_command(description="Кикнуть пользователя")
async def kick(
    inter: disnake.ApplicationCommandInteraction,
    member: disnake.Member,
    reason: str = "Не указана"
):
    if not inter.author.guild_permissions.kick_members:
        return await inter.response.send_message(
            "❌ У вас нет прав на кик.",
            ephemeral=True
        )

    await member.kick(reason=reason)

    await inter.response.send_message(
        f"👢 {member.mention} был кикнут.\nПричина: {reason}"
    )


@bot.slash_command(description="Выдать тайм-аут пользователю")
async def timeout(
    inter: disnake.ApplicationCommandInteraction,
    member: disnake.Member,
    minutes: int,
    reason: str = "Не указана"
):
    if not inter.author.guild_permissions.moderate_members:
        return await inter.response.send_message(
            "❌ У вас нет прав на тайм-аут.",
            ephemeral=True
        )

    duration = datetime.timedelta(minutes=minutes)

    await member.timeout(duration=duration, reason=reason)

    await inter.response.send_message(
        f"⏳ {member.mention} получил тайм-аут на {minutes} минут.\nПричина: {reason}"
    )


@bot.slash_command(description="Снять тайм-аут с пользователя")
async def untimeout(
    inter: disnake.ApplicationCommandInteraction,
    member: disnake.Member
):
    if not inter.author.guild_permissions.moderate_members:
        return await inter.response.send_message(
            "❌ У вас нет прав.",
            ephemeral=True
        )

    await member.timeout(duration=None)

    await inter.response.send_message(
        f"✅ Тайм-аут с {member.mention} снят."
    )

# ===================== WARN SYSTEM =====================

MAX_WARNS = 3


@bot.slash_command(description="Выдать предупреждение пользователю")
async def warn(
    inter: disnake.ApplicationCommandInteraction,
    member: disnake.Member,
    reason: str = "Не указана"
):
    if not inter.author.guild_permissions.moderate_members:
        return await inter.response.send_message(
            "❌ У вас нет прав.",
            ephemeral=True
        )

    data = get_guild(inter.guild.id)

    user_id = str(member.id)

    if user_id not in data["warns"]:
        data["warns"][user_id] = []

    data["warns"][user_id].append({
        "reason": reason,
        "moderator": inter.author.id,
        "date": datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    })

    warn_count = len(data["warns"][user_id])
    save_data()

    embed = disnake.Embed(
        title="⚠ Пользователь получил предупреждение",
        color=disnake.Color.orange()
    )

    embed.add_field(name="👤 Пользователь", value=member.mention)
    embed.add_field(name="📝 Причина", value=reason, inline=False)
    embed.add_field(name="📊 Всего варнов", value=f"{warn_count}/{MAX_WARNS}")

    await inter.response.send_message(embed=embed)

    try:
        dm_embed = disnake.Embed(
            title="⚠ Вам выдано предупреждение",
            color=disnake.Color.orange()
        )

        dm_embed.add_field(name="📌 Сервер", value=inter.guild.name, inline=False)
        dm_embed.add_field(name="📝 Причина", value=reason, inline=False)
        dm_embed.add_field(
            name="📊 Всего предупреждений",
            value=f"{warn_count}/{MAX_WARNS}",
            inline=False
        )

        await member.send(embed=dm_embed)

    except disnake.Forbidden:
        pass

        # Автонаказание
    if warn_count >= MAX_WARNS:

        try:
            await member.send(
                f"🚨 Вы получили {MAX_WARNS} предупреждения на сервере {inter.guild.name} "
                "и были кикнуты."
            )
        except disnake.Forbidden:
            pass

        await member.kick(reason="Превышен лимит предупреждений")

        data["warns"][user_id] = []
        save_data()

        await inter.channel.send(
            f"🚨 {member.mention} получил 3 предупреждения и был КИКНУТ"
        )

@bot.slash_command(description="Снять самое старое предупреждение с пользователя")
async def remove_warn(
    inter: disnake.ApplicationCommandInteraction,
    member: disnake.Member
):
    if not inter.author.guild_permissions.moderate_members:
        return await inter.response.send_message(
            "❌ У вас нет прав.",
            ephemeral=True
        )

    data = get_guild(inter.guild.id)
    user_id = str(member.id)

    if user_id not in data["warns"] or not data["warns"][user_id]:
        return await inter.response.send_message(
            "⚠ У пользователя нет предупреждений.",
            ephemeral=True
        )


    # Удаляем самый старый варн
    removed_warn = data["warns"][user_id].pop(0)
    save_data()

    try:
        dm_embed = disnake.Embed(
            title="🧹 С вас снято предупреждение",
            color=disnake.Color.green()
        )

        dm_embed.add_field(name="📌 Сервер", value=inter.guild.name, inline=False)
        dm_embed.add_field(
            name="📝 Снятая причина",
            value=removed_warn['reason'],
            inline=False
        )

        dm_embed.add_field(
            name="📊 Осталось предупреждений",
            value=f"{len(data['warns'][user_id])}/{MAX_WARNS}",
            inline=False
        )

        await member.send(embed=dm_embed)

    except disnake.Forbidden:
        pass

    await inter.response.send_message(
        f"🧹 С пользователя {member.mention} снято самое старое предупреждение.\n"
        f"Причина: {removed_warn['reason']}\n"
        f"Осталось варнов: {len(data['warns'][user_id])}/{MAX_WARNS}"
    )


@bot.slash_command(description="Посмотреть предупреждения пользователя")
async def warns(
    inter: disnake.ApplicationCommandInteraction,
    member: disnake.Member
):
    data = get_guild(inter.guild.id)
    user_id = str(member.id)

    if user_id not in data["warns"] or not data["warns"][user_id]:
        return await inter.response.send_message(
            "✅ У пользователя нет предупреждений.",
            ephemeral=True
        )

    embed = disnake.Embed(
        title=f"⚠ Варны пользователя {member}",
        color=disnake.Color.red()
    )

    for i, warn in enumerate(data["warns"][user_id], start=1):
        embed.add_field(
            name=f"Warn #{i}",
            value=f"Причина: {warn['reason']}\n"
                  f"Модератор: <@{warn['moderator']}>\n"
                  f"Дата: {warn['date']}",
            inline=False
        )

    embed.set_footer(text=f"Всего: {len(data['warns'][user_id])}")

    await inter.response.send_message(embed=embed, ephemeral=True)


@bot.slash_command(description="Очистить предупреждения пользователя")
async def clear_warns(
    inter: disnake.ApplicationCommandInteraction,
    member: disnake.Member
):
    if not inter.author.guild_permissions.moderate_members:
        return await inter.response.send_message(
            "❌ У вас нет прав.",
            ephemeral=True
        )

    data = get_guild(inter.guild.id)
    user_id = str(member.id)

    data["warns"][user_id] = []
    save_data()

    await inter.response.send_message(
        f"🧹 Все предупреждения пользователя {member.mention} очищены."
    )

# ===================== RUN =====================

bot.run(TOKEN)