import discord
from discord.ext import commands
from discord import app_commands
import os, random, time, asyncio
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
STAFF_IDS = [
    1106193228971122689,
    702667135775801376,
    701969588157415506,
    701968449462599752,
    871159389799743488
]

def is_staff(uid):
    return uid in STAFF_IDS

# ======================
# 💎 CONFIG
# ======================
DROP_CD = 300
CLAIM_CD = 120
DAILY_CD = 79200
CURRENCY = "Relics"  # you can change later

last_drop = {}
last_claim = {}

# ======================
# ✨ RARITIES
# ======================
RARITIES = ["whisper","cherub","siren","enthrall","devotion","fallen","eclipse","velour","sanctum"]
RARITY_CHOICES = [app_commands.Choice(name=r.title(), value=r) for r in RARITIES]

# ======================
# 🎴 DROP CHANCES
# ======================
def get_chances():
    r = random.random()
    if r < 0.1:
        return {"whisper":30,"cherub":25,"siren":17,"enthrall":12,"devotion":8,"eclipse":5,"velour":3}
    elif r < 0.3:
        return {"whisper":30,"cherub":25,"siren":20,"enthrall":12,"devotion":8,"eclipse":5}
    elif r < 0.5:
        return {"whisper":30,"cherub":25,"siren":20,"enthrall":12,"devotion":9,"velour":4}
    else:
        return {"whisper":35,"cherub":30,"siren":20,"enthrall":10,"devotion":5}

async def get_card():
    for _ in range(10):  # try multiple times
        chances = get_chances()
        rarity = random.choices(list(chances), list(chances.values()))[0]

        res = await cards.aggregate([
            {"$match":{"rarity":rarity,"droppable":True}},
            {"$sample":{"size":1}}
        ]).to_list(1)

        if res:
            return res[0]

    return None
# ======================
# 🎴 BACK SYSTEM
# ======================
async def get_back(card):
    if card.get("rarity_back"):
        return card["rarity_back"]

    other = await cards.find_one({
        "group": card["group"],
        "rarity": card["rarity"],
        "rarity_back": {"$ne": None}
    })

    return other["rarity_back"] if other else card["image_url"]

# ======================
# 🖼 MERGE
# ======================
async def merge(urls):
    async with aiohttp.ClientSession() as session:
        imgs = []
        for url in urls:
            async with session.get(url) as r:
                data = await r.read()
                imgs.append(Image.open(BytesIO(data)).resize((300,420)))

    canvas = Image.new("RGBA",(900,420))
    for i,img in enumerate(imgs):
        canvas.paste(img,(i*300,0))

    buf = BytesIO()
    canvas.save(buf,"PNG")
    buf.seek(0)
    return buf

# ======================
# 🔒 ADD CARD
# ======================
@tree.command(name="add_card", description="Add a card (staff)")
@app_commands.choices(rarity=RARITY_CHOICES)
async def add_card(interaction: discord.Interaction,
                   name:str, group:str,
                   rarity: app_commands.Choice[str],
                   card_code:str,
                   image_url:str,
                   droppable:bool,
                   era:str=None,
                   rarity_back:str=None):

    if not is_staff(interaction.user.id):
        return

    await cards.insert_one({
        "name":name,
        "group":group.lower(),
        "rarity":rarity.value,
        "card_code":card_code,
        "image_url":image_url,
        "droppable":droppable,
        "era":era,
        "rarity_back":rarity_back
    })

    await interaction.response.send_message("✧ card added to archive")

# ======================
# ❌ DELETE
# ======================
@tree.command(name="del_card")
async def del_card(interaction:discord.Interaction, card_code:str):

    if not is_staff(interaction.user.id):
        return

    await cards.delete_one({"card_code":card_code})
    await interaction.response.send_message("✧ card removed")

# ======================
# 🎁 STAFF COMMAND
# ======================
@tree.command(name="grant")
async def grant(interaction:discord.Interaction,
                user:discord.User,
                card_code:str=None,
                amount:int=0,
                currency:int=0):

    if not is_staff(interaction.user.id):
        return

    if card_code:
        await users.update_one(
            {"id":user.id},
            {"$inc":{f"cards.{card_code}":amount}},
            upsert=True
        )

    if currency:
        await users.update_one(
            {"id":user.id},
            {"$inc":{"currency":currency}},
            upsert=True
        )

    await interaction.response.send_message("✧ updated")

