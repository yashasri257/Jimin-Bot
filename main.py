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

    
# ======================
# GET CARD (FAST + SAFE)
# ======================

async def get_card():
    for _ in range(5):
        rarity = random.choices(
            ["whisper","cherub","siren","enthrall","devotion"],
            weights=[40,30,15,10,5]
        )[0]

        res = await cards.aggregate([
            {"$match":{"rarity":rarity,"droppable":True}},
            {"$sample":{"size":1}}
        ]).to_list(1)

        if res:
            return res[0]

    return None

# ======================
# ADD CARD
# ======================

@tree.command(name="add_card", description="✧ add a new card (staff)")
async def add_card(interaction: discord.Interaction,
    name: str, group: str, rarity: str,
    card_code: str, image_url: str,
    droppable: bool, rarity_back: str = None, era: str = None):

    if not is_staff(interaction.user.id):
        return await interaction.response.send_message("✧ no permission", ephemeral=True)

    await cards.insert_one({
        "name": name,
        "group": group.lower(),
        "rarity": rarity.lower(),
        "card_code": card_code.lower(),
        "image_url": image_url,
        "droppable": droppable,
        "rarity_back": rarity_back,
        "era": era
    })

    await interaction.response.send_message("✧ card added")
        
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
async def inventory(
    interaction: discord.Interaction,
    user: discord.Member=None,
    name: str=None,
    group: str=None,
    rarity: str=None,
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
        query["rarity"] = rarity.lower()
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

        lines.append(
            f"✦ **{c['group']}** ⟡ {c['name']}\n"
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

    await interaction.response.defer()

    uid = interaction.user.id

    left = await check_cd(uid, "weekly", WEEKLY_CD)
    if left > 0:
        return await interaction.followup.send(
            f"✧ return later... {format_time(left)}"
        )

    await set_cooldown(uid, "weekly")

    reward = random.randint(1500, 5000)

    cards_won = []
    for _ in range(7):
        c = await get_card()
        if c:
            cards_won.append(c)

    update = {"currency": reward}
    for c in cards_won:
        update[f"cards.{c['card_code']}"] = 1

    await users.update_one({"id": uid}, {"$inc": update}, upsert=True)

    await interaction.followup.send(
        f"✧ weekly fortune\n+{reward} {CURRENCY}\n+{len(cards_won)} cards"
    )

# =========================
# 🩸 MONTHLY
# =========================

@tree.command(name="monthly", description="✧ claim monthly fate")
async def monthly(interaction: discord.Interaction):

    await interaction.response.defer()

    uid = interaction.user.id

    left = await check_cd(uid, "monthly", MONTHLY_CD)
    if left > 0:
        return await interaction.followup.send(
            f"✧ return later... {format_time(left)}"
        )

    await set_cooldown(uid, "monthly")

    reward = random.randint(10000, 25000)

    cards_won = []
    for _ in range(25):
        c = await get_card()
        if c:
            cards_won.append(c)

    update = {"currency": reward}
    for c in cards_won:
        update[f"cards.{c['card_code']}"] = 1

    await users.update_one({"id": uid}, {"$inc": update}, upsert=True)

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
    
