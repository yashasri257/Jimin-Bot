import discord, random, time, asyncio
from discord.ext import commands
from discord import app_commands
from motor.motor_asyncio import AsyncIOMotorClient
from PIL import Image
from io import BytesIO
import aiohttp
import os
from PIL import Image, ImageDraw, ImageFont

raw = os.getenv("TOKEN")
print("TOKEN raw repr:", repr(raw))      # shows hidden chars
print("TOKEN length:", len(raw) if raw else None)
print("TOKEN has spaces?", (" " in raw) if raw else None)

TOKEN = raw.strip() if raw else None     # remove any hidden whitespace
print("TOKEN start:", TOKEN[:10] if TOKEN else None)

# ======================
# CONFIG
# ======================

TOKEN = os.getenv("TOKEN")
MONGO = os.getenv("MONGO")

STAFF_IDS = [
    1106193228971122689,
    702667135775801376,
    701969588157415506,
    701968449462599752,
    871159389799743488
]

LOG_CHANNEL_ID = 1496151311836512378
CURRENCY = "Relics"

DROP_CD = 300
CLAIM_CD = 120
DAILY_CD = 79200
WEEKLY_CD = 604800
MONTHLY_CD = 2592000

RARITIES = ["whisper","cherub","siren","enthrall","devotion","eclipse","velour","fallen","sanctum"]
RARITY_CHOICES = [
    app_commands.Choice(name="Whisper", value="whisper"),
    app_commands.Choice(name="Cherub", value="cherub"),
    app_commands.Choice(name="Siren", value="siren"),
    app_commands.Choice(name="Enthrall", value="enthrall"),
    app_commands.Choice(name="Devotion", value="devotion"),
    app_commands.Choice(name="Fallen", value="fallen"),
    app_commands.Choice(name="Eclipse", value="eclipse"),
    app_commands.Choice(name="Velour", value="velour"),
    app_commands.Choice(name="Sanctum", value="sanctum"),
]
RARITY_EMOJIS = {
    "whisper": "<:whisper:1498991362396131389>",
    "cherub": "<:cherub:1498991360227934299>",
    "siren": "<:siren:1498991357904158810>",
    "enthrall": "<:enthrall:1498991347380523048>",
    "devotion": "<:devotion:1498991355890761868>",
    "fallen": "<:fallen:1498991353290555432>",
    "eclipse": "<:eclipse:1498991351285678243>",
    "velour": "<:velour:1498991364556324884>",
    "sanctum": "<:sanctum:1498991349347647559>",
}
# ======================
# BOT SETUP
# ======================

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

client = AsyncIOMotorClient(MONGO)
db = client["kpop"]
cards = db["cards"]
users = db["users"]

# ======================
# HELPERS
# ======================

def is_staff(uid):
    return uid in STAFF_IDS

async def log(bot, msg):
    ch = bot.get_channel(LOG_CHANNEL_ID)
    if ch:
        await ch.send(msg)

def now():
    return int(time.time())

def cd_left(last, cd):
    return max(0, cd - (now() - last))

cooldowns = {}

async def check_cd(uid, key, cd):
    user = await users.find_one({"id": uid}) or {}
    last = user.get(f"{key}_cd", 0)
    return max(0, cd - (now() - last))

async def set_cooldown(uid, key):
    await users.update_one(
        {"id": uid},
        {"$set": {f"{key}_cd": now()}},
        upsert=True
    )

from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

CELL_POS = [
    (100,100),(300,100),(500,100),
    (100,300),(300,300),(500,300),
    (100,500),(300,500),(500,500)
]

def draw_board(board):
    img = Image.new("RGBA", (600, 600), (20, 20, 25))
    draw = ImageDraw.Draw(img)

    for i in range(1, 3):
        draw.line((0, i*200, 600, i*200), fill=(200,200,200), width=6)
        draw.line((i*200, 0, i*200, 600), fill=(200,200,200), width=6)

    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 140)
    except:
        font = ImageFont.load_default()

    for i, val in enumerate(board):
        if val:
            x, y = CELL_POS[i]
            draw.text((x, y), val, font=font, fill=(255,255,255))

    buf = BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return buf

async def get_card_by_rarity(rarities):
    results = await cards.find({
        "rarity": {"$in": rarities},
        "droppable": True
    }).to_list(50)  # limit to avoid heavy load

    if not results:
        return None

    return random.choice(results)

def rarity_emoji(rarity):
    return RARITY_EMOJIS.get(rarity, "✦")
    
# ======================
# ⏳ GLOBAL COOLDOWN SYSTEM (PERMANENT)
# ======================

def now():
    return int(time.time())

async def get_user(uid):
    return await users.find_one({"id": uid}) or {}

async def check_cd(uid, key, cd):
    user = await get_user(uid)
    last = user.get(f"{key}_cd", 0)
    return max(0, cd - (now() - last))

async def set_cd(uid, key):
    await users.update_one(
        {"id": uid},
        {"$set": {f"{key}_cd": now()}},
        upsert=True
    )

def fmt(sec):
    if sec <= 0:
        return "ready ✧"
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h}h {m}m {s}s"


