import discord
from discord.ext import commands
from discord import app_commands
import os, random
from motor.motor_asyncio import AsyncIOMotorClient
from PIL import Image
from io import BytesIO
import aiohttp

# ======================
# CONFIG
# ======================

TOKEN = os.getenv("TOKEN")
MONGO = os.getenv("MONGO")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

mongo_client = AsyncIOMotorClient(MONGO)
db = mongo_client["kpop"]
cards = db["cards"]
users = db["users"]

RARITIES = [
    "Whisper", "Cherub", "Siren", "Enthrall",
    "Devotion", "Fallen", "Eclipse", "Velour", "Sanctum"
]

# ======================
# RARITY CHOICES (IMPORTANT)
# ======================

RARITY_CHOICES = [
    discord.app_commands.Choice(name=r, value=r.lower())
    for r in RARITIES
]

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
    await interaction.response.send_message("Deleted 🗑️")

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

async def apply_target(uid, chances):
    u = await users.find_one({"id": uid})
    if not u or not u.get("target"):
        return chances

    r = u["target"].get("rarity")

    if r == "whisper": chances["whisper"] += 5; chances["cherub"] -= 5
    elif r == "cherub": chances["cherub"] += 5; chances["whisper"] -= 5
    elif r == "siren": chances["siren"] += 5
    elif r == "enthrall": chances["enthrall"] += 5
    elif r == "devotion": chances["devotion"] += 3

    return chances

async def get_card(uid):
    chances = await apply_target(uid, get_base())
    rarity = random.choices(list(chances), weights=list(chances.values()))[0]

    res = await cards.aggregate([
        {"$match": {"rarity": rarity, "droppable": True}},
        {"$sample": {"size": 1}}
    ]).to_list(1)

    return res[0]

# ======================
# IMAGE MERGE (ASYNC FIXED)
# ======================

async def merge(urls):
    async with aiohttp.ClientSession() as session:
        imgs = []

        for u in urls:
            async with session.get(u) as resp:
                data = await resp.read()
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
# FALLEN CHECK
# ======================

async def check_fallen(user_id, group):

    user = await users.find_one({"id": user_id})
    owned = set(user.get("cards", {}).keys())

    required = await cards.find({
        "group": group,
        "rarity": {"$nin": ["fallen", "sanctum"]}
    }).to_list(None)

    required_codes = set(c["card_code"] for c in required)

    if not required_codes.issubset(owned):
        return False

    fallen_cards = await cards.find({
        "group": group,
        "rarity": "fallen"
    }).to_list(None)

    for c in fallen_cards:
        await users.update_one(
            {"id": user_id},
            {"$inc": {f"cards.{c['card_code']}": 1}},
            upsert=True
        )

    return True

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
            await interaction.response.send_message("Already taken ❌", ephemeral=True)
            return

        self.claimed[idx] = True
        card = self.cards[idx]

        await users.update_one(
            {"id": interaction.user.id},
            {"$inc": {f"cards.{card['card_code']}": 1}},
            upsert=True
        )

        unlocked = await check_fallen(interaction.user.id, card["group"])

        self.children[idx].disabled = True

        await interaction.response.defer()
        await interaction.message.edit(view=self)

        embed = discord.Embed(
            title=card["name"],
            description=card["rarity"]
        )
        embed.set_image(url=card["image_url"])

        await interaction.followup.send(embed=embed)

        if unlocked:
            await interaction.followup.send(
                f"🩸 Fallen set unlocked for **{card['group']}**!"
            )

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
        embed.add_field(name=str(i), value=c["group"])

    embed.set_image(url="attachment://drop.png")

    await interaction.response.send_message(
        embed=embed,
        file=file,
        view=DropView(chosen)
    )

# ======================
# VIEW CARD
# ======================

@tree.command(name="view")
async def view(interaction: discord.Interaction, card_code: str):

    c = await cards.find_one({"card_code": card_code})
    u = await users.find_one({"id": interaction.user.id})

    count = u.get("cards", {}).get(card_code, 0) if u else 0

    embed = discord.Embed(title=c["name"])
    embed.add_field(name="Group", value=c["group"])
    embed.add_field(name="Rarity", value=c["rarity"])
    embed.add_field(name="Code", value=c["card_code"])
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
            text += f"{c['name']} x{count}\n"

    await interaction.response.send_message(text[:2000])

# ======================
# READY EVENT
# ======================

@bot.event
async def on_ready():
    try:
        synced = await tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(e)

    print("READY")

# ======================
# RUN BOT
# ======================

bot.run(TOKEN)    "sanctum":"https://ibb.co/BKBQFq5z"}

EMOJIS = [
    "https://ibb.co/Xr66LPGn",
    "https://ibb.co/qMbF7wfm",
    "https://ibb.co/9mdzC5CP"
]

RARITY_CHOICES = [
    discord.app_commands.Choice(name=r, value=r)
    for r in RARITIES
]

# ======================
# CARD SYSTEM
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


@tree.command(name="del_card")
async def del_card(interaction: discord.Interaction, card_code: str):
    await cards.delete_one({"card_code": card_code})
    await interaction.response.send_message("Deleted 🗑️")

# ======================
# DROP SYSTEM
# ======================

def get_base():
    return {
        "whisper": 40,
        "cherub": 30,
        "sasync def add_card(interaction:discord.Interaction,
                   name:str, group:str,
                   rarity:str,
                   card_code:str,
                   image_url:str,
                   back_url:str,
                   droppable:bool,
                   era:str=None):

    await cards.insert_one({
        "name":name,
        "group":group,
        "rarity":rarity.lower(),
        "card_code":card_code,
        "image_url":image_url,
        "back_url":back_url,
        "droppable":droppable,
        "era":era
    })

    await interaction.response.send_message("Card added")