# ======================
# 🎴 DROP VIEW
# ======================
class DropView(discord.ui.View):
    def __init__(self, cards_list):
        super().__init__(timeout=60)
        self.cards = cards_list
        self.claimed = [False]*3

    async def handle(self, interaction, idx):
        uid = interaction.user.id
        now = time.time()

        # claim cooldown
        last = last_claim.get(uid, 0)
        if now - last < CLAIM_CD:
            await interaction.response.send_message(
                "✧ the magic hasn't settled yet... wait a moment",
                ephemeral=True
            )
            return

        if self.claimed[idx]:
            await interaction.response.send_message(
                "✧ this card has already been taken",
                ephemeral=True
            )
            return

        self.claimed[idx] = True
        last_claim[uid] = now

        card = self.cards[idx]

        # give card
        await users.update_one(
            {"id": uid},
            {"$inc": {f"cards.{card['card_code']}": 1}},
            upsert=True
        )

        # disable button
        self.children[idx].disabled = True
        await interaction.response.edit_message(view=self)

        # suspense message
        await interaction.followup.send("✧ the card begins to reveal itself...")

        await asyncio.sleep(20)

        # reveal
        embed = discord.Embed(
            title=f"{card['name']}",
            description=f"{card['group']} • {card['rarity']}",
            color=0x2b2d31
        )
        embed.add_field(name="Code", value=card["card_code"])
        embed.add_field(name="Era", value=card.get("era", "—"))
        embed.set_image(url=card["image_url"])

        await interaction.followup.send(embed=embed)

    @discord.ui.button(label="1")
    async def b1(self, interaction, button):
        await self.handle(interaction, 0)

    @discord.ui.button(label="2")
    async def b2(self, interaction, button):
        await self.handle(interaction, 1)

    @discord.ui.button(label="3")
    async def b3(self, interaction, button):
        await self.handle(interaction, 2)


# ======================
# 🎴 DROP COMMAND
# ======================
@tree.command(name="drop", description="✧ summon cards")
async def drop(interaction: discord.Interaction):

    await interaction.response.defer()  # 🔥 fixes timeout

    uid = interaction.user.id
    now = time.time()

    # cooldown check
    last = last_drop.get(uid, 0)
    if now - last < DROP_CD:
        await interaction.followup.send(
            f"✧ return later... ({int(DROP_CD - (now - last))}s)",
            ephemeral=True
        )
        return

    last_drop[uid] = now

    # get cards
    chosen = [await get_card() for _ in range(3)]

    if None in chosen:
        await interaction.followup.send("✧ no cards available yet")
        return

    # get rarity backs
    backs = [await get_back(c) for c in chosen]
    img = await merge(backs)

    file = discord.File(img, "drop.png")

    # embed
    embed = discord.Embed(
        title="✧ ethereal descent ✧",
        description="three unseen cards descend...\nchoose one before it fades",
        color=0x2b2d31
    )

    for i, c in enumerate(chosen, 1):
        embed.add_field(
            name=f"{i}. {c['rarity'].title()}",
            value=f"{c['group']}",
            inline=False
        )

    await interaction.followup.send(
        embed=embed,
        file=file,
        view=DropView(chosen)
    )
# ======================
# 🎁 DAILY
# ======================
@tree.command(name="daily")
async def daily(interaction:discord.Interaction):

    uid = interaction.user.id
    user = await users.find_one({"id":uid})
    now = int(time.time())

    if user and user.get("last_daily") and now-user["last_daily"] < DAILY_CD:
        await interaction.response.send_message("✧ already claimed", ephemeral=True)
        return

    card = await get_card()

    await users.update_one(
        {"id":uid},
        {"$set":{"last_daily":now},
         "$inc":{"currency":50, f"cards.{card['card_code']}":1}},
        upsert=True
    )

    embed = discord.Embed(
        title="✧ daily blessing ✧",
        description=f"+50 {CURRENCY}\n{card['name']}",
        color=0x2b2d31
    )
    embed.set_image(url=card["image_url"])

    await interaction.response.send_message(embed=embed)

# ======================
# 🔍 VIEW
# ======================
@tree.command(name="view")
async def view(interaction:discord.Interaction, card_code:str):

    c = await cards.find_one({"card_code":card_code})
    u = await users.find_one({"id":interaction.user.id})

    count = u.get("cards",{}).get(card_code,0) if u else 0

    embed = discord.Embed(
        title=c["name"],
        description=f"{interaction.user.name} owns {count} copies",
        color=0x2b2d31
    )
    embed.add_field(name="Group", value=c["group"])
    embed.add_field(name="Rarity", value=c["rarity"])
    embed.add_field(name="Era", value=c.get("era","—"))
    embed.set_image(url=c["image_url"])

    await interaction.response.send_message(embed=embed)

# ======================
# READY
# ======================
@bot.event
async def on_ready():
    await tree.sync()
    print("READY")

bot.run(TOKEN)