# ======================
# ADD CARD
# ======================
@tree.command(name="add_card", description="✧ add a new card (staff only)")
@app_commands.choices(rarity=RARITY_CHOICES)
async def add_card(
    interaction: discord.Interaction,
    name: str,
    group: str,
    rarity: app_commands.Choice[str],
    card_code: str,
    image_url: str,
    droppable: bool,
    rarity_back: str = None,
    era: str = None
):

    if not is_staff(interaction.user.id):
        return await interaction.response.send_message("✧ no permission", ephemeral=True)

    await cards.insert_one({
        "name": name,
        "group": group.lower(),
        "rarity": rarity.value,
        "card_code": card_code.lower(),
        "image_url": image_url,
        "droppable": droppable,
        "rarity_back": rarity_back,
        "era": era
    })

    emoji = get_rarity_emoji(rarity.value)

    embed = discord.Embed(
        title="✧ card added",
        description=f"{emoji} **{name}** | {group} | {rarity.name}",
        color=0x2b2d31
    )

    embed.set_image(url=image_url)

    await interaction.response.send_message(embed=embed)
    
# ======================
# DELETE
# ======================

@tree.command(name="del_card", description="✧ remove a card (staff)")
async def del_card(interaction:discord.Interaction, card_code:str):
    if not is_staff(interaction.user.id):
        return await interaction.response.send_message("✧ no permission", ephemeral=True)

    await cards.delete_one({"card_code":card_code})
    await interaction.response.send_message("✧ card deleted")
    
# ======================
# edit card 
# ======================

@tree.command(name="edit_card", description="✧ edit an existing card (staff)")
async def edit_card(
    interaction: discord.Interaction,
    card_code: str,

    new_name: str = None,
    new_group: str = None,
    new_rarity: str = None,
    new_card_code: str = None,
    new_image_url: str = None,
    new_droppable: bool = None,
    new_rarity_back: str = None,
    new_era: str = None
):

    # ======================
    # PERMISSION CHECK
    # ======================
    if not is_staff(interaction.user.id):
        return await interaction.response.send_message(
            "✧ no permission", ephemeral=True
        )

    await interaction.response.defer()

    code = card_code.lower()

    # ======================
    # FIND CARD
    # ======================
    card = await cards.find_one({"card_code": code})

    if not card:
        return await interaction.followup.send("✧ card not found")

    update = {}
    log_text = f"✧ {interaction.user} edited {code}\n"

    # ======================
    # APPLY CHANGES
    # ======================
    if new_name:
        update["name"] = new_name
        log_text += f"• name → {new_name}\n"

    if new_group:
        update["group"] = new_group.lower()
        log_text += f"• group → {new_group}\n"

    if new_rarity:
        update["rarity"] = new_rarity.lower()
        log_text += f"• rarity → {new_rarity}\n"

    if new_image_url:
        update["image_url"] = new_image_url
        log_text += f"• image updated\n"

    if new_droppable is not None:
        update["droppable"] = new_droppable
        log_text += f"• droppable → {new_droppable}\n"

    if new_rarity_back:
        update["rarity_back"] = new_rarity_back
        log_text += f"• rarity_back updated\n"

    if new_era:
        update["era"] = new_era
        log_text += f"• era → {new_era}\n"

    # ======================
    # CARD CODE CHANGE (IMPORTANT)
    # ======================
    if new_card_code:
        new_code = new_card_code.lower()

        # check if already exists
        exists = await cards.find_one({"card_code": new_code})
        if exists:
            return await interaction.followup.send("✧ new code already exists")

        update["card_code"] = new_code

        # ALSO UPDATE USER INVENTORIES
        all_users = users.find({f"cards.{code}": {"$exists": True}})

        async for u in all_users:
            amount = u.get("cards", {}).get(code, 0)
            if amount > 0:
                await users.update_one(
                    {"id": u["id"]},
                    {
                        "$inc": {
                            f"cards.{code}": -amount,
                            f"cards.{new_code}": amount
                        }
                    }
                )

        log_text += f"• card_code → {new_code}\n"

    # ======================
    # APPLY UPDATE
    # ======================
    if not update:
        return await interaction.followup.send("✧ nothing to update")

    await cards.update_one(
        {"card_code": code},
        {"$set": update}
    )

    # ======================
    # SUCCESS MESSAGE
    # ======================
    embed = discord.Embed(
        title="✧ card updated",
        description=f"`{code}` edited successfully",
        color=0x2b2d31
    )

    await interaction.followup.send(embed=embed)

    # optional logging
    await log(bot, log_text)


# ======================
# mass edit 
# ======================
@tree.command(name="mass_edit", description="✧ mass edit cards (staff)")
async def mass_edit(
    interaction: discord.Interaction,

    group: str = None,
    rarity: str = None,
    era: str = None,

    set_droppable: bool = None,
    new_rarity: str = None,
    new_era: str = None
):

    # ======================
    # PERMISSION
    # ======================
    if not is_staff(interaction.user.id):
        return await interaction.response.send_message(
            "✧ no permission", ephemeral=True
        )

    await interaction.response.defer()

    # ======================
    # BUILD FILTER
    # ======================
    query = {}

    if group:
        query["group"] = group.lower()

    if rarity:
        query["rarity"] = rarity.lower()

    if era:
        query["era"] = {"$regex": era, "$options": "i"}

    # ======================
    # CHECK MATCHES
    # ======================
    count = await cards.count_documents(query)

    if count == 0:
        return await interaction.followup.send("✧ no cards matched")

    # ======================
    # BUILD UPDATE
    # ======================
    update = {}
    log_text = f"✧ {interaction.user} mass edited\n"

    if set_droppable is not None:
        update["droppable"] = set_droppable
        log_text += f"• droppable → {set_droppable}\n"

    if new_rarity:
        update["rarity"] = new_rarity.lower()
        log_text += f"• rarity → {new_rarity}\n"

    if new_era:
        update["era"] = new_era
        log_text += f"• era → {new_era}\n"

    if not update:
        return await interaction.followup.send("✧ nothing to update")

    # ======================
    # APPLY MASS UPDATE
    # ======================
    await cards.update_many(
        query,
        {"$set": update}
    )

    # ======================
    # RESPONSE
    # ======================
    embed = discord.Embed(
        title="✧ mass edit complete",
        description=f"updated **{count}** cards",
        color=0x2b2d31
    )

    await interaction.followup.send(embed=embed)

    await log(bot, log_text)


