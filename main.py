print("RUNNING NEW FILE")
import discord
from discord.ext import commands
from discord import app_commands
import os, random, time
from motor.motor_asyncio import AsyncIOMotorClient
from PIL import Image
from io import BytesIO
import aiohttp

TOKEN = os.getenv("TOKEN")
MONGO = os.getenv("MONGO")

bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
tree = bot.tree

mongo = AsyncIOMotorClient(MONGO)
db = mongo["kpop"]
cards = db["cards"]
users = db["users"]

# ======================
# 🔒 STAFF
# ======================
STAFF_IDS = [871159389799743488
            1106193228971122689
863994605493682206
701968449462599752
702667135775801376]
def is_staff(uid):
    return uid in STAFF_IDS

# ======================
# 💎 CONFIG
# ======================
DROP_COOLDOWN = 300
CLAIM_COOLDOWN = 120
DAILY_COOLDOWN = 79200

last_drop = {}
last_claim = {}

CURRENCY = "Essence"

# ======================
# ✨ RARITIES
# ======================
RARITIES = ["whisper","cherub","siren","enthrall","devotion","fallen","eclipse","velour","sanctum"]

RARITY_CHOICES = [app_commands.Choice(name=r.title(), value=r) for r in RARITIES]

RARITY_ICONS = {
    "whisper":"⋆","cherub":"✧","siren":"✦",
    "enthrall":"❖","devotion":"✿",
    "fallen":"🩸","eclipse":"☾","velour":"♛","sanctum":"✶"
}

# ======================
# 🎴 DROP CHANCES
# ======================
def get_chances():
    mode=random.random()
    if mode<0.1:
        return {"whisper":30,"cherub":25,"siren":17,"enthrall":12,"devotion":8,"eclipse":5,"velour":3}
    elif mode<0.3:
        return {"whisper":30,"cherub":25,"siren":20,"enthrall":12,"devotion":8,"eclipse":5}
    elif mode<0.5:
        return {"whisper":30,"cherub":25,"siren":20,"enthrall":12,"devotion":9,"velour":4}
    else:
        return {"whisper":35,"cherub":30,"siren":20,"enthrall":10,"devotion":5}

async def get_card():
    chances=get_chances()
    rarity=random.choices(list(chances),list(chances.values()))[0]

    res=await cards.aggregate([
        {"$match":{"rarity":rarity,"droppable":True}},
        {"$sample":{"size":1}}
    ]).to_list(1)

    return res[0] if res else None

# ======================
# 🎴 RARITY BACK SYSTEM
# ======================
async def get_back(card):
    if card.get("rarity_back"):
        return card["rarity_back"]

    query={
        "group":card["group"],
        "rarity":card["rarity"],
        "rarity_back":{"$ne":None}
    }

    if card.get("era"):
        query["era"]=card["era"]

    other=await cards.find_one(query)

    if other:
        return other["rarity_back"]

    return card["image_url"]

