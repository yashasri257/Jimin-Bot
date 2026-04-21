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

LOG_CHANNEL_ID = 1496151311836512378

def is_staff(uid):
    return uid in STAFF_IDS

async def log_action(bot, message):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(message)

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
# 🎒 INVENTORY VIEW (PAGINATION)
# ======================
class InventoryView(discord.ui.View):
    def __init__(self, pages, user_id):
        super().__init__(timeout=120)
        self.pages = pages
        self.page = 0
        self.user_id = user_id

    async def update(self, interaction):
        embed = discord.Embed(
            title=self.pages[self.page]["title"],
            description=self.pages[self.page]["content"],
            color=0x2b2d31
        )
        embed.set_footer(text=f"page {self.page+1}/{len(self.pages)}")

        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="◀")
    async def prev(self, interaction, button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("✧ not yours", ephemeral=True)

        if self.page > 0:
            self.page -= 1
        await self.update(interaction)

    @discord.ui.button(label="▶")
    async def next(self, interaction, button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("✧ not yours", ephemeral=True)

        if self.page < len(self.pages)-1:
            self.page += 1
        await self.update(interaction)

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
# 🎁 GRANT COMMAND
# ======================
@tree.command(name="grant", description="✧ bestow cards or currency")
async def grant(
    interaction: discord.Interaction,
    user: discord.Member,
    currency: int = 0,

    card_code1: str = None, copies_1: int = 0,
    card_code2: str = None, copies_2: int = 0,
    card_code3: str = None, copies_3: int = 0,
    card_code4: str = None, copies_4: int = 0,
    card_code5: str = None, copies_5: int = 0
):

    if not is_staff(interaction.user.id):
        return await interaction.response.send_message("✧ you cannot wield this power", ephemeral=True)

    await interaction.response.defer()

    update_ops = {}
    log_text = []

    # 💰 currency
    if currency > 0:
        update_ops["currency"] = currency
        log_text.append(f"+{currency} {CURRENCY_NAME}")

    # 🎴 cards
    pairs = [
        (card_code1, copies_1),
        (card_code2, copies_2),
        (card_code3, copies_3),
        (card_code4, copies_4),
        (card_code5, copies_5),
    ]

    for code, amount in pairs:
        if code and amount > 0:
            update_ops[f"cards.{code}"] = amount
            log_text.append(f"+{amount} {code}")

    if not update_ops:
        return await interaction.followup.send("✧ nothing to grant")

    await users.update_one(
        {"id": user.id},
        {"$inc": update_ops},
        upsert=True
    )

    msg = f"✧ {interaction.user.mention} granted {user.mention}:\n" + "\n".join(log_text)

    await interaction.followup.send("✧ granted successfully")
    await log_action(interaction.client, msg)

# ======================
# ⛓️‍💥 REVOKE COMMAND
# ======================
@tree.command(name="revoke", description="✧ take away cards or currency")
async def revoke(
    interaction: discord.Interaction,
    user: discord.Member,
    currency: int = 0,

    card_code1: str = None, copies_1: int = 0,
    card_code2: str = None, copies_2: int = 0,
    card_code3: str = None, copies_3: int = 0,
    card_code4: str = None, copies_4: int = 0,
    card_code5: str = None, copies_5: int = 0
):

    if not is_staff(interaction.user.id):
        return await interaction.response.send_message("✧ you cannot wield this power", ephemeral=True)

    await interaction.response.defer()

    user_data = await users.find_one({"id": user.id}) or {"cards": {}, "currency": 0}

    update_ops = {}
    log_text = []

    # 💰 currency SAFE REMOVE
    if currency > 0:
        current = user_data.get("currency", 0)
        remove_amount = min(currency, current)

        if remove_amount > 0:
            update_ops["currency"] = -remove_amount
            log_text.append(f"-{remove_amount} {CURRENCY_NAME}")

    # 🎴 cards SAFE REMOVE
    pairs = [
        (card_code1, copies_1),
        (card_code2, copies_2),
        (card_code3, copies_3),
        (card_code4, copies_4),
        (card_code5, copies_5),
    ]

    for code, amount in pairs:
        if code and amount > 0:
            current = user_data.get("cards", {}).get(code, 0)
            remove_amount = min(amount, current)

            if remove_amount > 0:
                update_ops[f"cards.{code}"] = -remove_amount
                log_text.append(f"-{remove_amount} {code}")

    if not update_ops:
        return await interaction.followup.send("✧ nothing to revoke")

    await users.update_one(
        {"id": user.id},
        {"$inc": update_ops}
    )

    msg = f"✧ {interaction.user.mention} revoked from {user.mention}:\n" + "\n".join(log_text)

    await interaction.followup.send("✧ revoked successfully")
    await log_action(interaction.client, msg)

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
# INVENTORY 
# ======================
@tree.command(name="inventory", description="✧ view a collection of owned cards")
@app_commands.describe(
    user="view another user's inventory",
    name="filter by idol name",
    group="filter by group",
    rarity="filter by rarity",
    dupes="show only duplicates"
)
@app_commands.choices(rarity=RARITY_CHOICES)
async def inventory(
    interaction: discord.Interaction,
    user: discord.User = None,
    name: str = None,
    group: str = None,
    rarity: app_commands.Choice[str] = None,
    dupes: bool = False
):

    await interaction.response.defer()

    target = user or interaction.user

    data = await users.find_one({"id": target.id})
    if not data or "cards" not in data:
        await interaction.followup.send("✧ nothing rests here...", ephemeral=True)
        return

    user_cards = data["cards"]

    # 🔥 FETCH ALL CARDS IN ONE GO
    card_list = await cards.find({
        "card_code": {"$in": list(user_cards.keys())}
    }).to_list(None)

    items = []

    for card in card_list:
        code = card["card_code"]
        count = user_cards.get(code, 0)

        # filters
        if name and name.lower() not in card["name"].lower():
            continue
        if group and group.lower() != card["group"]:
            continue
        if rarity and rarity.value != card["rarity"]:
            continue

        display_count = count - 1 if dupes else count
        if display_count <= 0:
            continue

        icon = RARITY_ICONS.get(card["rarity"], "")

        text = f"{card['group'].title()} ✧ {card['name']} • [{card['rarity'].title()}]({icon}) • {card['card_code']} ×{display_count}"

        items.append({
            "group": card["group"],
            "text": text
        })

    if not items:
        await interaction.followup.send("✧ nothing matches the search...", ephemeral=True)
        return

    # 🔥 SORT
    items.sort(key=lambda x: x["group"])

    # 🔥 PAGINATION
    per_page = 5
    pages = []

    for i in range(0, len(items), per_page):
        chunk = items[i:i+per_page]
        content = "\n".join(x["text"] for x in chunk)

        pages.append({
            "title": f"{target.name}'s inventory",
            "content": content
        })

    embed = discord.Embed(
        title=pages[0]["title"],
        description=pages[0]["content"],
        color=0x2b2d31
    )
    embed.set_footer(text=f"page 1/{len(pages)}")

    await interaction.followup.send(
        embed=embed,
        view=InventoryView(pages, interaction.user.id)
    )

# ======================
# COLLECTION 
# ======================
@tree.command(name="collection", description="✧ view your collection progress")
@app_commands.describe(
    group="view a specific group's collection",
    name="view collection of an idol",
    rarity="filter by rarity"
)
@app_commands.choices(rarity=RARITY_CHOICES)
async def collection(
    interaction: discord.Interaction,
    group: str = None,
    name: str = None,
    rarity: app_commands.Choice[str] = None
):

    uid = interaction.user.id
    user_data = await users.find_one({"id": uid}) or {"cards": {}}

    owned = user_data.get("cards", {})

    query = {}
    if group:
        query["group"] = group.lower()
    if name:
        query["name"] = {"$regex": name, "$options": "i"}
    if rarity:
        query["rarity"] = rarity.value

    all_cards = await cards.find(query).to_list(None)

    if not all_cards:
        await interaction.response.send_message("✧ no such cards exist...", ephemeral=True)
        return

    total = len(all_cards)
    owned_count = 0

    for c in all_cards:
        if owned.get(c["card_code"], 0) > 0:
            owned_count += 1

    percent = int((owned_count / total) * 100)

    embed = discord.Embed(
        title="✧ collection ✧",
        description=(
            f"progress: {owned_count}/{total}\n"
            f"completion: {percent}%"
        ),
        color=0x2b2d31
    )

    # ✨ show small preview list
    preview = []
    for c in all_cards[:10]:
        if owned.get(c["card_code"], 0) > 0:
            preview.append(f"✓ {c['name']}")
        else:
            preview.append(f"✧ {c['name']}")

    embed.add_field(
        name="cards",
        value="\n".join(preview),
        inline=False
    )

    await interaction.response.send_message(embed=embed)

    # ======================
    # 🩸 FALLEN UNLOCK
    # ======================
    if group and percent == 100:
        fallen_cards = await cards.find({
            "group": group.lower(),
            "rarity": "fallen"
        }).to_list(None)

        for c in fallen_cards:
            await users.update_one(
                {"id": uid},
                {"$inc": {f"cards.{c['card_code']}": 1}},
                upsert=True
            )

        if fallen_cards:
            await interaction.followup.send(
                f"✧ the veil parts... fallen cards awaken for {group}"
            )

# ======================
# READY
# ======================
@bot.event
async def on_ready():
    await tree.sync()
    print("READY")

bot.run(TOKEN)