# ======================
# DROP
# ======================

last_drop = {}
last_claim = {}

class DropView(discord.ui.View):
    def __init__(self, cards_list, owner):
        super().__init__(timeout=60)
        self.cards = cards_list
        self.owner = owner
        self.claimed = [False]*3
        self.start = now()

    async def handle(self, interaction, idx):
        uid = interaction.user.id

        # owner priority
        if uid != self.owner and now() - self.start < 25:
            return await interaction.response.send_message(
                "✧ wait for the summoner...",
                ephemeral=True
            )

        if self.claimed[idx]:
            return await interaction.response.send_message("✧ taken", ephemeral=True)

        if cd_left(last_claim.get(uid,0), CLAIM_CD) > 0:
            return await interaction.response.send_message("✧ slow down...", ephemeral=True)

        last_claim[uid] = now()
        self.claimed[idx] = True

        card = self.cards[idx]

        await users.update_one(
            {"id":uid},
            {"$inc":{f"cards.{card['card_code']}":1}},
            upsert=True
        )

        self.children[idx].disabled = True
        await interaction.response.edit_message(view=self)

        await interaction.followup.send("✧ revealing...")

        await asyncio.sleep(5)

        e = discord.Embed(
            title=card["name"],
            description=f"{card['group']} • {card['rarity']}",
            color=0x2b2d31
        )
        e.set_image(url=card["image_url"])

        await interaction.followup.send(embed=e)

    @discord.ui.button(label="1")
    async def b1(self,i,b): await self.handle(i,0)

    @discord.ui.button(label="2")
    async def b2(self,i,b): await self.handle(i,1)

    @discord.ui.button(label="3")
    async def b3(self,i,b): await self.handle(i,2)

@tree.command(name="drop", description="✧ summon cards")
async def drop(interaction: discord.Interaction):

    await interaction.response.send_message("✧ summoning...")

    uid = interaction.user.id

    if cd_left(last_drop.get(uid,0), DROP_CD) > 0:
        return await interaction.edit_original_response(content="✧ return later...")

    last_drop[uid] = now()

    chosen = []
    for _ in range(3):
        c = await get_card()
        if not c:
            return await interaction.edit_original_response(content="✧ no cards yet")
        chosen.append(c)

    backs = [c["rarity_back"] for c in chosen]
    img = await merge(backs)

    file = discord.File(img, "drop.png")

    e = discord.Embed(
        title="✧ ethereal descent ✧",
        description="three unseen cards descend...\nchoose one",
        color=0x2b2d31
    )

    for i,c in enumerate(chosen,1):
        e.add_field(name=f"{i}. {c['rarity']}", value=c["group"])

    await interaction.edit_original_response(
        content=None,
        embed=e,
        attachments=[file],
        view=DropView(chosen, uid)
    )


# ======================
# INVENTORY (FAST)
# ======================
@tree.command(name="inventory", description="✧ view collection")
@app_commands.choices(rarity=RARITY_CHOICES)
async def inventory(
    interaction: discord.Interaction,
    user: discord.Member=None,
    name: str=None,
    group: str=None,
    rarity: app_commands.Choice[str]=None,
    era: str=None,
    dupes: bool=False
):
    await interaction.response.defer()

    target = user or interaction.user

    data = await users.find_one({"id": target.id}) or {"cards": {}}
    user_cards = data.get("cards", {})

    valid = {k:v for k,v in user_cards.items() if v > 0}
    if not valid:
        return await interaction.followup.send("✧ nothing here yet...")

    query = {"card_code": {"$in": list(valid.keys())}}

    if name:
        query["name"] = {"$regex": name, "$options": "i"}
    if group:
        query["group"] = {"$regex": group, "$options": "i"}
    if rarity:
        query["rarity"] = rarity.value
    if era:
        query["era"] = {"$regex": era, "$options": "i"}

    cards_data = await cards.find(query).to_list(None)

    lines = []

for c in cards_data:
    count = valid.get(c["card_code"], 0)
    if count <= 0:
        continue

    if dupes:
        count -= 1
        if count <= 0:
            continue

    emoji = rarity_emoji(c["rarity"])

    lines.append(
        f"{emoji} **{c['group']}** ⟡ {c['name']}\n"
        f"〔{c['rarity']}〕 • `{c['card_code']}` • {count}"
    )