# ======================
# 🖼 MERGE
# ======================
async def merge(urls):
    async with aiohttp.ClientSession() as session:
        imgs=[]
        for url in urls:
            async with session.get(url) as r:
                data=await r.read()
                imgs.append(Image.open(BytesIO(data)).resize((300,420)))

    canvas=Image.new("RGBA
RARITIES = [
    "whisper", "cherub", "siren",
    "enthrall", "devotion",
    "fallen", "eclipse", "velour", "sanctum"
]

RARITY_CHOICES = [
    discord.app_commands.Choice(name=r.title(), value=r)
    for r in RARITIES
]

RARITY_ICONS = {
    "whisper": "🌫️",
    "cherub": "👼",
    "siren": "🧜‍♀️",
    "enthrall": "🖤",
    "devotion": "💖",
    "fallen": "🩸",
    "eclipse": "🌑",
    "velour": "💜",
    "sanctum": "✨"
}

# ======================
# CARD ADD
# ======================

@tree.command(name="add_card")
@app_commands.choices(rarity=RARITY_CHOICES)
async def add_card(
    interaction: discord.Interaction,
    name: str,
    group: str,
    rarity: app_commands.Choice[str],
    card_code: str,
    image_url: str,
    back_url: str,
    droppable: bool,
    era: str = None
):

    await cards.insert_one({
        "name": name,
        "group": group,
        "rarity": rarity.value,
        "card_code": card_code,
        "image_url": image_url,
        "back_url": back_url,
        "droppable": droppable,
        "era": era
    })

    await interaction.response.send_message("Card added ✅")

# ======================
# DELETE CARD
# ======================

@tree.command(name="del_card")
async def del_card(interaction: discord.Interaction, card_code: str):
    await cards.delete_one({"card_code": card_code})
    await interaction.response.send_message("Deleted")

# ======================
# DROP SYSTEM
# ======================

def get_base():
    return {
        "whisper": 40,
        "cherub": 30,
        "siren": 15,
        "enthrall": 10,
        "devotion": 5,
        "fallen": 0,
        "eclipse": 0,
        "velour": 0,
        "sanctum": 0
    }

async def get_card(uid):
    chances = get_base()
    rarity = random.choices(list(chances), list(chances.values()))[0]

    res = await cards.aggregate([
        {"$match": {"rarity": rarity, "droppable": True}},
        {"$sample": {"size": 1}}
    ]).to_list(1)

    return res[0]

# ======================
# IMAGE MERGE (SAFE)
# ======================

async def merge(urls):
    async with aiohttp.ClientSession() as session:
        imgs = []

        for url in urls:
            async with session.get(url) as r:
                data = await r.read()
                img = Image.open(BytesIO(data)).resize((300, 420))
                imgs.append(img)

    canvas = Image.new("RGBA", (900, 420))

    for i, img in enumerate(imgs):
        canvas.paste(img, (i * 300, 0))

    buf = BytesIO()
    canvas.save(buf, "PNG")
    buf.seek(0)
    return buf

# ======================
# DROP VIEW
# ======================

class DropView(discord.ui.View):
    def __init__(self, cards_list):
        super().__init__(timeout=60)
        self.cards = cards_list
        self.claimed = [False, False, False]

    async def handle(self, interaction, idx):

        if self.claimed[idx]:
            await interaction.response.send_message("Already taken", ephemeral=True)
            return

        self.claimed[idx] = True
        card = self.cards[idx]

        await users.update_one(
            {"id": interaction.user.id},
            {"$inc": {f"cards.{card['card_code']}": 1}},
            upsert=True
        )

        self.children[idx].disabled = True

        await interaction.response.defer()
        await interaction.message.edit(view=self)

        icon = RARITY_ICONS.get(card["rarity"], "")
        embed = discord.Embed(
            title=f"{icon} {card['name']}",
            description=card["rarity"]
        )
        embed.set_image(url=card["image_url"])

        await interaction.followup.send(embed=embed)

    @discord.ui.button(label="1")
    async def b1(self, i, b): await self.handle(i, 0)

    @discord.ui.button(label="2")
    async def b2(self, i, b): await self.handle(i, 1)

    @discord.ui.button(label="3")
    async def b3(self, i, b): await self.handle(i, 2)

# ======================
# DROP COMMAND
# ======================

@tree.command(name="drop")
async def drop(interaction: discord.Interaction):

    chosen = [await get_card(interaction.user.id) for _ in range(3)]
    backs = [c["back_url"] for c in chosen]

    img = await merge(backs)
    file = discord.File(img, "drop.png")

    embed = discord.Embed(title="✧ ethereal drop ✧")

    for i, c in enumerate(chosen, 1):
        icon = RARITY_ICONS.get(c["rarity"], "")
        embed.add_field(name=f"{i}. {icon} {c['rarity']}", value=c["group"])

    embed.set_image(url="attachment://drop.png")

    await interaction.response.send_message(
        embed=embed,
        file=file,
        view=DropView(chosen)
    )

# ======================
# VIEW COMMAND
# ======================

@tree.command(name="view")
async def view(interaction: discord.Interaction, card_code: str):

    c = await cards.find_one({"card_code": card_code})
    u = await users.find_one({"id": interaction.user.id})

    count = u.get("cards", {}).get(card_code, 0) if u else 0

    icon = RARITY_ICONS.get(c["rarity"], "")

    embed = discord.Embed(title=f"{icon} {c['name']}")
    embed.add_field(name="Group", value=c["group"])
    embed.add_field(name="Rarity", value=c["rarity"])
    embed.add_field(name="Era", value=c.get("era", "None"))
    embed.set_image(url=c["image_url"])

    await interaction.response.send_message(
        f"You own {count} copies",
        embed=embed
    )

# ======================
# INVENTORY
# ======================

@tree.command(name="inventory")
async def inventory(interaction: discord.Interaction):

    u = await users.find_one({"id": interaction.user.id})

    if not u:
        await interaction.response.send_message("Empty")
        return

    text = ""
    for code, count in u.get("cards", {}).items():
        c = await cards.find_one({"card_code": code})
        if c:
            icon = RARITY_ICONS.get(c["rarity"], "")
            text += f"{icon} {c['name']} x{count}\n"

    await interaction.response.send_message(text[:2000])

# ======================
# READY
# ======================

@bot.event
async def on_ready():
    await tree.sync()
    print("READY")

# ======================
# RUN
# ======================

bot.run(TOKEN)