# ❌ DELETE
@bot.tree.command(name="del_card")
async def del_card(interaction:discord.Interaction,card_code:str):
    await cards.delete_one({"card_code":card_code})
    await interaction.response.send_message("Deleted")

# 🎲 BASE DROP
def get_base():
    return {"whisper":40,"cherub":30,"siren":15,"enthrall":10,"devotion":5}

# 🎯 TARGET
async def apply_target(uid,chances):
    u=await users.find_one({"id":uid})
    if not u or not u.get("target"): return chances

    r=u["target"].get("rarity")

    if r=="whisper": chances["whisper"]+=5; chances["cherub"]-=5
    elif r=="cherub": chances["cherub"]+=5; chances["whisper"]-=5
    elif r=="siren": chances["siren"]+=5; chances["whisper"]-=3; chances["cherub"]-=2
    elif r=="enthrall": chances["enthrall"]+=5; chances["whisper"]-=5
    elif r=="devotion": chances["devotion"]+=3; chances["siren"]-=3

    return chances

# 🎴 GET CARD
async def get_card(uid):
    chances = await apply_target(uid,get_base())
    rarity = random.choices(list(chances),weights=list(chances.values()))[0]

    res = await cards.aggregate([
        {"$match":{"rarity":rarity,"droppable":True}},
        {"$sample":{"size":1}}
    ]).to_list(1)

    return res[0]

# 🖼 MERGE
def merge(urls):
    imgs=[Image.open(BytesIO(requests.get(u).content)).resize((300,420)) for u in urls]
    canvas=Image.new("RGBA",(900,420))
    for i,img in enumerate(imgs):
        canvas.paste(img,(i*300,0))
    buf=BytesIO()
    canvas.save(buf,"PNG")
    buf.seek(0)
    return buf

# 🩸 FALLEN CHECK
async def check_fallen(user_id, group):

    user = await users.find_one({"id":user_id})

    owned_codes = set(user.get("cards",{}).keys())

    # all required cards
    required = await cards.find({
        "group":group,
        "rarity":{"$nin":["fallen","sanctum"]}
    }).to_list(None)

    required_codes = set(c["card_code"] for c in required)

    if not required_codes.issubset(owned_codes):
        return False

    # give fallen cards
    fallen_cards = await cards.find({
        "group":group,
        "rarity":"fallen"
    }).to_list(None)

    for c in fallen_cards:
        await users.update_one(
            {"id":user_id},
            {"$inc":{f"cards.{c['card_code']}":1}}
        )

    return True

# 🎴 DROP VIEW
class DropView(discord.ui.View):
    def __init__(self,cards_list):
        super().__init__(timeout=60)
        self.cards=cards_list
        self.claimed=[False]*3

    async def handle(self,interaction,idx):

        if self.claimed[idx]:
            await interaction.response.send_message("Taken",ephemeral=True)
            return

        self.claimed[idx]=True
        card=self.cards[idx]

        await users.update_one(
            {"id":interaction.user.id},
            {"$inc":{f"cards.{card['card_code']}":1}},
            upsert=True
        )

        # 🔥 CHECK FALLEN
        unlocked = await check_fallen(interaction.user.id, card["group"])

        self.children[idx].disabled=True
        await interaction.response.edit_message(view=self)

        e=discord.Embed(title=f"{RARITY_ICONS.get(card['rarity'],'')} {card['name']}")
        e.set_image(url=card["image_url"])

        await interaction.followup.send(embed=e)

        if unlocked:
            await interaction.followup.send(f"🩸 You unlocked FALLEN cards for {card['group']}!")

    @discord.ui.button(emoji=EMOJIS[0])
    async def b1(self,i,b): await self.handle(i,0)

    @discord.ui.button(emoji=EMOJIS[1])
    async def b2(self,i,b): await self.handle(i,1)

    @discord.ui.button(emoji=EMOJIS[2])
    async def b3(self,i,b): await self.handle(i,2)

# 🎴 DROP
@bot.tree.command(name="drop")
async def drop(interaction:discord.Interaction):

    chosen=[await get_card(interaction.user.id) for _ in range(3)]

    backs=[c["back_url"] for c in chosen]
    img=merge(backs)

    file=discord.File(img,"drop.png")

    e=discord.Embed(title="✧ ethereal drop ✧")
    for i,c in enumerate(chosen,1):
        e.add_field(name=f"{i}. {c['rarity']}",value=c["group"])

    e.set_image(url="attachment://drop.png")

    await interaction.response.send_message(embed=e,file=file,view=DropView(chosen))

# 🔍 VIEW
@bot.tree.command(name="view")
async def view(interaction:discord.Interaction,card_code:str):

    c=await cards.find_one({"card_code":card_code})
    u=await users.find_one({"id":interaction.user.id})

    count=u.get("cards",{}).get(card_code,0) if u else 0

    e=discord.Embed(title=c["name"])
    e.add_field(name="Group",value=c["group"])
    e.add_field(name="Rarity",value=c["rarity"])
    e.add_field(name="Code",value=c["card_code"])
    e.add_field(name="Era",value=c.get("era","None"))
    e.set_image(url=c["image_url"])

    await interaction.response.send_message(f"You own {count} copies",embed=e)

# 🎒 INVENTORY
@bot.tree.command(name="inventory")
async def inventory(interaction:discord.Interaction):

    u=await users.find_one({"id":interaction.user.id})

    if not u:
        await interaction.response.send_message("Empty")
        return

    text=""
    for code,count in u["cards"].items():
        c=await cards.find_one({"card_code":code})
        text+=f"{c['name']} x{count}\n"

    await interaction.response.send_message(text[:2000])

@bot.event
async def on_ready():
    await bot.tree.sync()
    print("READY")

bot.run(TOKEN)