if not lines:
    return await interaction.followup.send("✧ nothing matches...")
    
    lines.sort(key=lambda x: x.lower())
    pages = [lines[i:i+5] for i in range(0, len(lines), 5)]

    class InvView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=120)
            self.page = 0

        async def update(self, interaction):
            embed = discord.Embed(
                description="\n\n".join(pages[self.page]),
                color=0x2b2d31
            )
            embed.set_author(
                name=f"{target.name}'s archive ✧",
                icon_url=target.display_avatar.url
            )
            embed.set_footer(
                text=f"{self.page+1}/{len(pages)} • total: {len(lines)} cards"
            )
            await interaction.response.edit_message(embed=embed, view=self)

        @discord.ui.button(label="◀")
        async def prev(self, interaction, button):
            if interaction.user.id != target.id:
                return await interaction.response.send_message("✧ not yours", ephemeral=True)
            if self.page > 0:
                self.page -= 1
            await self.update(interaction)

        @discord.ui.button(label="▶")
        async def next(self, interaction, button):
            if interaction.user.id != target.id:
                return await interaction.response.send_message("✧ not yours", ephemeral=True)
            if self.page < len(pages)-1:
                self.page += 1
            await self.update(interaction)

    embed = discord.Embed(
        description="\n\n".join(pages[0]),
        color=0x2b2d31
    )
    embed.set_author(
        name=f"{target.name}'s archive ✧",
        icon_url=target.display_avatar.url
    )
    embed.set_footer(text=f"1/{len(pages)} • total: {len(lines)} cards")

    await interaction.followup.send(embed=embed, view=InvView())
    
# =========================
# ⏳ TIME FORMAT
# =========================

def format_time(sec):
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h}h {m}m {s}s"

# =========================
# 🎁 DAILY
# =========================
@tree.command(name="daily", description="✧ daily reward")
async def daily(interaction: discord.Interaction):

    await interaction.response.send_message("✧ descending...")

    uid = interaction.user.id

    left = await check_cd(uid, "daily", DAILY_CD)
    if left > 0:
        return await interaction.edit_original_response(content=f"✧ wait {format_time(left)}")

    await set_cooldown(uid, "daily")

    reward = random.randint(500,800)

    await users.update_one(
        {"id": uid},
        {"$inc": {"currency": reward}},
        upsert=True
    )

    await interaction.edit_original_response(
        content=f"✧ +{reward} {CURRENCY}"
    )

# =========================
# 📦 WEEKLY
# =========================
@tree.command(name="weekly", description="✧ claim weekly relics")
async def weekly(interaction: discord.Interaction):

    uid = interaction.user.id

    left = await check_cd(uid, "weekly", WEEKLY_CD)
    if left > 0:
        return await interaction.response.send_message(
            f"✧ return later... {format_time(left)}",
            ephemeral=True
        )

    await interaction.response.defer()

    reward = random.randint(5000, 10000)
    cards_won = []

    # HIGH TIER
    c = await get_card_by_rarity(["eclipse", "velour"])
    if c: cards_won.append(c)

    # NORMALS
    for _ in range(6):
        c = await get_card_by_rarity(["siren","enthrall","devotion","whisper","cherub"])
        if c: cards_won.append(c)

    # UPDATE DB
    update = {"currency": reward}
    for c in cards_won:
        update[f"cards.{c['card_code']}"] = 1

    await users.update_one({"id": uid}, {"$inc": update}, upsert=True)

    await set_cooldown(uid, "weekly")

    await interaction.followup.send(
        f"✧ weekly fortune\n+{reward} {CURRENCY}\n+{len(cards_won)} cards"
    )
    
# =========================
# 🩸 MONTHLY
# =========================
@tree.command(name="monthly", description="✧ claim monthly fate")
async def monthly(interaction: discord.Interaction):

    uid = interaction.user.id

    left = await check_cd(uid, "monthly", MONTHLY_CD)
    if left > 0:
        return await interaction.response.send_message(
            f"✧ return later... {format_time(left)}",
            ephemeral=True
        )

    await interaction.response.defer()

    reward = random.randint(45000, 75000)
    cards_won = []

    # HIGH TIERS
    for _ in range(5):
        c = await get_card_by_rarity(["eclipse", "velour"])
        if c: cards_won.append(c)

    # DEVOTION
    for _ in range(10):
        c = await get_card_by_rarity(["devotion"])
        if c: cards_won.append(c)

    # ENTHRALL
    for _ in range(7):
        c = await get_card_by_rarity(["enthrall"])
        if c: cards_won.append(c)

    # LOW
    for _ in range(8):
        c = await get_card_by_rarity(["siren","cherub","whisper"])
        if c: cards_won.append(c)

    update = {"currency": reward}
    for c in cards_won:
        update[f"cards.{c['card_code']}"] = 1

    await users.update_one({"id": uid}, {"$inc": update}, upsert=True)

    await set_cooldown(uid, "monthly")

    await interaction.followup.send(
        f"✧ monthly fate\n+{reward} {CURRENCY}\n+{len(cards_won)} cards"
    )
    
# =========================
#  VIEW
# =========================
@tree.command(name="view", description="✧ view a card by code")
async def view(interaction: discord.Interaction, card_code: str):

    await interaction.response.defer()

    uid = interaction.user.id
    code = card_code.lower()

    # get card
    card = await cards.find_one({"card_code": code})
    if not card:
        return await interaction.followup.send("✧ card not found")

    # merge old + new schema
    d1 = await users.find_one({"id": uid}) or {}
    d2 = await users.find_one({"user_id": uid}) or {}

    owned = d1.get("cards", {}).get(code, 0) + d2.get("cards", {}).get(code, 0)

    # total copies in bot
    pipeline = [
        {"$project": {"count": f"$cards.{code}"}},
        {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$count", 0]}}}}
    ]

    res = await users.aggregate(pipeline).to_list(1)
    total = res[0]["total"] if res else 0

    # message
    await interaction.followup.send(
        f"✧ {interaction.user.mention} owns **{owned}** copies of this card"
    )

    # aesthetic embed
    e = discord.Embed(
        title=f"{card['name']} ✧",
        description=f"{card['group']} • {card['rarity']}",
        color=0x2b2d31
    )

    e.set_author(
        name=f"{interaction.user.name}'s archive",
        icon_url=interaction.user.display_avatar.url
    )

    e.add_field(name="✦ code", value=f"`{code}`", inline=True)
    e.add_field(name="✦ era", value=card.get("era", "—"), inline=True)
    e.add_field(name="✦ owned", value=str(owned), inline=True)

    e.set_image(url=card["image_url"])

    e.set_footer(text=f"{total} copies exist across the bot ✧")

    await interaction.followup.send(embed=e)
    
# =========================
# 🧬 COLLECTION + FALLEN
# =========================
@tree.command(name="collection", description="✧ view collection")
async def collection(interaction: discord.Interaction, group: str):

    await interaction.response.defer()

    uid = interaction.user.id
    user = await users.find_one({"user_id": uid}) or {"cards": {}}
    owned = user.get("cards", {})

    all_cards = await cards.find({
        "group": group.lower(),
        "rarity": {"$nin": ["fallen","sanctum"]}
    }).to_list(None)

    if not all_cards:
        return await interaction.followup.send("✧ nothing exists...")

    lines = []

    for c in all_cards:
        owned_flag = "✓" if owned.get(c["card_code"],0) > 0 else "✧"
        lines.append(
            f"{owned_flag} {c['name']} • {c['rarity']}"
        )

    pages = [lines[i:i+8] for i in range(0, len(lines), 8)]

    class ColView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=120)
            self.page = 0

        async def update(self, interaction):
            embed = discord.Embed(
                title=f"{group.title()} ✧ collection",
                description="\n".join(pages[self.page]),
                color=0x2b2d31
            )
            embed.set_footer(text=f"{self.page+1}/{len(pages)}")
            await interaction.response.edit_message(embed=embed, view=self)

        @discord.ui.button(label="◀")
        async def prev(self, interaction, button):
            if self.page > 0:
                self.page -= 1
            await self.update(interaction)

        @discord.ui.button(label="▶")
        async def next(self, interaction, button):
            if self.page < len(pages)-1:
                self.page += 1
            await self.update(interaction)

    embed = discord.Embed(
        title=f"{group.title()} ✧ collection",
        description="\n".join(pages[0]),
        color=0x2b2d31
    )

    await interaction.followup.send(embed=embed, view=ColView())
    
    # =====================
    # FALLEN UNLOCK
    # =====================

    if owned_count == total:

        fallen_cards = await cards.find({
            "group": group.lower(),
            "rarity": "fallen"
        }).to_list(None)

        new_cards = []
        for c in fallen_cards:
            if owned.get(c["card_code"], 0) == 0:
                new_cards.append(c)

        if new_cards:

            update = {}
            for c in new_cards:
                update[f"cards.{c['card_code']}"] = 1

            await users.update_one(
                {"id": uid},
                {"$inc": update}
            )

            await interaction.followup.send(
                f"🩸 {group.title()} complete — fallen cards awakened..."
            )



# ======================
# cooldown
# ======================          
@tree.command(name="cooldown", description="✧ view cooldowns")
async def cooldown(interaction: discord.Interaction, user: discord.Member = None):

    target = user or interaction.user
    uid = target.id

    await interaction.response.defer()

    drop_cd = await check_cd(uid, "drop", DROP_CD)
    claim_cd = await check_cd(uid, "claim", CLAIM_CD)
    daily_cd = await check_cd(uid, "daily", DAILY_CD)
    weekly_cd = await check_cd(uid, "weekly", WEEKLY_CD)
    monthly_cd = await check_cd(uid, "monthly", MONTHLY_CD)
    ttt_cd = await check_cd(uid, "ttt", 1800)

    embed = discord.Embed(
        title="✧ cooldowns",
        color=0x2b2d31
    )

    embed.set_author(
        name=target.name,
        icon_url=target.display_avatar.url
    )

    embed.add_field(name="claim", value=fmt(claim_cd), inline=True)
    embed.add_field(name="drop", value=fmt(drop_cd), inline=True)
    embed.add_field(name="daily", value=fmt(daily_cd), inline=True)
    embed.add_field(name="weekly", value=fmt(weekly_cd), inline=True)
    embed.add_field(name="monthly", value=fmt(monthly_cd), inline=True)
    embed.add_field(name="tic-tac-toe", value=fmt(ttt_cd), inline=True)

    embed.set_footer(text="✧ time bends, patience rewards")

    await interaction.followup.send(embed=embed)
    
# ======================
# GRANT
# ======================
@tree.command(name="grant", description="✧ bestow relics or cards (staff)")
async def grant(
    interaction: discord.Interaction,
    user: discord.Member,
    bot_currency: int = 0,
    code1: str = None, copies1: int = 0,
    code2: str = None, copies2: int = 0,
    code3: str = None, copies3: int = 0,
    code4: str = None, copies4: int = 0,
    code5: str = None, copies5: int = 0
):

    if not is_staff(interaction.user.id):
        return await interaction.response.send_message("✧ no permission", ephemeral=True)

    await interaction.response.defer()

    update = {}
    log_text = f"✧ {interaction.user} granted {user.mention}\n"

    # currency
    if bot_currency > 0:
        update["currency"] = bot_currency
        log_text += f"+{bot_currency} {CURRENCY}\n"

    # cards helper
    async def process(code, copies):
        if code and copies > 0:
            c = await cards.find_one({"card_code": code})
            if not c:
                return f"⚠ invalid code: {code}\n"
            update[f"cards.{code}"] = copies
            return f"+{copies} {c['name']} ({code})\n"
        return ""

    log_text += await process(code1, copies1)
    log_text += await process(code2, copies2)
    log_text += await process(code3, copies3)
    log_text += await process(code4, copies4)
    log_text += await process(code5, copies5)

    if not update:
        return await interaction.followup.send("✧ nothing to grant")

    await users.update_one(
        {"id": user.id},
        {"$inc": update},
        upsert=True
    )

    await interaction.followup.send("✧ granted successfully")
    await log(bot, log_text)

# ======================
# REVOKE
# ======================
@tree.command(name="revoke", description="✧ withdraw relics or cards (staff)")
async def revoke(
    interaction: discord.Interaction,
    user: discord.Member,
    bot_currency: int = 0,
    code1: str = None, copies1: int = 0,
    code2: str = None, copies2: int = 0,
    code3: str = None, copies3: int = 0,
    code4: str = None, copies4: int = 0,
    code5: str = None, copies5: int = 0
):

    if not is_staff(interaction.user.id):
        return await interaction.response.send_message("✧ no permission", ephemeral=True)

    await interaction.response.defer()

    user_data = await users.find_one({"id": user.id}) or {"cards": {}, "currency": 0}

    update = {}
    log_text = f"✧ {interaction.user} revoked from {user.mention}\n"

    # currency safe remove
    if bot_currency > 0:
        current = user_data.get("currency", 0)
        remove = min(bot_currency, current)
        if remove > 0:
            update["currency"] = -remove
            log_text += f"-{remove} {CURRENCY}\n"

    # cards helper
    async def process(code, copies):
        if code and copies > 0:
            current = user_data.get("cards", {}).get(code, 0)
            remove = min(copies, current)

            if remove > 0:
                c = await cards.find_one({"card_code": code})
                update[f"cards.{code}"] = -remove
                return f"-{remove} {c['name']} ({code})\n"
        return ""

    log_text += await process(code1, copies1)
    log_text += await process(code2, copies2)
    log_text += await process(code3, copies3)
    log_text += await process(code4, copies4)
    log_text += await process(code5, copies5)

    if not update:
        return await interaction.followup.send("✧ nothing to revoke")

    await users.update_one(
        {"id": user.id},
        {"$inc": update}
    )

    await interaction.followup.send("✧ revoked successfully")
    await log(bot, log_text)


# ======================
# favourite 
# ======================
@bot.tree.command(name="favourite", description="✧ set your favourites")
async def favourite(
    interaction: discord.Interaction,
    group: str = None,
    name: str = None,
    card_code: str = None
):

    if not group and not name and not card_code:
        # reset favourites
        await users.update_one(
            {"id": interaction.user.id},
            {"$unset": {"favourite": ""}},
            upsert=True
        )
        return await interaction.response.send_message("✧ favourites cleared")

    fav_data = {}

    if group:
        fav_data["group"] = group.lower()

    if name:
        fav_data["name"] = name.lower()

    if card_code:
        card = await cards.find_one({"card_code": card_code})
        if not card:
            return await interaction.response.send_message("✧ invalid card code")
        fav_data["card_code"] = card_code
        fav_data["image"] = card["image_url"]

    await users.update_one(
        {"id": interaction.user.id},
        {"$set": {"favourite": fav_data}},
        upsert=True
    )

    await interaction.response.send_message("✧ favourites updated")


# ======================
# profile
# ======================
@bot.tree.command(name="profile", description="✧ view your profile")
async def profile(interaction: discord.Interaction, user: discord.User = None):

    user = user or interaction.user
    data = await users.find_one({"id": user.id}) or {}

    cards_data = data.get("cards", {})
    relics = data.get("currency", 0)
    fav = data.get("favourite", {})

    total_cards = sum(cards_data.values())

    embed = discord.Embed(
        title=f"✧ {user.name}'s profile ✧",
        color=0x2b2d31
    )

    embed.add_field(name="✦ relics", value=f"{relics:,}", inline=True)
    embed.add_field(name="✦ total cards", value=str(total_cards), inline=True)

    # favourites
    fav_text = ""

    if fav.get("group"):
        fav_text += f"✧ group: {fav['group']}\n"
    if fav.get("name"):
        fav_text += f"✧ idol: {fav['name']}\n"

    embed.add_field(
        name="✦ favourites",
        value=fav_text if fav_text else "—",
        inline=False
    )

    if fav.get("image"):
        embed.set_image(url=fav["image"])

    embed.set_footer(text="✧ curated presence")

    await interaction.response.send_message(embed=embed)

# ======================
# tic-tac-toe 
# ======================
@bot.tree.command(name="tic-tac-toe", description="✧ play tic-tac-toe with Jimin or a user")
async def tic_tac_toe(interaction: discord.Interaction, opponent: discord.Member = None):

    uid = interaction.user.id
    opp_id = opponent.id if opponent else None

    data = await users.find_one({"id": uid}) or {}
    last_cd = data.get("ttt_cd", 0)

    # cooldown check
    if time.time() - last_cd < 1800:
        remaining = int(1800 - (time.time() - last_cd))
        return await interaction.response.send_message(
            f"✧ cooldown active: {remaining//60}m {remaining%60:02d}s",
            ephemeral=True
        )

    # defer FIRST (important)
    await interaction.response.defer()

    # ping message (NOT embed)
    if opponent:
        await interaction.followup.send(
            f"✧ {interaction.user.mention} vs {opponent.mention} — game starting..."
        )
    else:
        await interaction.followup.send("✧ starting game...")

    P1 = "🌺"
    P2 = "🌹"

    def check_win(b, p):
        wins = [(0,1,2),(3,4,5),(6,7,8),
                (0,3,6),(1,4,7),(2,5,8),
                (0,4,8),(2,4,6)]
        return any(all(b[i] == p for i in w) for w in wins)

    def bot_move(board):
        wins = [(0,1,2),(3,4,5),(6,7,8),
                (0,3,6),(1,4,7),(2,5,8),
                (0,4,8),(2,4,6)]

        # win
        for a,b,c in wins:
            line = [board[a],board[b],board[c]]
            if line.count(P2)==2 and line.count("")==1:
                for i in (a,b,c):
                    if board[i]=="":
                        board[i]=P2
                        return

        # block
        for a,b,c in wins:
            line = [board[a],board[b],board[c]]
            if line.count(P1)==2 and line.count("")==1:
                for i in (a,b,c):
                    if board[i]=="":
                        board[i]=P2
                        return

        # center
        if board[4]=="":
            board[4]=P2
            return

        # corners
        for i in [0,2,6,8]:
            if board[i]=="":
                board[i]=P2
                return

        # random
        empty=[i for i,v in enumerate(board) if v==""]
        if empty:
            board[random.choice(empty)] = P2

    total_wins = 0

    # ======================
    # 3 ROUNDS
    # ======================
    for round_no in range(1, 4):

        board = [""] * 9
        result = None

        # random starter
        if opponent:
            turn = random.choice([uid, opp_id])
        else:
            starter = random.choice(["player", "bot"])
            turn = uid
            if starter == "bot":
                bot_move(board)

        class GameView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60)
                self.update_buttons()

            def update_buttons(self):
                self.clear_items()

                for i in range(9):
                    btn = discord.ui.Button(
                        label=board[i] if board[i] else "⬛",
                        style=discord.ButtonStyle.secondary,
                        row=i // 3
                    )

                    async def callback(interaction: discord.Interaction, idx=i):
                        nonlocal result, turn, total_wins

                        # PvP checks
                        if opponent:
                            if interaction.user.id not in [uid, opp_id]:
                                return await interaction.response.send_message("✧ not your game", ephemeral=True)
                            if interaction.user.id != turn:
                                return await interaction.response.send_message("✧ not your turn", ephemeral=True)
                        else:
                            if interaction.user.id != uid:
                                return await interaction.response.send_message("✧ not your game", ephemeral=True)

                        if board[idx] != "":
                            return await interaction.response.defer()

                        # assign symbol
                        if opponent:
                            symbol = P1 if interaction.user.id == uid else P2
                        else:
                            symbol = P1

                        board[idx] = symbol

                        # check result
                        if check_win(board, symbol):
                            result = "win" if interaction.user.id == uid else "lose"
                            self.disable_all()

                        elif "" not in board:
                            result = "draw"
                            self.disable_all()

                        else:
                            if not opponent:
                                bot_move(board)

                                if check_win(board, P2):
                                    result = "lose"
                                    self.disable_all()
                                elif "" not in board:
                                    result = "draw"
                                    self.disable_all()
                            else:
                                turn = opp_id if turn == uid else uid

                        self.update_buttons()

                        embed = discord.Embed(
                            title=f"✧ TIC TAC TOE ✧ 〔ROUND {round_no}〕",
                            description=(
                                f"Turn: <@{turn}>"
                                if opponent and not result
                                else ("Your move" if not opponent and not result else "")
                            ),
                            color=0x2b2d31
                        )

                        await interaction.response.edit_message(embed=embed, view=self)

                        # rewards
                        if result == "win":
                            reward = random.randint(2000, 4000)
                            total_wins += 1

                            await users.update_one(
                                {"id": uid},
                                {"$inc": {"currency": reward}},
                                upsert=True
                            )

                            await interaction.followup.send(f"✧ round {round_no} win +{reward}")

                        elif result == "lose":
                            await interaction.followup.send(f"✧ round {round_no} lost")

                        elif result == "draw":
                            await interaction.followup.send(f"✧ round {round_no} draw")

                    btn.callback = callback
                    self.add_item(btn)

            def disable_all(self):
                for item in self.children:
                    item.disabled = True

        view = GameView()

        embed = discord.Embed(
            title=f"✧ TIC TAC TOE ✧ 〔ROUND {round_no}〕",
            description=(
                f"Turn: <@{turn}>"
                if opponent
                else ("Bot started" if 'starter' in locals() and starter == "bot" else "Your move")
            ),
            color=0x2b2d31
        )

        msg = await interaction.followup.send(embed=embed, view=view)

        # timeout system
        start_time = time.time()

        while result is None:
            await asyncio.sleep(1)

            if time.time() - start_time > 60:
                result = "timeout"
                view.disable_all()

                try:
                    await msg.edit(view=view)
                except:
                    pass

                await interaction.followup.send(
                    f"✧ game ended — <@{turn}> didn’t respond"
                )
                break

        await asyncio.sleep(2)

    # ======================
    # FINAL RESULT
    # ======================
    if total_wins > 0:
        await users.update_one(
            {"id": uid},
            {"$set": {"ttt_cd": time.time()}},
            upsert=True
        )

    if total_wins == 3:
        bonus = 10000
        await users.update_one(
            {"id": uid},
            {"$inc": {"currency": bonus}},
            upsert=True
        )
        await interaction.followup.send(f"🔥 PERFECT GAME +{bonus} RELICS")

    elif total_wins > 0:
        await interaction.followup.send("✧ game finished — cooldown applied")

    else:
        await interaction.followup.send("✧ no wins — you can play again immediately")


# ======================
# search 
# ======================
@tree.command(name="search", description="✧ search for cards in the bot")
@app_commands.describe(
    name="filter by idol name",
    group="filter by group",
    rarity="filter by rarity",
    era="filter by era"
)
@app_commands.choices(rarity=RARITY_CHOICES)
async def search(
    interaction: discord.Interaction,
    name: str = None,
    group: str = None,
    rarity: app_commands.Choice[str] = None,
    era: str = None
):
    await interaction.response.defer()

    # ======================
    # BUILD QUERY
    # ======================
    query = {}

    if name:
        query["name"] = {"$regex": name, "$options": "i"}

    if group:
        query["group"] = {"$regex": group, "$options": "i"}

    if rarity:
        query["rarity"] = rarity.value

    if era:
        query["era"] = {"$regex": era, "$options": "i"}

    results = await cards.find(query).to_list(None)

    if not results:
        return await interaction.followup.send("✧ no cards found")

    # ======================
    # FORMAT RESULTS
    # ======================
    lines = []
    for c in results:
        emoji = rarity_emoji(c["rarity"])

        lines.append(
            f"{emoji} **{c['group']}** ⟡ {c['name']}\n"
            f"〔{c['rarity']}〕 • `{c['card_code']}` • {c.get('era','—')}"
        )

    lines.sort(key=lambda x: x.lower())
    pages = [lines[i:i+6] for i in range(0, len(lines), 6)]

    # ======================
    # VIEW
    # ======================
    class SearchView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=120)
            self.page = 0

        async def update(self, interaction):
            embed = discord.Embed(
                description="\n\n".join(pages[self.page]),
                color=0x2b2d31
            )
            embed.set_author(name="✧ card search")
            embed.set_footer(
                text=f"{self.page+1}/{len(pages)} • {len(results)} results"
            )
            await interaction.response.edit_message(embed=embed, view=self)

        @discord.ui.button(label="◀")
        async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
            if self.page > 0:
                self.page -= 1
            await self.update(interaction)

        @discord.ui.button(label="▶")
        async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
            if self.page < len(pages) - 1:
                self.page += 1
            await self.update(interaction)

        @discord.ui.button(label="Preview")
        async def preview(self, interaction: discord.Interaction, button: discord.ui.Button):
            page_cards = results[self.page*6:(self.page+1)*6]

            if not page_cards:
                return await interaction.response.send_message(
                    "✧ nothing to preview", ephemeral=True
                )

            card = page_cards[0]  # first card in page

            e = discord.Embed(
                title=card["name"],
                description=f"{card['group']} • {card['rarity']}",
                color=0x2b2d31
            )
            e.set_image(url=card["image_url"])

            await interaction.response.send_message(embed=e, ephemeral=True)

    # ======================
    # FIRST PAGE
    # ======================
    embed = discord.Embed(
        description="\n\n".join(pages[0]),
        color=0x2b2d31
    )
    embed.set_author(name="✧ card search")
    embed.set_footer(text=f"1/{len(pages)} • {len(results)} results")

    await interaction.followup.send(embed=embed, view=SearchView())
    
# ======================
# reset cooldowns 
# ======================
@bot.tree.command(name="reset_cooldown", description="✧ reset cooldowns (staff only)")
@app_commands.describe(
    user="user to reset",
    daily="reset daily cooldown",
    weekly="reset weekly cooldown",
    monthly="reset monthly cooldown",
    tic_tac_toe="reset tic tac toe cooldown"
)
async def reset_cooldown(
    interaction: discord.Interaction,
    user: discord.Member,
    daily: bool = False,
    weekly: bool = False,
    monthly: bool = False,
    tic_tac_toe: bool = False
):

    # ✅ STAFF CHECK
    if interaction.user.id not in STAFF_IDS:
        return await interaction.response.send_message("✧ no permission", ephemeral=True)

    await interaction.response.defer()

    updates = {}
    reset_list = []

    # ======================
    # SELECTIVE RESET
    # ======================

    if daily:
        updates["daily_cd"] = 0
        reset_list.append("daily")

    if weekly:
        updates["weekly_cd"] = 0
        reset_list.append("weekly")

    if monthly:
        updates["monthly_cd"] = 0
        reset_list.append("monthly")

    if tic_tac_toe:
        updates["ttt_cd"] = 0
        reset_list.append("tic-tac-toe")

    # ======================
    # IF NOTHING SELECTED → RESET ALL
    # ======================

    if not updates:
        updates = {
            "daily_cd": 0,
            "weekly_cd": 0,
            "monthly_cd": 0,
            "ttt_cd": 0
        }
        reset_list = ["daily", "weekly", "monthly", "tic-tac-toe"]

    # ======================
    # APPLY UPDATE
    # ======================

    await users.update_one(
        {"id": user.id},
        {"$set": updates},
        upsert=True
    )

    # ======================
    # RESPONSE
    # ======================

    await interaction.followup.send(
        f"✧ reset {', '.join(reset_list)} cooldown(s) for {user.mention}"
                 )
    
print("TOKEN:", TOKEN)
print("MONGO:", MONGO)

# ======================
# READY
# ======================

@bot.event
async def on_ready():
    print(f"LOGGED IN AS {bot.user}")

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print("Sync error:", e)
        await bot.tree.sync()
        
import threading
from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "alive"

def run():
    app.run(host="0.0.0.0", port=10000)

def keep_alive():
    t = threading.Thread(target=run)
    t.start()
    
keep_alive()

if __name__ == "__main__":
    bot.run(TOKEN)
    
